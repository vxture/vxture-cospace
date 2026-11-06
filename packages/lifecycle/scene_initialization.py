"""Trusted administrator scene bootstrap. No online creation authority is inferred.

An intent is durable before file writes; policy binding and completion receipt commit
together in the policy database. Unbound partial files are retained for explicit resume.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator
from packages.construction.preview_jobs import now
from packages.data.preview_inputs import PreviewInputs, inspect
from packages.data.preview_registration import PreviewRegistration
from packages.data.space_sources import SpaceSources, SourceChange
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.service.space_access import SpaceAccessPolicy


def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class WorkspaceScope(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    issuer:str=Field(min_length=1,max_length=2048)
    org_id:str=Field(min_length=1,max_length=160)
    workspace_id:str=Field(min_length=1,max_length=160)


class InitializationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    profile:str=Field(default='cospace.scene-initialization-request/0.1',pattern=r'^cospace\.scene-initialization-request/0\.1$')
    scope:WorkspaceScope
    preset_id:str=Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    manager_subjects:list[str]=Field(min_length=1,max_length=30)
    existing_space_id:str|None=Field(default=None,pattern=r'^space-[a-f0-9]{16}$')
    actor:str=Field(min_length=1,max_length=200)
    reason:str=Field(min_length=1,max_length=500)

    @field_validator('manager_subjects')
    @classmethod
    def members(cls,value):
        from packages.service.space_access import Grant
        if len(set(value))!=len(value):raise ValueError('duplicate_manager')
        for subject in value:
            Grant(issuer='validated-later',subject=subject,space_id='space-'+'0'*16,role='manager')
        return sorted(value)

    @field_validator('actor','reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('administrative_actor_and_reason_required')
        return value.strip()


class SceneInitialization:
    def __init__(self,runtime,policies,sources,presets):
        self.runtime=Path(runtime).resolve();self.policies=policies;self.sources=dict(sources)
        self.presets={p['id']:dict(p) for p in presets['presets']}
        if presets.get('profile')!='cospace.scene-presets/0.1' or len(self.presets)!=len(presets['presets']):raise ValueError('invalid_scene_presets')
        keys=[p['scene_key'] for p in self.presets.values()]
        if len(set(keys))!=len(keys):raise ValueError('duplicate_physical_scene_key')
        for p in self.presets.values():
            if (not p['scene_key'] or not 1<=len(p['name'])<=100 or len(p['description'])>500
                    or not p['source_ids'] or len(set(p['source_ids']))!=len(p['source_ids'])):raise ValueError('invalid_scene_preset')
        original=Path('var/nyu').resolve();auth=self.policies.path.parent
        if (self.runtime.is_relative_to(original) or original.is_relative_to(self.runtime)
                or auth.is_relative_to(original) or original.is_relative_to(auth)
                or auth.is_relative_to(self.runtime) or self.runtime.is_relative_to(auth)):
            raise ValueError('separate_initialization_runtime_required')

    def _load(self,identity):
        if not self.policies.path.exists():return None
        with closing(sqlite3.connect(self.policies.path.as_uri()+'?mode=ro',uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scene_initializations'").fetchone():return None
            row=db.execute('SELECT record FROM scene_initializations WHERE id=?',(identity,)).fetchone()
            return json.loads(row[0]) if row else None

    def _project_record(self,scope):
        if not self.policies.path.exists():return None
        with closing(sqlite3.connect(self.policies.path.as_uri()+'?mode=ro',uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='scene_initializations'").fetchone():return None
            for row in db.execute('SELECT record FROM scene_initializations'):
                record=json.loads(row[0])
                if record['scope']==scope and record['spec']['runtime']==str(self.runtime) and record['directory_records'].get('project'):
                    return record['directory_records']['project']
        return None

    @staticmethod
    def _table(db):
        db.execute('CREATE TABLE IF NOT EXISTS scene_initializations(id TEXT PRIMARY KEY,record TEXT NOT NULL)')

    def _journal(self,record):
        if not record['events'] or record['events'][-1]['state']!=record['state']:
            record['events'].append({'at':now(),'state':record['state']})
        with closing(sqlite3.connect(self.policies.path,timeout=10)) as db:
            with db:
                db.execute('BEGIN IMMEDIATE');self._table(db)
                db.execute('INSERT OR REPLACE INTO scene_initializations VALUES(?,?)',(record['id'],json.dumps(record,ensure_ascii=False)))

    def plan(self,request):
        """Read-only, including source validation; no directory or database creation."""
        if not isinstance(request,InitializationRequest):raise ValueError('typed_initialization_request_required')
        preset=self.presets.get(request.preset_id)
        if preset is None:raise ValueError('scene_preset_not_found')
        scope=request.scope.model_dump();identity='init-'+checksum(scope|{'scene_key':preset['scene_key']})[:32]
        spec={'request':request.model_dump(),'preset':preset,'runtime':str(self.runtime),'policy_store':str(self.policies.path)}
        source_store=SpaceSources(self.runtime/'preview-directory',self.sources)
        selected={key:self.sources[key] for key in preset['source_ids'] if key in self.sources}
        if len(selected)!=len(preset['source_ids']):raise ValueError('preset_source_not_available')
        spec['sources']={key:{'fingerprint':source_store.fingerprints[key],'label':value['label'],
            'checked':inspect(value['snapshot'],value.get('tracking'),value.get('format','nyu_rgbd_with_existing_poses'))} for key,value in selected.items()}
        saved=self._load(identity)
        if self.policies.path.exists():
            with closing(sqlite3.connect(self.policies.path.as_uri()+'?mode=ro',uri=True)) as db:
                has_policy=db.execute("SELECT 1 FROM sqlite_master WHERE name='policy'").fetchone()
                history_exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='history'").fetchone()
                # Only a journal we prepared on a previously empty store can resume without policy.
                empty_resume=(not has_policy and not history_exists and saved and saved['state']!='complete'
                              and saved.get('initial_policy_revision')==0)
            if empty_resume:revision,policy=0,SpaceAccessPolicy(bindings=[],grants=[])
            else:revision,policy=self.policies.load()
        else:revision,policy=0,SpaceAccessPolicy(bindings=[],grants=[])
        if saved and saved['spec_sha256']!=checksum(spec):raise ValueError('initialization_definition_changed')
        project_id='project-'+checksum(scope)[:16]
        space_id=request.existing_space_id or 'space-'+checksum(scope|{'scene_key':preset['scene_key']})[:16]
        directory=self.runtime/'preview-directory'
        if request.existing_space_id:
            path=directory/'space'/(space_id+'.json')
            if not path.is_file():raise ValueError('adopted_scene_not_found')
            adopted=json.loads(path.read_bytes())
            if adopted.get('id')!=space_id or adopted.get('profile')!='cospace.preview-space/0.1':raise ValueError('invalid_adopted_scene')
            project_id=adopted['project_id']
            if saved and saved.get('receipt') and saved['receipt']['project_id']!=project_id:
                raise ValueError('adopted_scene_project_changed_no_repair')
        expected_binding=scope|{'space_id':space_id}
        bindings=[b.model_dump() for b in policy.bindings if b.space_id==space_id]
        expected_grants=[{'issuer':scope['issuer'],'subject':s,'space_id':space_id,'role':'manager'} for s in request.manager_subjects]
        if (saved and saved['state']=='complete') or request.existing_space_id:
            if bindings!=[expected_binding] or any(g not in [v.model_dump() for v in policy.grants] for g in expected_grants):
                raise ValueError('initialization_binding_or_grant_changed_no_repair')
        elif bindings:raise ValueError('initialization_space_already_bound')
        snapshot={};project_record=self._project_record(scope)
        # Prevent second space for an already registered same sample in this workspace.
        for path in sorted((self.runtime/'preview-inputs').glob('input-*.json')):
            record=json.loads(path.read_bytes())
            if request.existing_space_id and record.get('space_id')==space_id:
                other_sources={key for p in self.presets.values() if p['scene_key']!=preset['scene_key'] for key in p['source_ids']}
                if any(key in self.sources and Path(record['snapshot']).resolve()==Path(self.sources[key]['snapshot']).resolve()
                       for key in other_sources):raise ValueError('adopted_scene_contains_other_sample')
            for key,value in selected.items():
                checked=spec['sources'][key]['checked']
                if (record.get('format')==value.get('format','nyu_rgbd_with_existing_poses')
                        and Path(record['snapshot']).resolve()==Path(value['snapshot']).resolve()
                        and all(record.get(k)==v for k,v in checked.items())):
                    foreign=next((b for b in policy.bindings if b.space_id==record.get('space_id') and b.model_dump(exclude={'space_id'})==scope),None)
                    if foreign and foreign.space_id!=space_id:raise ValueError('sample_scene_exists_explicit_adoption_required')
        for kind,identity_value in [('project',project_id),('space',space_id)]:
            path=directory/kind/(identity_value+'.json')
            if path.exists():
                raw=path.read_bytes();value=json.loads(raw);snapshot[str(path)]=hashlib.sha256(raw).hexdigest()
                if kind=='project' and request.existing_space_id:
                    if value.get('id')!=project_id or value.get('profile')!='cospace.preview-project/0.1':raise ValueError('invalid_adopted_project')
                elif kind=='space' and request.existing_space_id:
                    if value.get('id')!=space_id or value.get('profile')!='cospace.preview-space/0.1':raise ValueError('invalid_adopted_scene')
                    project_id=value['project_id']
                elif kind=='project' and project_record and value==project_record:pass
                elif not saved or value!=saved['directory_records'].get(kind):raise ValueError('initialization_directory_collision')
            elif saved and saved['state']=='complete':raise ValueError('initialized_directory_missing_no_repair')
        if request.existing_space_id:
            project_path=directory/'project'/(project_id+'.json');space_path=directory/'space'/(space_id+'.json')
            if not project_path.is_file() or not space_path.is_file():raise ValueError('adopted_scene_not_found')
            snapshot[str(project_path)]=hashlib.sha256(project_path.read_bytes()).hexdigest()
        settings=source_store.read(space_id)
        if (settings['revision'] or saved and saved['state']=='complete') and not set(selected)<=set(source_store.effective(settings)):
            raise ValueError('existing_source_settings_changed_no_repair')
        if saved and saved['state']=='complete':
            inputs=PreviewInputs.__new__(PreviewInputs);inputs.root=self.runtime/'preview-inputs';inputs.directory=None
            for entry in saved['inputs']:
                record=inputs.resolve(entry['id'])
                if checksum(record)!=entry['record_sha256']:raise ValueError('initialized_input_changed_no_repair')
        plan={'profile':'cospace.scene-initialization-plan/0.1','id':identity,'scope':scope,'preset_id':preset['id'],
            'scene_key':preset['scene_key'],'space_id':space_id,'project_id':project_id,'state':saved['state'] if saved else 'not_started',
            'policy_revision':revision,'spec_sha256':checksum(spec),'spec':spec,'directory_snapshot':snapshot,
            'source_settings':settings,'inputs':saved.get('inputs',[]) if saved else [],'mode':'trusted_administrator_only',
            'quality':'unverified','production_ready':False,'robot_ready':False}
        return plan|{'plan_sha256':checksum(plan)}

    def apply(self,request,expected_revision,expected_plan_sha256):
        # Offline administrative operation; browsers never reach this class.
        with mutation_guard(self.policies.path.parent),mutation_guard(self.runtime):
            plan=self.plan(request)
            if type(expected_revision) is not int or plan['policy_revision']!=expected_revision:raise ValueError('policy_revision_changed')
            if plan['plan_sha256']!=expected_plan_sha256:raise ValueError('initialization_plan_changed')
            saved=self._load(plan['id'])
            if saved and saved['state']=='complete':return {'created':False,**saved['receipt']}
            try:
                if saved is None:
                    timestamp=now();preset=plan['spec']['preset'];records={}
                    if not request.existing_space_id:
                        records={'project':self._project_record(plan['scope']) or {'profile':'cospace.preview-project/0.1','id':plan['project_id'],'name':'Workspace 场景目录','created_at':timestamp},
                            'space':{'profile':'cospace.preview-space/0.1','id':plan['space_id'],'name':preset['name'],'description':preset['description'],
                                'created_at':timestamp,'project_id':plan['project_id'],'publication_id':None,'state':'no_publication'}}
                    saved={'profile':'cospace.scene-initialization/0.1','id':plan['id'],'spec_sha256':plan['spec_sha256'],
                        'state':'prepared','scope':plan['scope'],'space_id':plan['space_id'],'directory_records':records,
                        'initial_policy_revision':expected_revision,
                        'spec':plan['spec'],'created_at':timestamp,'events':[],'inputs':[]}
                    self.policies.path.parent.mkdir(parents=True,exist_ok=True);self._journal(saved)
                directory=PreviewSpaces(self.runtime/'preview-directory')
                for kind,record in saved['directory_records'].items():
                    path=directory.root/kind/(record['id']+'.json')
                    if path.exists():
                        if json.loads(path.read_bytes())!=record:raise ValueError('initialization_directory_collision')
                    else:
                        # Exclusive durable file, no replacement of historical records.
                        pending=path.with_suffix('.'+plan['id']+'.pending')
                        # Pending name is owned by the saved intent; a torn staging write
                        # can be replaced on explicit resume, final records never can.
                        with pending.open('w',encoding='utf-8') as stream:
                            json.dump(record,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
                        pending.rename(path)
                saved['state']='directory_ready';self._journal(saved)
                source_store=SpaceSources(directory.root,self.sources);settings=source_store.read(plan['space_id'])
                if settings['revision']==0:
                    settings=source_store.change(SourceChange(space_id=plan['space_id'],expected_revision=0,catalog_sha256=source_store.catalog_sha256,
                        enabled_source_ids=plan['spec']['preset']['source_ids'],reason=request.reason),request.actor)
                if not set(plan['spec']['preset']['source_ids'])<=set(source_store.effective(settings)):raise ValueError('existing_source_settings_changed_no_repair')
                inputs=PreviewInputs(self.runtime/'preview-inputs',directory)
                entries=[]
                for key in plan['spec']['preset']['source_ids']:
                    source=self.sources[key]
                    registration=PreviewRegistration(inputs,{key:source},{'source_id':key,'settings_revision':settings['revision'],
                        'catalog_sha256':source_store.catalog_sha256,'actor':request.actor})
                    entry=registration.register(key,source['label'],plan['space_id'])['input']
                    record=inputs.resolve(entry['id'])
                    entries.append({'id':entry['id'],'source_id':key,'record_sha256':checksum(record)})
                saved['inputs']=entries;saved['state']='inputs_ready';self._journal(saved)
                # Source content must still be the reviewed content, not a replacement between plan and registration.
                for entry in entries:
                    record=inputs.resolve(entry['id']);checked=plan['spec']['sources'][entry['source_id']]['checked']
                    if any(record.get(k)!=v for k,v in checked.items()):raise ValueError('initialization_source_changed')
                with closing(sqlite3.connect(self.policies.path,timeout=10)) as db:
                    with db:
                        db.execute('BEGIN IMMEDIATE')
                        current=db.execute('SELECT revision,policy FROM policy WHERE id=1').fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='policy'").fetchone() else None
                        revision,policy=(current[0],SpaceAccessPolicy.model_validate_json(current[1])) if current else (0,SpaceAccessPolicy(bindings=[],grants=[]))
                        if revision!=expected_revision:raise ValueError('policy_revision_changed')
                        value=policy.model_dump()
                        if not request.existing_space_id:
                            if any(b['space_id']==plan['space_id'] for b in value['bindings']):raise ValueError('initialization_space_already_bound')
                            value['bindings'].append(plan['scope']|{'space_id':plan['space_id']})
                            value['grants'] += [{'issuer':plan['scope']['issuer'],'subject':s,'space_id':plan['space_id'],'role':'manager'} for s in request.manager_subjects]
                            revision=SpacePolicyStore.write_transaction(db,SpaceAccessPolicy.model_validate(value),expected_revision=expected_revision,
                                actor=request.actor,reason=request.reason[:400]+' [scene-init '+plan['id']+']')
                        receipt={'profile':'cospace.scene-initialization-receipt/0.1','id':plan['id'],'scope':plan['scope'],
                            'space_id':plan['space_id'],'project_id':plan['project_id'],'preset_id':request.preset_id,'scene_key':plan['scene_key'],
                            'inputs':entries,'policy_revision':revision,'initialized_at':now(),'quality':'unverified',
                            'production_ready':False,'robot_ready':False,'authority':'trusted_local_administrator','adopted':bool(request.existing_space_id)}
                        saved.update(state='complete',receipt=receipt,last_error=None)
                        saved['events'].append({'at':now(),'state':'complete','policy_revision':revision})
                        db.execute('UPDATE scene_initializations SET record=? WHERE id=?',(json.dumps(saved,ensure_ascii=False),plan['id']))
                return {'created':True,**receipt}
            except Exception as exc:
                if saved and saved['state']=='complete':saved=self._load(plan['id'])
                if saved:
                    saved['last_error']=type(exc).__name__+':'+str(exc)[:300]
                    saved['events'].append({'at':now(),'state':saved['state'],'error':saved['last_error']})
                    self._journal(saved)
                raise
