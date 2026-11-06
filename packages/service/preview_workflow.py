"""Current-space reference flow, anchored to the selected immutable candidate.

Reads saved records only: no job polling, source preflight, bundle export or consumer IO.
"""
import json
from packages.data.preview_artifacts import artifact_catalog
from packages.construction.preview_model import PreviewModel,digest
from packages.construction.preview_jobs import now
from packages.lifecycle.preview_scope import scope,match
from packages.service.preview_publication_changes import review_provenance

def workflow(publications,space_id,job_id=None,publication_id=None,preparation_report=None):
    if not space_id:raise ValueError('explicit_space_required')
    jobs=publications.jobs;ownership=scope(jobs.directory,space_id)
    selection_path=jobs.root/'space-selections'/(space_id+'.json')
    selection_before=selection_path.read_bytes() if selection_path.exists() else None
    catalog=artifact_catalog(publications,space_id);items=catalog['items'];stages=[]
    selected=next((i for i in items if i['kind']=='candidate' and i['selected']),None)
    model=None;selection=None;selection_raw=None;review_status='not_recorded'
    path=jobs.root/'space-selections'/(space_id+'.json')
    if selected:
        selection_raw=path.read_bytes();selection=json.loads(selection_raw);match(selection,ownership)
        model=PreviewModel(jobs.root/selected['record_id']/'output')
        if selection.get('candidate_id')!=selected['record_id'] or digest(model.root/'model.json')!=selection.get('model_manifest_sha256'):
            raise ValueError('workflow_selection_changed_refresh_required')
        review_status=review_provenance({'candidate_id':selected['record_id'],'model_manifest_sha256':selection['model_manifest_sha256'],
            'selection_revision':selection['revision'],'selection_review':selection.get('selection_review'),**ownership},None)['status']
    broken=catalog['selection_status']=='missing_or_mismatch'
    candidates=[i for i in items if i['kind']=='candidate' and i['integrity']=='snapshot_verified']
    releases=[i for i in items if i['kind']=='publication' and i['integrity']=='snapshot_verified']
    matching=sorted([i for i in releases if selected and i['model_manifest_sha256']==selected['model_manifest_sha256']
                     and json.loads((publications.root/i['record_id']/'publication.json').read_bytes())['candidate_id']==selected['record_id']],
                    key=lambda i:(i.get('created_at') or '',i['record_id']),reverse=True)
    publication=matching[0] if matching else None
    paused=bool(publication and publication.get('lifecycle_state') in ('paused','retired'))
    values={'space':space_id,**({'job':selected['record_id']} if selected else {})}
    def add(identity,title,module,status,detail,action,params=None,basis='saved_space_records'):
        stages.append({'id':identity,'title':title,'module':module,'status':status,'detail':detail,'basis':basis,
                       'action':{'label':action,'module':module,'values':params or values}})
    batch_ref=model.manifest.get('source',{}).get('batch_ref') if model else None
    inputs=[i for i in items if i['kind']=='input'];input_id=None
    input_link=next((r for r in catalog['relations'] if selected and r['from']==selected['key'] and r['relation']=='built_from'),None)
    if input_link and input_link['to']:input_id=input_link['to'].split(':',1)[1]
    input_status='blocked' if broken or input_link and input_link['status']!='matched' else 'recorded' if inputs else 'pending'
    add('data','资料登记与来源','data',input_status,
        '当前候选的登记来源绑定一致；源文件未在本次重新预检。' if input_link and input_link['status']=='matched' else
        '当前选择或来源绑定不可用，请处理来源问题。' if input_status=='blocked' else
        f'本空间已登记 {len(inputs)} 项资料，尚未绑定当前候选。' if inputs else '先登记本空间的封存资料，并在构建前执行预检。',
        '查看资料与预检',{'space':space_id,**({'input':input_id} if input_id else {})})
    if batch_ref:
        stages[-1]['detail']+=f" 保存的构建批次：{batch_ref['batch_id']}（提交修订 {batch_ref['admitted_revision']}）；此处不检查批次当前启停。"
        stages[-1]['action']['values']['batch']=batch_ref['batch_id']
        stages[-1]['action']['label']='查看来源批次与资料'
    active=sum(catalog['job_counts'].get(s,0) for s in ('running','queued'))
    build_status='blocked' if broken or review_status=='binding_mismatch' else 'ready' if model and review_status=='internally_consistent' else 'in_progress' if active else 'pending'
    add('build','候选构建与人工核对','build',build_status,
        '已选固定候选，保存的人工核对记录绑定一致；现场质量仍待验收。' if build_status=='ready' else
        '当前选择或保存核对记录不一致，请重新读取并核对。' if build_status=='blocked' else
        f'保存记录中有 {active} 个进行中任务；此处不轮询进程，请到构建中心检查。' if active else
        '当前候选缺少保存的人工核对记录，请在构建中心核对。' if model else
        f'已有 {len(candidates)} 个可读候选，尚未核对选择。' if candidates else '提交构建，生成独立候选后核对并选择。',
        '前往构建中心',values|{'tab':'flow'})
    semantics=model.semantic_snapshot if model else None
    ontology=semantics['ontology_ref'] if semantics else None
    add('ontology','固定本体应用','ontology','blocked' if broken else 'recorded' if ontology else 'pending',
        f"当前候选固定引用 {ontology['ontology_id']} · V{ontology['version']}，嵌入规则与对象校验通过。" if ontology else '可按业务需要选择固定本体规则，并在空间关联应用于对象；不阻塞几何双视图发布与使用。',
        '查看固定本体',{'space':space_id,**({'ontology_id':ontology['ontology_id'],'ontology_version':ontology['version'],'ontology_sha256':ontology['sha256']} if ontology else {})},'selected_snapshot')
    stages[-1]['optional']=True
    object_count=len(semantics['objects']) if semantics else 0
    business=getattr(model,'business_snapshot',None);relations=getattr(model,'relation_snapshot',None)
    business_count=len(business['bindings']) if business else 0;relation_count=len(relations['relations']) if relations else 0
    missing=[name for name,count in [('对象标注',object_count),('业务台账绑定',business_count),('对象关系',relation_count)] if not count]
    add('association','对象、台账与关系','association','blocked' if broken else 'pending' if missing else 'recorded',
        f'当前候选：{object_count} 个对象、{business_count} 个台账绑定、{relation_count} 条关系。'+(' 可按业务需要补充：'+'、'.join(missing)+'；不阻塞几何双视图发布与使用。' if missing else '快照绑定与规则通过，现场含义仍待核实。'),
        '补齐或查看空间关联',basis='selected_snapshot')
    stages[-1]['optional']=True
    pub_values=values|({'publication':publication['record_id']} if publication else {})
    add('delivery','当前候选固定发布','delivery','blocked' if broken or paused else 'recorded' if publication else 'pending',
        f"匹配发布 {publication['record_id']} 已暂停或退役，请在态势服务核查状态及替代版本。" if paused else
        f"匹配当前候选及摘要的固定发布：{publication['record_id']}。离线包按需生成，尚未检查消费端。" if publication else
        f'当前候选尚无匹配发布；本空间另有 {len(releases)} 个历史固定发布，不代替当前候选发布。' if releases else '核对选择候选后，另行固定发布。',
        '查看发布与离线交付',pub_values,'matching_publication')
    human=bool(model and model.manifest.get('human_view',{}).get('path') in model.manifest['members'])
    add('space','固定双视图预览','space','blocked' if broken or paused or publication and not human else 'ready' if publication and human else 'pending',
        '匹配发布已暂停或退役，不能打开空间；不会自动改用历史版本。' if paused else
        '打开与当前候选一致的固定发布，在独立标签页查看双视图。' if publication and human else '需要匹配发布及完整双视图成员；历史空间预览仍可独立浏览。',
        '打开固定空间' if publication and human and not paused else '前往态势服务核查',pub_values,'matching_publication')
    if paused:stages[-1]['action']['module']='delivery'
    # Consumer state belongs to another process/device. Server records cannot prove activation.
    add('consumer','离线消费与恢复','delivery','unobserved','当前服务不读取消费端状态；下载、导出或本机已有消费能力均不证明该发布已安装、激活或恢复。',
        '查看本地消费步骤',pub_values|{'from':'consumer'},'consumer_not_observed')
    next_stage=next((s for s in stages if s['status']=='blocked'),None) or next((s for s in stages if not s.get('optional') and s['status'] in ('pending','in_progress')),None) or next(s for s in stages if s['id']=='space')
    result={'profile':'cospace.preview-workflow/0.1',**ownership,'observed_at':now(),
            'selection_status':catalog['selection_status'],'candidate_ref':{'candidate_id':selected['record_id'],'model_manifest_sha256':selected['model_manifest_sha256']} if selected else None,
            'publication_ref':{'publication_id':publication['record_id'],'model_manifest_sha256':publication['model_manifest_sha256']} if publication else None,
            'counts':catalog['counts']|{'objects':object_count,'business_bindings':business_count,'object_relations':relation_count},
            'stages':stages,'next_action':next_stage['action'],'next_stage':next_stage['id'],
            'source_files_rechecked':False,'consumer_state_checked':False,'jobs_polled':False,
            'scope':'reference_flow_not_publication_gate','consistency':'request_time_reads_not_transactional',
            'quality':'unverified','production_ready':False,'robot_ready':False}
    from packages.service.scene_progress import progress
    result['summary']=progress(publications,result,catalog,job_id,publication_id,preparation_report)
    if preparation_report is not None:result['preparation']=preparation_report
    if selection_raw is not None and path.read_bytes()!=selection_raw:raise ValueError('workflow_selection_changed_refresh_required')
    if (path.read_bytes() if path.exists() else None)!=selection_before:raise ValueError('workflow_selection_changed_refresh_required')
    return result
