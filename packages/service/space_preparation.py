"""Read saved preparation evidence without source IO or polling workers."""
from packages.data.preflight_records import PreflightRecords
from packages.data.input_descriptions import InputDescriptions
from packages.data.input_routes import route
import json


def preparation(jobs,sources,space_id,input_id=None,batch_id=None):
    saved=sources.read(space_id)
    enabled=sources.effective(saved)
    records=[r for r in jobs.inputs.list() if r.get('space_id')==space_id]
    if input_id and not any(r['id']==input_id for r in records):raise PermissionError('input_not_in_space')
    checks=PreflightRecords(jobs.inputs)
    saved_jobs=[json.loads(p.read_bytes()) for p in jobs.root.glob('*/job.json')]
    rows=[]
    for record in records:
        latest=checks.latest(record['id'])
        state=jobs.controls.read(space_id,'input:'+record['id'])['lifecycle_state']
        fixed_binding={k:v for k,v in record.items() if k not in ('snapshot','tracking')}
        related=[j for j in saved_jobs if j.get('space_id')==space_id and j.get('input_id')==record['id'] and j.get('input_binding') in (record,fixed_binding)]
        counts={s:sum(j.get('state')==s for j in related) for s in ('queued','running','succeeded','failed','interrupted','views_failed')}
        batches=jobs.batches.preparation(jobs.inputs.read(record['id']),space_id,batch_id if record['id']==input_id else None)
        rows.append({'input_id':record['id'],'label':record['label'],'route':route(record['format']),'batch':batches,'presentation':InputDescriptions(jobs.inputs).presentation(record),'lifecycle_state':state,'saved_build_counts':counts,
            'check_status':'not_checked' if not latest else 'registration_changed' if not latest['registration_matches'] else latest['status'],
            'checked_at':latest['checked_at'] if latest else None,'check_sequence':latest['sequence'] if latest else None,
            'issue':latest.get('issue') if latest else None,'action':{'module':'data','label':'查看资料与预检','values':{'space':space_id,'input':record['id']}}})
    target=next((r for r in rows if r['input_id']==input_id),None)
    if batch_id and not target:raise ValueError('batch_requires_explicit_input')
    if target:
        checked=target['check_status']=='passed' and target['lifecycle_state']=='active'
        ready=checked and target['batch']['can_submit']
        action={'module':'build' if ready else 'data','label':'前往构建中心' if ready else '查看资料与预检','values':{'space':space_id,'input':input_id}}
        detail='已保存预检通过记录；构建提交仍重新核验文件与使用状态。' if ready else '请检查所选资料的预检结果与使用状态。'
        if target['lifecycle_state']!='active':detail='资料已停用或归档，请先核查使用状态。'
        elif target['check_status']!='passed':
            detail={'not_checked':'尚未保存预检记录，请先执行预检。','failed':'上次预检失败，请核查问题后重新预检。',
                    'registration_changed':'登记记录已变化，请重新预检。'}.get(target['check_status'],'预检状态未知，请核查记录。')
        if batch_id:action['values']['batch']=batch_id
        if checked and not ready:
            selection=target['batch']['status']=='selection_required'
            action.update(module='build' if selection else 'data',label='选择封存批次' if selection else '整理批次')
            action['values']['tab']='tasks' if selection else 'batches'
            detail='请选择本次使用的封存批次；不会自动选择最近批次。' if selection else '所选批次与资料不匹配、尚未封存或已停用，请核查批次。'
            if not selection:
                choice=next((c for c in target['batch']['choices'] if c['id']==batch_id),None)
                states={c['state'] for c in target['batch']['choices']}
                if choice and choice['state']=='disabled' or not batch_id and states=={'disabled'}:detail='批次已停用，请核查并显式恢复后再构建。'
                elif choice and choice['state']=='draft' or not batch_id and 'draft' in states:detail='批次仍在整理中，请核对成员并封存后再构建。'
                elif target['batch']['issue']=='input_not_in_batch':detail='指定批次不包含当前资料，请核查明确传入的批次引用。'
        if ready and any(target['saved_build_counts'][s] for s in ('queued','running')):
            detail='有保存的进行中任务，请到构建中心刷新实际进程状态。'
        elif ready and target['saved_build_counts']['succeeded']:
            detail='已有绑定此资料的成功候选，请到构建中心核对选择；不会自动替换当前候选或发布。'
    elif rows:
        action={'module':'data','label':'选择资料并预检','values':{'space':space_id,'tab':'inputs'}}
        detail='选择本次要构建的资料，查看或执行预检；不自动使用最新登记。'
    else:
        action={'module':'data','label':'导入资料','values':{'space':space_id,'tab':'inputs'},'intent':'import'}
        detail='上传资料包，或从已启用来源登记资料；上传不要求先配置来源。'
    return {'profile':'cospace.space-preparation/0.1','source_revision':saved['revision'],'enabled_source_count':len(enabled),
        'can_submit':bool(target and ready),'selected_batch_id':batch_id,
        'inputs':rows,'selected_input_id':input_id,'next_action':action,'detail':detail,'current_files_checked':False,
        'jobs_polled':False,'quality':'unverified'}
