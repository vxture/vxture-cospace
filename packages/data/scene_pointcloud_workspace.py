"""Explicit scene bindings, immutable display tiles and bounded region intake jobs."""
import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.data.scene_pointcloud_intake import digest
from packages.data.scene_pointcloud_region import SceneRegions, RegionBudgetExceeded
from packages.data.scene_pointcloud_tiles import PROFILE, MAX_TILE_POINTS


class SceneCloudUnavailable(ValueError): pass
class SceneCloudConflict(ValueError): pass
class SceneCloudAuthorizationPending(Exception): pass


class SceneBinding(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    root:str=Field(min_length=1)
    scene_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    tiles_root:str=Field(min_length=1)
    index_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class SceneCloudConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    profile:Literal['cospace.scene-pointcloud-bindings/0.1']
    bindings:list[SceneBinding]=Field(max_length=1000)


class ComposeRegion(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    request_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    index_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    sources:list[str]=Field(min_length=1,max_length=32)
    bounds:list[list[float]]=Field(min_length=2,max_length=2)
    voxel_size:float=Field(ge=0,le=100)
    label:str=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def valid(self):
        if (len(set(self.sources))!=len(self.sources) or not self.label.strip()
                or any(len(row)!=3 for row in self.bounds)
                or any(abs(v)>1_000_000 for row in self.bounds for v in row)
                or any(self.bounds[0][i]>=self.bounds[1][i] for i in range(3))
                or 0<self.voxel_size<.001):
            raise ValueError('invalid_region')
        return self


def bounded_json(path,limit=4_000_000):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise SceneCloudUnavailable('scene_cloud_manifest_budget')
    return raw,json.loads(raw)


class ScenePointcloudWorkspace:
    def __init__(self,catalog,config=None):
        self.catalog,self.config=catalog,Path(config) if config else None
        self.root=catalog.root/'scene-compositions'
        self.lock=threading.RLock();self.active=None

    def binding(self,space):
        self.catalog.directory.read('space',space)
        if self.config is None:return None
        _,value=bounded_json(self.config,1_000_000)
        config=SceneCloudConfig.model_validate(value)
        if len({b.space_id for b in config.bindings})!=len(config.bindings):
            raise SceneCloudUnavailable('scene_cloud_duplicate_binding')
        return next((b for b in config.bindings if b.space_id==space),None)

    def index(self,space,expected=None):
        binding=self.binding(space)
        if binding is None:return None,None
        if expected is not None and expected!=binding.index_sha256:raise SceneCloudConflict('scene_cloud_index_changed')
        root=Path(binding.tiles_root).resolve()
        raw,value=bounded_json(root/'index.json')
        if (hashlib.sha256(raw).hexdigest()!=binding.index_sha256 or value['profile']!=PROFILE
                or value['scene_manifest_sha256']!=binding.scene_sha256
                or len(value['tiles'])>10_000 or not 1<=len(value['sources'])<=32
                or digest(Path(binding.root)/'scene.json')!=binding.scene_sha256):
            raise SceneCloudUnavailable('scene_cloud_evidence_changed')
        # Metadata is trusted only with its configured digest. No path is accepted from a browser.
        return binding,value

    def directory(self,space):
        binding,value=self.index(space)
        if binding is None:return dict(configured=False,space_id=space,profile='cospace.scene-pointcloud-workspace/0.1')
        return value|dict(configured=True,space_id=space,index_sha256=binding.index_sha256,
                          profile='cospace.scene-pointcloud-workspace/0.1',
                          display_point_budget=150_000,cache_point_budget=300_000,max_visible_tiles=96)

    def tile(self,space,identity,level,expected):
        if not re.fullmatch(r't[0-9]{5}',identity) or type(level) is not int or level not in (0,1,2):
            raise SceneCloudUnavailable('scene_cloud_tile_unknown')
        binding,value=self.index(space,expected)
        if binding is None:raise SceneCloudUnavailable('scene_cloud_not_configured')
        tile=next((t for t in value['tiles'] if t['id']==identity),None)
        if tile is None:raise SceneCloudUnavailable('scene_cloud_tile_unknown')
        lod=next(l for l in tile['lods'] if l['level']==level)
        if not 1<=lod['points']<=MAX_TILE_POINTS or lod['bytes']!=15*lod['points']:
            raise SceneCloudUnavailable('scene_cloud_tile_layout')
        path=Path(binding.tiles_root)/f'{identity}-{level}.bin'
        with path.open('rb') as stream:raw=stream.read(MAX_TILE_POINTS*15+1)
        if len(raw)!=lod['bytes'] or hashlib.sha256(raw).hexdigest()!=lod['sha256']:
            raise SceneCloudUnavailable('scene_cloud_tile_changed')
        return raw

    def _save(self,path,value):
        pending=path.with_suffix('.pending')
        pending.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        pending.replace(path)

    def status(self,space,identity):
        if not re.fullmatch(r'compose-[a-f0-9]{24}',identity):raise SceneCloudUnavailable('scene_cloud_job_unknown')
        with self.lock:
            path=self.root/identity/'job.json'
            _,value=bounded_json(path,64_000)
            if value['space_id']!=space:raise PermissionError('composition_not_in_space')
            if value['state'] in ('queued','running') and self.active!=identity:
                value.update(state='interrupted',issue='service_restarted_submit_new_request')
                self._save(path,value)
            return value

    def start(self,request,actor,reauthorize):
        binding,value=self.index(request.space_id,request.index_sha256)
        if binding is None:raise SceneCloudUnavailable('scene_cloud_not_configured')
        if any(n not in {s['name'] for s in value['sources']} for n in request.sources):
            raise SceneCloudConflict('scene_cloud_source_unknown')
        body=request.model_dump()
        identity='compose-'+hashlib.sha256((request.space_id+request.request_id).encode()).hexdigest()[:24]
        with self.lock:
            path=self.root/identity/'job.json'
            if path.exists():
                old=self.status(request.space_id,identity)
                if old['request']!=body:raise SceneCloudConflict('scene_cloud_request_reused')
                return old
            if self.active is not None:raise SceneCloudConflict('scene_cloud_worker_busy')
            path.parent.mkdir(parents=True)
            job=dict(id=identity,space_id=request.space_id,state='queued',request=body,actor=actor,
                     scene_manifest_sha256=binding.scene_sha256,input_id=None,issue=None)
            self._save(path,job);self.active=identity
            thread=threading.Thread(target=self._work,args=(path,job,binding,request,reauthorize),daemon=True)
            thread.start()
            return dict(job)

    def _work(self,path,job,binding,request,reauthorize):
        try:
            with self.lock:job.update(state='running');self._save(path,job)
            result=SceneRegions(binding.root,binding.scene_sha256).prepare(path.parent/'derived',request.sources,
                        request.bounds,limit=250_000,voxel_size=request.voxel_size)
            from experiments.scripts.pack_input_upload import pack
            bundle=path.parent/'input.zip'
            pack(path.parent/'derived/snapshot',None,bundle,'ply_pointcloud')
            with self.lock:
                job.update(bundle_sha256=digest(bundle),matched_points=result['matched_points'],
                           retained_points=result['retained_points'],shards_loaded=result['shards_loaded'],
                           shards_skipped=result['shards_skipped'])
                self._save(path,job)
            # Long work does not retain an earlier permission/subscription decision.
            with self.lock:
                self._register(path,job,reauthorize)
        except SceneCloudAuthorizationPending:
            with self.lock:
                job.update(state='awaiting_authorization',issue='confirm_session_to_register')
                self._save(path,job)
        except Exception as exc:
            issue=('region_budget_exceeded' if isinstance(exc,RegionBudgetExceeded) else
                   'region_empty' if str(exc)=='empty_region' else
                   'authorization_changed' if isinstance(exc,PermissionError) else 'composition_failed_recheck_sources')
            with self.lock:job.update(state='failed',issue=issue);self._save(path,job)
        finally:
            with self.lock:self.active=None

    def _register(self,path,job,reauthorize):
        from packages.data.input_uploads import InputUploads
        reauthorize()
        request=ComposeRegion.model_validate(job['request'])
        binding,_=self.index(request.space_id,request.index_sha256)
        if binding is None or binding.scene_sha256!=job['scene_manifest_sha256']:
            raise SceneCloudConflict('scene_cloud_index_changed')
        bundle=path.parent/'input.zip'
        if digest(bundle)!=job['bundle_sha256']:raise SceneCloudUnavailable('scene_cloud_bundle_changed')
        registered=InputUploads(self.catalog).register(bundle,request.space_id,request.label,job['actor'])
        job.update(state='succeeded',input_id=registered['input']['id'],issue=None)
        self._save(path,job)

    def complete(self,space,identity,actor,reauthorize):
        # A fresh authorized POST resumes only registration, never the costly derivation.
        with self.lock:
            job=self.status(space,identity)
            if actor!=job['actor']:raise PermissionError('composition_actor_changed')
            if job['state']=='succeeded':return job
            if job['state']!='awaiting_authorization' or self.active==identity:
                raise SceneCloudConflict('scene_cloud_not_ready_to_register')
            self._register(self.root/identity/'job.json',job,reauthorize)
            return job
