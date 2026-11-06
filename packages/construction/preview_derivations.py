"""Frozen geometry and independently recorded preview views; no source reprocessing."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import numpy as np
from packages.construction.preview_model import digest,surface_cells
from packages.lifecycle.preview_scope import match,owned
from packages.data.nyu_rgbd import ply_bytes

PIPELINE='model_then_views/0.1'
def now():return datetime.now(timezone.utc).isoformat()
def write(path,record):
    path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def freeze(root,metadata):
    root=Path(root)
    record={'profile':'cospace.frozen-geometry/0.1','frozen_at':now(),'metadata':metadata,
            'members':{'spatial.npz':{'sha256':digest(root/'spatial.npz'),'bytes':(root/'spatial.npz').stat().st_size}}}
    write(root/'frozen.json',record)
    return record

def frozen(root,expected=None):
    root=Path(root);record=json.loads((root/'frozen.json').read_bytes());meta=record['metadata']
    if record.get('profile')!='cospace.frozen-geometry/0.1' or set(record['members'])!={'spatial.npz'}:raise ValueError('frozen_model_invalid')
    member=record['members']['spatial.npz']
    if digest(root/'spatial.npz')!=member['sha256'] or (root/'spatial.npz').stat().st_size!=member['bytes']:raise ValueError('frozen_model_integrity')
    ref={'job_id':meta['id'],'model_id':meta['id'],'manifest_sha256':digest(root/'frozen.json'),'source_model_sha256':member['sha256']}
    if expected is not None and ref!=expected:raise ValueError('frozen_model_binding_mismatch')
    return record,ref

def derive(root,output,task):
    record,ref=frozen(root,task['frozen_model']);meta=record['metadata'];match(task,owned(meta))
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    with np.load(Path(root)/'spatial.npz',allow_pickle=False) as arrays:points=arrays['points'];colors=arrays['colors']
    if points.ndim!=2 or points.shape[1]!=3 or not len(points) or not np.isfinite(points).all() or colors.shape!=points.shape:raise ValueError('frozen_arrays_invalid')
    kind=task['view_kind'];params=task['parameters']
    if kind=='human' and params=={'format':'ply'}:
        name='human.ply';(output/name).write_bytes(ply_bytes(points,colors,np.ones(len(points),bool)));details={'path':name}
        if meta.get('appearance'):details['appearance']=meta['appearance']
        if meta.get('data_kind')=='real_lidar_sensor_local_candidate':details['appearance']='intensity_grayscale_not_rgb'
    elif kind=='agent' and params=={'resolution_m':.1}:
        name='agent.npz';cells=surface_cells(points,.1);np.savez_compressed(output/name,cells=cells)
        details={'path':name,'resolution_m':.1,'surface_cells':len(cells),'unlisted_state':'unknown'}
    else:raise ValueError('view_parameters_unsupported')
    result={'profile':'cospace.derived-view/0.1','id':task['id'],'view_kind':kind,'frozen_model':ref,
            'source_model_sha256':ref['source_model_sha256'],'frame_id':meta['frame_id'],'unit':meta['unit'],
            'parameters':params,'created_at':now(),'view':details,**owned(meta),
            'members':{name:{'sha256':digest(output/name),'bytes':(output/name).stat().st_size}}}
    write(output/'view.json',result)

def validate_composition(manifest):
    declaration=manifest.get('derivation')
    if declaration is None:return
    if declaration.get('profile')!='cospace.model-view-composition/0.1':raise ValueError('view_composition_invalid')
    ref=declaration['frozen_model']
    if ref['source_model_sha256']!=manifest['members']['spatial.npz']['sha256']:raise ValueError('view_composition_model_mismatch')
    if set(declaration['views'])!={'human','agent'}:raise ValueError('view_composition_incomplete')
    for kind in ('human','agent'):
        view=declaration['views'][kind];member=manifest[kind+'_view'];path=member['path']
        match(view,owned(manifest))
        if (view.get('profile')!='cospace.derived-view/0.1' or view.get('view_kind')!=kind or view.get('frozen_model')!=ref
            or view.get('source_model_sha256')!=ref['source_model_sha256'] or view.get('frame_id')!=manifest['frame_id']
            or view.get('unit')!=manifest['unit'] or view.get('view')!={k:v for k,v in member.items() if k not in ('source_model_sha256','objects_path','ontology_ref')}
            or view.get('members')!={path:manifest['members'][path]}):raise ValueError('view_composition_binding_mismatch')


class SplitBuilds:
    def __init__(self,jobs):
        self.jobs=jobs;self.root=jobs.root;self.active={}
        for path in self.root.glob('*/views/view-*/task.json'):
            task=json.loads(path.read_bytes())
            if task['state'] in ('queued','running'):
                task.update(state='interrupted',error='preview_service_restarted',finished_at=now());write(path,task)

    def frozen(self,ref):
        if not re.fullmatch(r'build-[A-Za-z0-9-]+',ref.get('job_id','')):raise ValueError('frozen_model_not_found')
        return frozen(self.root/ref['job_id']/'frozen',ref)

    def task(self,ref):
        if not isinstance(ref,dict) or not re.fullmatch(r'build-[A-Za-z0-9-]+',ref.get('job_id','')) or not re.fullmatch(r'view-[a-f0-9]{16}',ref.get('task_id','')):raise ValueError('view_task_not_found')
        path=self.root/ref['job_id']/'views'/ref['task_id']/'task.json';task=json.loads(path.read_bytes())
        if task.get('id')!=ref['task_id'] or task.get('job_id')!=ref['job_id']:raise ValueError('view_task_binding_mismatch')
        return path,task

    def manifest(self,task_ref,frozen_ref,kind):
        path,task=self.task(task_ref)
        if task['state']!='succeeded' or task['frozen_model']!=frozen_ref or task['view_kind']!=kind:raise ValueError('view_task_not_ready')
        root=path.parent/'output';view=json.loads((root/'view.json').read_bytes())
        if digest(root/'view.json')!=task.get('view_manifest_sha256') or view['id']!=task['id']:raise ValueError('view_manifest_integrity')
        for name,member in view['members'].items():
            if Path(name).name!=name or digest(root/name)!=member['sha256'] or (root/name).stat().st_size!=member['bytes']:raise ValueError('view_artifact_integrity')
        if view['frozen_model']!=frozen_ref or view['view_kind']!=kind:raise ValueError('view_model_mismatch')
        return root,view

    def launch(self,job,kind):
        identity='view-'+uuid.uuid4().hex[:16];root=self.root/job['id']/'views'/identity;root.mkdir(parents=True)
        task={'profile':'cospace.view-task/0.1','id':identity,'job_id':job['id'],'view_kind':kind,
              'frozen_model':job['frozen_model'],'parameters':{'format':'ply'} if kind=='human' else {'resolution_m':.1},
              'state':'queued','created_at':now(),'error':None,**owned(job)}
        write(root/'task.json',task);log=(root/'view.log').open('wb')
        try:
            process=subprocess.Popen([sys.executable,'-m','experiments.scripts.derive_frozen_preview',
                '--frozen',str(self.root/task['frozen_model']['job_id']/'frozen'),'--task',str(root/'task.json'),'--output',str(root/'output')],
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            task.update(state='running',started_at=now());self.active[identity]=(process,time.monotonic(),log,root/'task.json')
        except OSError:
            log.close();task.update(state='failed',error='view_launch_failed',finished_at=now())
        write(root/'task.json',task)
        return {'job_id':job['id'],'task_id':identity}

    def begin(self,record):
        saved,ref=frozen(self.root/record['id']/'frozen');match(saved['metadata'],owned(record))
        if saved['metadata'].get('source',{}).get('input_binding')!=record.get('input_binding') or saved['metadata'].get('source',{}).get('batch_ref')!=record.get('batch_ref'):raise ValueError('frozen_input_binding_mismatch')
        record.update(frozen_model=ref,stage='deriving_views',view_tasks={})
        for kind in ('human','agent'):record['view_tasks'][kind]=self.launch(record,kind)
        self.jobs.save(record)

    def poll(self):
        for identity,(process,started,log,path) in list(self.active.items()):
            code=process.poll()
            if code is None and time.monotonic()-started>120:process.kill();code=process.wait()
            if code is None:continue
            log.close();task=json.loads(path.read_bytes())
            try:
                if code!=0:raise ValueError('view_build_failed')
                view=json.loads((path.parent/'output/view.json').read_bytes())
                if view['id']!=identity or view['view_kind']!=task['view_kind'] or view['frozen_model']!=task['frozen_model']:raise ValueError('view_result_binding_mismatch')
                match(view,owned(task));self.frozen(task['frozen_model'])
                task.update(state='succeeded',error=None,view_manifest_sha256=digest(path.parent/'output/view.json'))
                write(path,task);self.manifest({'job_id':task['job_id'],'task_id':identity},task['frozen_model'],task['view_kind'])
            except (OSError,ValueError,KeyError,TypeError):task.update(state='failed',error='view_result_invalid' if code==0 else 'view_build_failed')
            task['finished_at']=now();write(path,task);del self.active[identity]
        for path in self.root.glob('*/job.json'):
            job=json.loads(path.read_bytes())
            if job.get('pipeline')!=PIPELINE or job.get('stage')!='deriving_views' or job['state']!='running':continue
            tasks=[self.task(job['view_tasks'][kind])[1] for kind in ('human','agent')]
            if any(t['state'] in ('queued','running') for t in tasks):continue
            try:
                if any(t['state']!='succeeded' for t in tasks):raise ValueError('one_or_more_views_failed')
                self.compose(job);job.update(state='succeeded',stage='candidate_ready',candidate_url=f'/candidates/{job["id"]}/',error=None,model_id=job['id'])
            except (ValueError,OSError,KeyError,TypeError) as exc:job.update(state='views_failed',error=str(exc))
            job['finished_at']=now();self.jobs.save(job)

    def compose(self,job):
        saved,_=self.frozen(job['frozen_model']);meta=saved['metadata'];match(meta,owned(job))
        views={kind:self.manifest(job['view_tasks'][kind],job['frozen_model'],kind) for kind in ('human','agent')}
        root=self.root/job['id'];staging=root/('.output-'+uuid.uuid4().hex);staging.mkdir()
        try:
            shutil.copyfile(self.root/job['frozen_model']['job_id']/'frozen/spatial.npz',staging/'spatial.npz')
            for directory,view in views.values():
                for name in view['members']:shutil.copyfile(directory/name,staging/name)
            with np.load(staging/'spatial.npz',allow_pickle=False) as arrays:points=arrays['points'];colors=arrays['colors']
            with np.load(staging/'agent.npz',allow_pickle=False) as arrays:cells=arrays['cells']
            sample=np.arange(0,len(points),max(1,int(np.ceil(len(points)/35000))))
            display={'points':np.round(points[sample].astype(float),4).tolist(),'colors':colors[sample].tolist(),'agent_points':np.round((cells+.5)*.1,4).tolist()}
            (staging/'views.js').write_text('window.PREVIEW_VIEWS='+json.dumps(display,separators=(',',':'))+';',encoding='utf-8')
            manifest={**meta,'profile':'cospace.real-model-preview/0.1','id':job['id'],'created_at':now(),
                'events':[{'stage':s,'state':'completed'} for s in ('source_verified','candidate_built','human_view_derived','agent_view_derived')],
                'derivation':{'profile':'cospace.model-view-composition/0.1','frozen_model':job['frozen_model'],'views':{k:v[1] for k,v in views.items()}},
                'members':{name:{'sha256':digest(staging/name),'bytes':(staging/name).stat().st_size} for name in ('spatial.npz','human.ply','agent.npz','views.js')}}
            for kind,(_,view) in views.items():manifest[kind+'_view']={**view['view'],'source_model_sha256':job['frozen_model']['source_model_sha256']}
            write(staging/'model.json',manifest);shutil.copyfile('experiments/templates/nyu-flow-preview.html',staging/'index.html')
            from packages.construction.preview_model import PreviewModel
            PreviewModel(staging);staging.rename(root/'output')
        finally:
            if staging.exists():shutil.rmtree(staging)

    def snapshot(self,job):
        if not job.get('frozen_model'):return None
        saved,_=self.frozen(job['frozen_model']);match(saved['metadata'],owned(job))
        views={k:self.task(v)[1] for k,v in job.get('view_tasks',{}).items()}
        for kind,task in views.items():
            match(task,owned(job))
            if task['view_kind']!=kind or task['frozen_model']!=job['frozen_model']:raise ValueError('view_model_mismatch')
        return {'profile':'cospace.build-stages/0.1','job_id':job['id'],'frozen_model':job['frozen_model'],
                'metadata':saved['metadata'],'views':views,
                'candidate_ready':job['state']=='succeeded',**owned(job)}
