"""Read-only lifecycle policy preview over saved space records, never an execution permit."""
from collections import deque
import json
from packages.construction.preview_jobs import now
from packages.construction.preview_model import digest
from packages.data.preview_artifacts import artifact_catalog,records
from packages.data.preview_batches import checksum
from packages.lifecycle.preview_scope import scope,owned

PROFILE='cospace.preview-artifact-impact/0.1'
POLICY='cospace.preview-lifecycle-policy/0.1'

def impact(publications,space_id,artifact):
    if not space_id:raise ValueError('explicit_space_required')
    if not isinstance(artifact,str) or ':' not in artifact:raise ValueError('impact_artifact_invalid')
    kind,identity=artifact.split(':',1)
    if kind not in ('input','candidate','publication'):raise ValueError('impact_kind_not_supported')
    jobs=publications.jobs;ownership=scope(jobs.directory,space_id)
    selection_path=jobs.root/'space-selections'/(space_id+'.json')
    selection_before=selection_path.read_bytes() if selection_path.exists() else None
    catalog=artifact_catalog(publications,space_id);items={i['key']:i for i in catalog['items']}
    if artifact not in items:raise ValueError('impact_artifact_not_found')
    target=items[artifact]
    # Traverse verified reverse references, never infer relationships from filenames or latest time.
    depth={artifact:0};queue=deque([artifact])
    while queue:
        parent=queue.popleft()
        for relation in catalog['relations']:
            if relation['status']=='matched' and relation['to']==parent and relation['from'] not in depth:
                depth[relation['from']]=depth[parent]+1;queue.append(relation['from'])
    refs=[]
    def add(key,ref_kind,record_id,label,state,relation,distance,**extra):
        refs.append({'key':key,'kind':ref_kind,'record_id':record_id,'label':label,'state':state,
                     'relation':relation,'distance':distance,**extra})
    for key,distance in sorted(depth.items()):
        if not distance:continue
        item=items[key]
        add(key,item['kind'],item['record_id'],item['label'],item['state'],'saved_artifact_reference',distance,selected=item['selected'])
    job_rows=[(p,r) for p,r in records(jobs.root,'*/job.json') if owned(r)==ownership]
    input_rows=[(p,r) for p,r in records(jobs.inputs.root if jobs.inputs else None,'input-*.json') if owned(r)==ownership]
    batches=jobs.batches.list(space_id) if jobs.batches else []
    issues=[]
    # An incomplete space graph may hide inbound references: no optimistic "zero references" decisions.
    for item in items.values():
        if item['integrity']=='unavailable':issues.append({'code':'artifact_unavailable','key':item['key']})
    for relation in catalog['relations']:
        if relation['status']!='matched':issues.append({'code':'reference_'+relation['status'],'key':relation['from']})
    if catalog['selection_status']=='missing_or_mismatch':issues.append({'code':'selection_binding_unavailable','key':None})
    known_inputs={r['id'] for _,r in input_rows}
    # Saved queued/running attempts are deliberately not polled, and count as still active.
    for _,job in job_rows:
        state=job.get('state');job_id=job.get('id')
        linked=(kind=='input' and job.get('input_id')==identity or
                kind=='candidate' and (job_id==identity or job.get('base_candidate_id')==identity or 'candidate:'+str(job_id) in depth))
        if state in ('queued','running') and job.get('input_id') not in known_inputs:
            issues.append({'code':'active_job_source_unresolved','key':'job:'+str(job_id)})
        if not linked:continue
        add('job:'+job_id,'job',job_id,job_id,state or 'unknown','saved_build_attempt',0 if job_id==identity else 1)
    for batch in batches:
        for member in batch['members']:
            registered=next((r for _,r in input_rows if r['id']==member['input_id']),None)
            from packages.data.input_coordinates import InputCoordinates
            if registered is None or not any(checksum(r)==member['input_record_sha256']
                    for r in InputCoordinates(jobs.inputs).fixed_records(registered)):
                issues.append({'code':'batch_member_missing_or_changed','key':'batch:'+batch['id']})
        if kind=='input' and any(m['input_id']==identity for m in batch['members']):
            add('batch:'+batch['id'],'batch',batch['id'],batch['name'],batch['state'],'batch_membership',1,revision=batch['revision'])
    selected=[i for i in items.values() if i['selected']]
    selected_dependencies=[i['key'] for i in selected if i['key'] in depth]
    # Stable content digest excludes checked_at and absolute paths. It is not a signature or authorization.
    evidence={'policy':POLICY,**ownership,'artifact':artifact,'items':catalog['items'],'relations':catalog['relations'],
              'selection_sha256':checksum(json.loads(selection_before)) if selection_before else None,
              'input_record_hashes':{r['id']:digest(p) for p,r in input_rows},
              'job_record_hashes':{r['id']:digest(p) for p,r in job_rows},'batches':batches}
    issues=sorted({(i['code'],i['key']) for i in issues},key=lambda i:(i[0],i[1] or ''))
    issues=[{'code':code,'key':key} for code,key in issues]
    global_blockers=['dependency_records_incomplete'] if issues else []
    plans=[]
    def plan(operation,title,blocks,effect,retained,next_steps):
        blockers=list(dict.fromkeys(global_blockers+blocks))
        plans.append({'operation':operation,'title':title,'decision':'blocked' if blockers else 'eligible_by_saved_records',
                      'blockers':blockers,'effect_if_implemented':effect,'retained':retained,'next_steps':next_steps,
                      'executable':False})
    if kind=='input':
        active_batches=[r for r in refs if r['kind']=='batch' and r['state']!='disabled']
        active_attempts=[r for r in refs if r['kind']=='job' and r['state'] in ('queued','running')]
        plan('disable_input','停用资料',[],
             '阻止以此登记资料发起新的资料构建，包括批次入口；不追溯取消已准入任务。',
             ['登记记录与源文件','批次成员与封存摘要','已生成候选、固定发布及离线包'],
             ['核对受影响批次；后续构建须使用其他可用登记资料。'])
        plan('archive_input','归档资料',(['active_batch_membership'] if active_batches else [])+
             (['saved_active_build_attempt'] if active_attempts else [])+(['current_selection_depends_on_input'] if selected_dependencies else []),
             '从新建资料选择范围移出并阻止新构建；保持历史详情与来源可追溯，不移动或删除源文件。',
             ['全部历史引用和文件','已有固定发布的查询和导出'],
             ['先处理整理中/封存批次；已停用批次成员保留。','确认活动任务结束，并显式选择替代候选后重新检查。'])
    elif kind=='candidate':
        active_attempts=[r for r in refs if r['kind']=='job' and r['state'] in ('queued','running')]
        plan('archive_candidate','归档候选',(['candidate_is_current_selection'] if target['selected'] else [])+
             (['saved_active_build_attempt'] if active_attempts else []),
             '阻止以后选择此候选、以其新建关联候选或固定发布；不级联归档已有派生候选。',
             ['候选内容、差异比较及基线记录','已有派生候选、固定发布与离线包'],
             ['如为当前选择，先人工核对并切换替代候选。','等待引用该基线的活动任务结束后重新检查。'])
    else:
        plan('pause_distribution','停止发布分发',[],
             '停止此发布的新在线查询、双视图资产读取及离线导出；历史审计读取须另设受控入口。',
             ['发布快照和来源记录','已安装、已下载或已缓存的消费数据'],
             ['覆盖此发布的全部查询和资产端点，不能仅隐藏下载按钮。','确认工程空间入口的替代发布；不能宣称远程撤回离线数据。'])
    if (selection_path.read_bytes() if selection_path.exists() else None)!=selection_before:
        raise ValueError('impact_selection_changed_refresh_required')
    return {'profile':PROFILE,'policy_version':POLICY,**ownership,'checked_at':now(),
            'target':{k:target[k] for k in ('key','kind','record_id','label','state','integrity','selected')},
            'snapshot_sha256':checksum(evidence),'references':sorted(refs,key=lambda r:r['key']),
            'reference_counts':{k:sum(r['kind']==k for r in refs) for k in ('batch','job','candidate','publication','offline_package')},
            'selected_dependencies':sorted(selected_dependencies),'issues':issues,'plans':plans,
            'mode':'impact_preview_only','mutation_supported':False,'jobs_polled':False,
            'source_files_rechecked':False,'consumer_state_checked':False,
            'consistency':'request_time_reads_not_transactional','quality':'unverified','robot_ready':False}
