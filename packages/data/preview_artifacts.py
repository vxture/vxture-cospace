"""Read-only space artifact inventory. Never poll jobs or generate offline bundles."""
import json
import re
from packages.construction.preview_jobs import now
from packages.construction.preview_model import PreviewModel,digest
from packages.lifecycle.preview_scope import scope,owned,match
from packages.service.preview_publication_changes import read_fixed
from packages.views.agent.preview_offline import bundle_profile

KINDS=('input','candidate','publication','offline_package')


def records(root,pattern):
    if root is None:return []
    result=[]
    for path in sorted(root.glob(pattern)):
        if path.parent!=root and path.parent.name.startswith('.'):continue
        try:
            record=json.loads(path.read_bytes())
            if not isinstance(record,dict):raise ValueError()
        except (OSError,ValueError,TypeError) as exc:
            raise ValueError('catalog_record_unreadable') from exc
        result.append((path,record))
    return result


def artifact_catalog(publications,space_id=None):
    jobs=publications.jobs;ownership=scope(jobs.directory,space_id)
    input_records=records(jobs.inputs.root if jobs.inputs else None,'input-*.json')
    job_records=records(jobs.root,'*/job.json')
    publication_records=records(publications.root,'preview-*/publication.json')
    items=[];relations=[];models={};inputs={};candidates={};published={};published_models={}
    # Global ownership is used only to classify a broken cross-space reference.
    all_scopes={}
    for kind,rows in [('input',input_records),('candidate',job_records),('publication',publication_records)]:
        for path,record in rows:
            identity=path.stem if kind=='input' else path.parent.name
            all_scopes[f'{kind}:{identity}']=owned(record)

    def add(kind,identity,label,classification,state,created_at=None):
        entry={'key':f'{kind}:{identity}','kind':kind,'record_id':identity,'label':label,
               'classification':classification,'state':state,'created_at':created_at,
               'integrity':'not_checked','problems':[],'resources':{},'selected':False}
        items.append(entry);return entry

    def relationship(source,kind,identity,relation,status=None):
        target=f'{kind}:{identity}' if isinstance(identity,str) else None
        local=next((item for item in items if item['key']==target),None)
        if target in all_scopes and all_scopes[target]!=ownership:
            status='mismatch';target=None
        elif local is None:
            status='missing' if identity else 'unrecorded';target=None
        elif status is None:
            status='matched' if local['integrity']!='unavailable' else 'mismatch'
        value={'from':source['key'],'to':target,'relation':relation,'status':status}
        relations.append(value);return value

    for path,record in input_records:
        if owned(record)!=ownership:continue
        identity=path.stem
        if not re.fullmatch(r'input-[a-f0-9]{16}',identity):raise ValueError('catalog_record_invalid')
        label=record.get('label') if isinstance(record.get('label'),str) else identity
        entry=add('input',identity,label,'registered_source','registered')
        if (record.get('id')!=identity or record.get('profile')!='cospace.preview-input/0.1'
                or record.get('format') not in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp','nyu_rgbd_with_existing_poses','ply_pointcloud')):
            entry.update(integrity='unavailable',problems=['input_record_invalid'])
        else:
            entry.update(integrity='record_only',format=record.get('format','unknown'))
            from packages.data.input_coordinates import InputCoordinates
            inputs[identity]=[{k:v for k,v in r.items() if k not in ('snapshot','tracking')}
                              for r in InputCoordinates(jobs.inputs).fixed_records(record)]
        entry['resources']={'details_url':f'/api/inputs/{identity}'}

    job_counts={}
    for path,record in job_records:
        if owned(record)!=ownership:continue
        state=record.get('state','unknown');job_counts[state]=job_counts.get(state,0)+1
        if state!='succeeded':continue
        identity=path.parent.name
        if not re.fullmatch(r'build-[A-Za-z0-9-]+',identity):raise ValueError('catalog_record_invalid')
        entry=add('candidate',identity,identity,'candidate_unknown','candidate',record.get('created_at'))
        candidates[identity]=(entry,record)
        try:
            if record.get('id')!=identity:raise ValueError()
            model=PreviewModel(path.parent/'output');match(model.manifest,ownership)
            if model.manifest['id']!=identity:raise ValueError()
            if record.get('batch_ref')!=model.manifest.get('source',{}).get('batch_ref'):raise ValueError()
            binding=model.manifest.get('source',{}).get('input_binding')
            if record.get('input_binding')!=binding:raise ValueError()
            if binding and owned(binding)!=ownership:raise ValueError()
            entry.update(label=model.manifest.get('label',identity),integrity='snapshot_verified',
                         classification='semantic_candidate' if model.semantic_snapshot else 'geometry_candidate',
                         model_manifest_sha256=digest(model.root/'model.json'),
                         format=model.manifest.get('data_kind','cospace.real-model-preview/0.1'))
            entry['resources']={'manifest_url':f'/candidates/{identity}/model.json','preview_url':f'/candidates/{identity}/'}
            models[identity]=model
        except (OSError,ValueError,KeyError,TypeError):
            entry.update(integrity='unavailable',problems=['candidate_snapshot_unavailable_or_binding_mismatch'])

    for path,record in publication_records:
        if owned(record)!=ownership:continue
        identity=path.parent.name
        entry=add('publication',identity,identity,'fixed_publication','preview_published',record.get('created_at'))
        published[identity]=(entry,record)
        try:
            fixed,model,ref=read_fixed(publications,identity,ownership)
            # Use the verified read, rather than earlier metadata, for relationships.
            published[identity]=(entry,fixed)
            published_models[identity]=model
            entry.update(integrity='snapshot_verified',model_manifest_sha256=ref['model_manifest_sha256'])
            entry['resources']={'manifest_url':f'/publications/{identity}/publication.json',
                                'preview_url':f'/publications/{identity}/'}
            package=add('offline_package',identity,identity+' · 离线包','offline_export','export_on_request')
            package.update(integrity='not_generated',format=bundle_profile(model))
            package['resources']={'info_url':f'/publications/{identity}/offline.json','download_url':f'/publications/{identity}/offline.zip'}
            relations.append({'from':package['key'],'to':entry['key'],'relation':'exported_from','status':'matched'})
        except (OSError,ValueError,KeyError,TypeError):
            entry.update(integrity='unavailable',problems=['publication_snapshot_unavailable_or_binding_mismatch'])

    def input_relation(entry,model,relation,job=None):
        source=model.manifest.get('source',{});binding=source.get('input_binding')
        input_id=binding.get('id') if binding else None
        keys=(('snapshot_sha256','cloud_sha256') if binding and binding.get('format')=='ply_pointcloud' else
              ('snapshot_sha256','bag_sha256','selected_frame') if binding and binding.get('format') in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp') else ('snapshot_sha256','tracking_sha256'))
        consistent=(binding is not None and binding in inputs.get(input_id,[])
                    and (job is None or job.get('input_id')==input_id)
                    and all(key in binding and binding[key]==source.get(key) for key in keys))
        relationship(entry,'input',input_id,relation,None if not input_id else 'matched' if consistent else 'mismatch')

    for identity,(entry,job) in candidates.items():
        model=models.get(identity)
        if not model:continue
        input_relation(entry,model,'built_from',job)
        if model.semantic_snapshot:
            base=model.manifest['semantic_annotation']['base_candidate_ref']
            target=candidates.get(base['candidate_id'])
            matches=(target and target[0].get('model_manifest_sha256')==base['model_manifest_sha256']
                     and job.get('base_candidate_id')==base['candidate_id']
                     and job.get('base_manifest_sha256')==base['model_manifest_sha256'])
            relationship(entry,'candidate',base['candidate_id'],'annotated_from','matched' if matches else 'mismatch')

    for identity,(entry,record) in published.items():
        if entry['integrity']=='unavailable':continue
        input_relation(entry,published_models[identity],'sourced_from')
        target=candidates.get(record['candidate_id'])
        matches=target and target[0].get('model_manifest_sha256')==record['model_manifest_sha256']
        relationship(entry,'candidate',record['candidate_id'],'published_from','matched' if matches else 'mismatch')

    # Do not call selection_path/selection: both can create a directory on a GET.
    selection_path=jobs.root/'space-selections'/(space_id+'.json') if space_id else jobs.root/'selection.json'
    selection_status='not_selected'
    if selection_path.exists():
        try:
            selected=json.loads(selection_path.read_bytes());match(selected,ownership)
            current=candidates.get(selected.get('candidate_id'))
            if current and current[0].get('model_manifest_sha256')==selected.get('model_manifest_sha256') and current[0]['integrity']=='snapshot_verified':
                current[0]['selected']=True;selection_status='matched'
            else:selection_status='missing_or_mismatch'
        except (OSError,ValueError,KeyError,TypeError):selection_status='missing_or_mismatch'
    if space_id:
        controls={r['artifact']:r for r in jobs.controls.saved(space_id)}
        for item in items:
            if item['kind'] not in ('input','candidate','publication','offline_package'):continue
            control=controls.get('publication:'+item['record_id'] if item['kind']=='offline_package' else item['key'])
            item['lifecycle_state']=control['lifecycle_state'] if control else 'active'
            item['lifecycle_revision']=control['revision'] if control else 0
            if item['lifecycle_state'] in ('paused','retired'):item['resources']={}
    return {'profile':'cospace.preview-artifact-catalog/0.1',**ownership,'observed_at':now(),
            'items':sorted(items,key=lambda item:(KINDS.index(item['kind']),item['record_id'])),
            'relations':sorted(relations,key=lambda r:(r['from'],r['relation'])),
            'counts':{kind:sum(item['kind']==kind for item in items) for kind in KINDS},
            'job_counts':job_counts,'selection_status':selection_status,
            'consistency':'request_time_file_reads_not_transactional',
            'source_files_rechecked':False,'consumer_state_checked':False,
            'quality':'unverified','robot_ready':False}
