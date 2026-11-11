"""Single-server local preview jobs, fixed sources, bounded subprocess execution."""
from contextlib import nullcontext
from datetime import datetime,timezone
import json
import re
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from packages.construction.preview_model import PreviewModel,digest
from packages.lifecycle.preview_scope import scope,match,owned
from packages.lifecycle.preview_control_lock import serialized
from packages.lifecycle.preview_control import PreviewControls


def now(): return datetime.now(timezone.utc).isoformat()


class PreviewJobs:
    def __init__(self,root,snapshot,tracking,inputs=None):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.snapshot=Path(snapshot); self.tracking=Path(tracking); self.lock=threading.Lock(); self.active={}
        self.inputs=inputs
        from packages.data.preview_batches import PreviewBatches
        self.batches=PreviewBatches(inputs) if inputs else None
        self.directory=getattr(inputs,"directory",None)
        for path in self.root.glob('*/job.json'):
            record=json.loads(path.read_bytes())
            if record['state'] in ['queued','running']:
                record.update(state='interrupted',finished_at=now(),error='preview_service_restarted')
                self.save(record)
        from packages.construction.preview_derivations import SplitBuilds
        self.split=SplitBuilds(self)

    def save(self,record):
        path=self.root/record['id']/'job.json'; temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(record,indent=2),encoding='utf-8'); temp.replace(path)

    def poll(self):
        for identity,(process,started,log) in list(self.active.items()):
            code=process.poll()
            if code is None and time.monotonic()-started>120:
                process.kill(); code=process.wait(); error='build_timeout'
            else: error='build_failed'
            if code is None: continue
            log.close(); record=json.loads((self.root/identity/'job.json').read_bytes())
            try:
                if code!=0: raise ValueError(error)
                if record.get('pipeline')=='model_then_views/0.1':
                    self.split.begin(record);del self.active[identity];continue
                model=PreviewModel(self.root/identity/'output')
                match(model.manifest,owned(record))
                if record.get('batch_ref')!=model.manifest.get('source',{}).get('batch_ref'):raise ValueError('candidate_batch_binding_mismatch')
                if record.get('input_binding') != model.manifest.get('source',{}).get('input_binding'):
                    raise ValueError('candidate_input_binding_mismatch')
                from packages.construction.build_admission import match_source
                match_source(record,model.manifest.get('source',{}))
                record.update(state='succeeded',model_id=model.manifest['id'],
                              candidate_url=f'/candidates/{identity}/',error=None)
            except (ValueError,OSError,KeyError) as exc: record.update(state='failed',error=str(exc))
            record['finished_at']=now(); self.save(record); del self.active[identity]
        self.split.poll()

    @property
    def controls(self):return PreviewControls(self.root.parent,self.directory)

    @serialized(lambda self:self.root.parent)
    def list(self):
        with self.lock:
            self.poll()
            return sorted([json.loads(p.read_bytes()) for p in self.root.glob('*/job.json')],
                          key=lambda r:r['created_at'],reverse=True)

    @serialized(lambda self:self.root.parent)
    def start(self,input_id=None,space_id=None,batch_id=None,batch_revision=None,*,retry_ref=None,input_revision=None,build_info=None):
        if build_info is not None:
            if not isinstance(build_info,dict) or set(build_info)-{'name','purpose','changes'}:raise ValueError('build_info_invalid')
            if any(not isinstance(v,str) or len(v)>({'name':100,'purpose':500,'changes':500}[k]) for k,v in build_info.items()):raise ValueError('build_info_invalid')
            build_info={k:v.strip() for k,v in build_info.items()}
        ownership=scope(self.directory,space_id)
        with self.lock:
            self.poll()
            if self.active or self.split.active: raise ValueError('build_already_running')
            registered=None; admission_preflight=None
            if self.inputs is not None:
                if not input_id: raise ValueError('input_selection_required')
                registered=self.inputs.read(input_id)
                match(registered,ownership)
                self.controls.require_active(space_id,'input:'+input_id)
                registered=self.inputs.resolve(input_id)
                current=registered.get('coordinate_revision',{}).get('revision',0)
                if input_revision is not None and input_revision!=current:raise ValueError('coordinate_revision_changed')
                if current:
                    if input_revision is None:raise ValueError('input_revision_confirmation_required')
                    from packages.data.preflight_records import PreflightRecords
                    check=PreflightRecords(self.inputs).latest(input_id)
                    if not check or not check['registration_matches'] or check['status']!='passed':raise ValueError('input_revision_preflight_required')
                admission_preflight=check['sequence'] if current else None
                snapshot=Path(registered['snapshot']); tracking=Path(registered['tracking']) if registered.get('tracking') else None
            else:
                if input_id is not None: raise ValueError('input_catalog_not_configured')
                if ownership: raise ValueError('input_catalog_not_configured')
                snapshot=self.snapshot; tracking=self.tracking
            if self.batches is None and (batch_id is not None or batch_revision is not None):raise ValueError('batches_not_configured')
            guard=self.batches.admit(registered,ownership,batch_id,batch_revision) if self.batches else nullcontext(None)
            with guard as batch_ref:return self._launch(registered,snapshot,tracking,ownership,input_id,batch_ref,retry_ref,admission_preflight,build_info)

    @serialized(lambda self:self.root.parent)
    def update_info(self,space_id,identity,build_info,expected_revision):
        if not re.fullmatch(r'build-[A-Za-z0-9-]+',identity):raise ValueError('build_not_found')
        ownership=scope(self.directory,space_id)
        if not isinstance(build_info,dict) or set(build_info)-{'name','purpose','changes'}:raise ValueError('build_info_invalid')
        if any(not isinstance(v,str) or len(v)>({'name':100,'purpose':500,'changes':500}[k]) for k,v in build_info.items()):raise ValueError('build_info_invalid')
        with self.lock:
            record=json.loads((self.root/identity/'job.json').read_bytes());match(record,ownership)
            if type(expected_revision) is not int or expected_revision!=record.get('build_info_revision',0):raise ValueError('build_info_revision_changed')
            value={k:v.strip() for k,v in build_info.items()}
            record.setdefault('build_info_history',[]).append({'revision':expected_revision+1,'changed_at':now(),'before':record.get('build_info',{}),'after':value})
            record.update(build_info=value,build_info_revision=expected_revision+1)
            self.save(record)
            return {'job_id':identity,'space_id':space_id,'build_info':value,'revision':record['build_info_revision']}

    @serialized(lambda self:self.root.parent)
    def retry(self,space_id,previous_id,request_id):
        ownership=scope(self.directory,space_id)
        if not space_id or not re.fullmatch(r'build-[A-Za-z0-9-]+',previous_id):raise ValueError('retry_job_not_found')
        if not re.fullmatch(r'[a-f0-9]{32}',request_id):raise ValueError('retry_request_invalid')
        records=self.list()
        previous=next((r for r in records if r['id']==previous_id),None)
        if previous is None:raise ValueError('retry_job_not_found')
        match(previous,ownership)
        # Replays return the admitted attempt, even after completion or a restart.
        # This lookup and launch share the runtime mutation lock.
        reused=next((r for r in records if r.get('retry_request_id')==request_id and owned(r)==ownership),None)
        if reused:
            if reused.get('retry_of')!=previous_id:raise ValueError('retry_request_conflict')
            return {'created':False,'job':reused}
        if previous.get('state') not in ('failed','interrupted'):raise ValueError('retry_requires_failed_or_interrupted')
        if previous.get('method') not in ('single_sensor_frame_no_registration','rebuild_from_frozen_rgbd_and_existing_poses','normalize_declared_pointcloud','laser_scan_to_scan_icp'):
            raise ValueError('retry_route_not_supported')
        if not self.inputs or not previous.get('input_id'):raise ValueError('retry_input_unavailable')
        registered=self.inputs.read(previous['input_id']);match(registered,ownership)
        binding={k:v for k,v in registered.items() if k not in ('snapshot','tracking')}
        if binding!=previous.get('input_binding'):raise ValueError('retry_input_binding_changed')
        batch=previous.get('batch_ref') or {}
        job=self.start(previous['input_id'],space_id,batch.get('batch_id'),batch.get('admitted_revision'),
                       retry_ref={'retry_of':previous_id,'retry_request_id':request_id},input_revision=registered.get('coordinate_revision',{}).get('revision',0))
        return {'created':True,'job':job}

    def _process_declaration(self,record,registered,snapshot,ownership):
        if registered is None or registered['format']!='nyu_rgbd_with_existing_poses':return
        pairs=[p for p in json.loads((snapshot/'report.json').read_bytes())['pairs'] if p['accepted']]
        stamps=[p.get('depth_time_us') for p in pairs]
        if ownership and stamps and all(type(t) is int and 0<=t<=2**53-1 for t in stamps) and all(a<b for a,b in zip(stamps,stamps[1:])):
            record['process_profile']='cospace.build-process/0.1'
        else:record['process_unsupported_reason']='source_frame_time_unavailable'

    def _launch_command(self,record,registered,snapshot,tracking):
        modules={'ros1_lidar_multiframe_icp':'build_lidar_mapping_preview','ply_pointcloud':'build_pointcloud_flow_preview',
                 'ros1_lidar_single_frame':'build_lidar_flow_preview'}
        input_format=registered['format'] if registered else 'nyu_rgbd_with_existing_poses'
        directory=self.root/record['id']
        command=[sys.executable,'-m','experiments.scripts.'+modules.get(input_format,'build_nyu_flow_preview'),
                 '--snapshot',str(snapshot),'--output',str(directory/('frozen' if registered else 'output')),
                 '--candidate-id',record['id']]
        if input_format=='nyu_rgbd_with_existing_poses':command+=['--tracking',str(tracking)]
        if registered:command+=['--input-binding',str(directory/'job.json'),'--freeze-only']
        return command

    def _require_input_files(self,lidar,pointcloud,snapshot,tracking):
        if not lidar and not pointcloud and (not (snapshot/'report.json').is_file() or tracking is None or not tracking.is_file()):
            raise ValueError('configured_input_missing')

    def _launch(self,registered,snapshot,tracking,ownership,input_id,batch_ref,retry_ref=None,admission_preflight=None,build_info=None):
        mapping=registered is not None and registered['format']=='ros1_lidar_multiframe_icp'
        lidar=registered is not None and registered['format'] in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp')
        pointcloud=registered is not None and registered['format']=='ply_pointcloud'
        self._require_input_files(lidar,pointcloud,snapshot,tracking)
        identity='build-'+uuid.uuid4().hex[:16]; directory=self.root/identity; directory.mkdir()
        record={'id':identity,'state':'queued','created_at':now(),'input_id':input_id or 'nyu-office-short',
                'method':{'ros1_lidar_multiframe_icp':'laser_scan_to_scan_icp','ply_pointcloud':'normalize_declared_pointcloud','ros1_lidar_single_frame':'single_sensor_frame_no_registration'}.get(registered['format'] if registered else '', 'rebuild_from_frozen_rgbd_and_existing_poses'),'stage':'candidate_and_dual_views',
                'candidate_url':None,'error':None,**ownership}
        if registered:
            record['input_binding']={k:v for k,v in registered.items() if k not in ('snapshot','tracking')}
        if registered and pointcloud:
            from packages.construction.build_admission import receipt
            record['build_admission']=receipt(identity,record['input_binding'],admission_preflight)
        if build_info is not None:record['build_info']=build_info
        if batch_ref:record['batch_ref']=batch_ref
        if retry_ref:record.update(retry_ref)
        if registered:record.update(pipeline='model_then_views/0.1',stage='building_model')
        if mapping:record['process_profile']='cospace.lidar-build-process/0.1'
        self._process_declaration(record,registered,snapshot,ownership)
        self.save(record); log=(directory/'build.log').open('wb')
        try:
            command=self._launch_command(record,registered,snapshot,tracking)
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError as exc:
            log.close(); record.update(state='failed',error=str(exc),finished_at=now()); self.save(record); return record
        record.update(state='running',started_at=now()); self.save(record)
        self.active[identity]=(process,time.monotonic(),log)
        return record

    @serialized(lambda self:self.root.parent)
    def stages(self,space_id,identity):
        ownership=scope(self.directory,space_id)
        if not re.fullmatch(r'build-[A-Za-z0-9-]+',identity):raise ValueError('build_not_found')
        record=next((r for r in self.list() if r['id']==identity),None)
        if record is None:raise ValueError('build_not_found')
        match(record,ownership)
        result=self.split.snapshot(record)
        return result or {'profile':'cospace.build-stages/0.1','job_id':identity,'frozen_model':None,'views':{},
            'candidate_ready':record['state']=='succeeded','legacy':not bool(record.get('pipeline')),**ownership}

    @serialized(lambda self:self.root.parent)
    def derive_view(self,space_id,previous_id,kind,request_id):
        ownership=scope(self.directory,space_id)
        if not space_id or not re.fullmatch(r'build-[A-Za-z0-9-]+',previous_id):raise ValueError('build_not_found')
        if kind not in ('human','agent') or not re.fullmatch(r'[a-f0-9]{32}',request_id):raise ValueError('view_request_invalid')
        records=self.list();previous=next((r for r in records if r['id']==previous_id),None)
        if previous is None:raise ValueError('build_not_found')
        match(previous,ownership)
        reused=next((r for r in records if r.get('view_request_id')==request_id and owned(r)==ownership),None)
        if reused:
            if reused.get('view_parent_id')!=previous_id or reused.get('rerun_view')!=kind:raise ValueError('view_request_conflict')
            return {'created':False,'job':reused}
        if previous['state'] not in ('succeeded','views_failed','interrupted'):raise ValueError('view_parent_not_ready')
        if not previous.get('frozen_model') or set(previous.get('view_tasks',{}))!={'human','agent'}:raise ValueError('frozen_model_not_available')
        self.controls.require_active(space_id,'candidate:'+previous_id)
        frozen_record,_=self.split.frozen(previous['frozen_model']);match(frozen_record['metadata'],ownership)
        self.controls.require_active(space_id,'candidate:'+previous['frozen_model']['job_id'])
        if self.active or self.split.active:raise ValueError('build_already_running')
        other='agent' if kind=='human' else 'human'
        # An incomplete counterpart may be kept for a second explicit rerun, but
        # a supposedly successful counterpart must pass integrity now.
        _,counterpart=self.split.task(previous['view_tasks'][other])
        if counterpart['frozen_model']!=previous['frozen_model'] or counterpart['view_kind']!=other:raise ValueError('view_model_mismatch')
        if counterpart['state']=='succeeded':self.split.manifest(previous['view_tasks'][other],previous['frozen_model'],other)
        identity='build-'+uuid.uuid4().hex[:16];(self.root/identity).mkdir()
        job={k:previous[k] for k in ('input_id','input_binding','batch_ref','build_admission') if k in previous}
        job.update(id=identity,state='running',created_at=now(),method='derive_frozen_views',pipeline='model_then_views/0.1',
            stage='deriving_views',candidate_url=None,error=None,frozen_model=previous['frozen_model'],
            view_tasks=dict(previous['view_tasks']),view_parent_id=previous_id,rerun_view=kind,view_request_id=request_id,**ownership)
        self.save(job)
        job['view_tasks'][kind]=self.split.launch(job,kind);self.save(job)
        return {'created':True,'job':job}

    def model(self,identity):
        records={r['id']:r for r in self.list()}
        if identity not in records or records[identity]['state']!='succeeded': raise ValueError('candidate_not_available')
        model=PreviewModel(self.root/identity/'output')
        match(model.manifest,owned(records[identity]))
        if records[identity].get('batch_ref')!=model.manifest.get('source',{}).get('batch_ref'):raise ValueError('candidate_batch_binding_mismatch')
        if owned(records[identity]):
            match(model.manifest.get('source',{}).get('input_binding',{}),owned(records[identity]))
        if records[identity].get('input_binding') is not None:
            if records[identity]['input_binding'] != model.manifest.get('source',{}).get('input_binding'):
                raise ValueError('candidate_input_binding_mismatch')
        from packages.construction.build_admission import match_source
        match_source(records[identity],model.manifest.get('source',{}))
        if records[identity].get('pipeline')=='model_then_views/0.1':
            declaration=model.manifest.get('derivation',{})
            if (declaration.get('frozen_model')!=records[identity].get('frozen_model') or
                any(declaration.get('views',{}).get(kind,{}).get('id')!=ref['task_id'] for kind,ref in records[identity].get('view_tasks',{}).items())):
                raise ValueError('candidate_view_task_binding_mismatch')
        return model

    def selection_path(self,space_id=None):
        scope(self.directory,space_id)
        if space_id is None: return self.root/'selection.json'
        parent=self.root/'space-selections'; parent.mkdir(exist_ok=True)
        return parent/(space_id+'.json')

    def selection(self,space_id=None):
        with self.lock:
            path=self.selection_path(space_id)
            record=json.loads(path.read_bytes()) if path.exists() else {'revision':0,'candidate_id':None}
            if path.exists(): match(record,scope(self.directory,space_id))
            return record

    @serialized(lambda self:self.root.parent)
    def select(self,identity,expected_revision,space_id=None,*,review=None):
        ownership=scope(self.directory,space_id)
        model=self.model(identity)
        match(model.manifest,ownership)
        self.controls.require_active(space_id,'candidate:'+identity)
        with self.lock:
            path=self.selection_path(space_id)
            previous=json.loads(path.read_bytes()) if path.exists() else {'revision':0,'candidate_id':None}
            if path.exists(): match(previous,ownership)
            if previous['revision']!=expected_revision: raise ValueError('selection_changed_refresh_required')
            if review is not None:
                from packages.construction.preview_changes import validate_review
                validate_review(self,previous,model,ownership,review)
            record={'revision':previous['revision']+1,'candidate_id':identity,'selected_at':now(),
                    'previous_candidate_id':previous['candidate_id'],
                    'model_manifest_sha256':digest(model.root/'model.json'),
                    'candidate_url':f'/candidates/{identity}/','purpose':'workspace_preview_only',**ownership}
            if review is not None:
                record['selection_review']={**review,'reviewed_at':now(),'purpose':'preview_candidate_selection_not_quality_acceptance'}
            # Append selection evidence before making the new pointer visible.
            history=self.root/'selections'; history.mkdir(exist_ok=True)
            raw=json.dumps(record,indent=2)
            (history/f'{record["revision"]}-{uuid.uuid4().hex}.json').write_text(raw,encoding='utf-8')
            temp=path.with_suffix('.tmp'); temp.write_text(raw,encoding='utf-8'); temp.replace(path)
            return record
