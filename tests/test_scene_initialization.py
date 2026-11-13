from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import pytest
from packages.data.preview_inputs import PreviewInputs
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.lifecycle.scene_initialization import SceneInitialization,InitializationRequest
from packages.service.space_access import SpaceAccessPolicy
from test_preview_inputs import source
from test_space_access import principal
from test_platform_business import secured,sign_in
from test_platform_login import runtime


@pytest.fixture
def setup(tmp_path):
    sources={}
    for key in ('office','laser'):
        snapshot,tracking=source(tmp_path/key)
        sources[key]={'label':key,'snapshot':snapshot,'tracking':tracking,'format':'nyu_rgbd_with_existing_poses'}
    presets={'profile':'cospace.scene-presets/0.1','presets':[{'id':key,'scene_key':'physical-'+key,'name':key,'description':'Test sample','source_ids':[key]} for key in sources]}
    policies=SpacePolicyStore(tmp_path/'auth');runtime=tmp_path/'sample'
    service=SceneInitialization(runtime,policies,sources,presets)
    request=InitializationRequest(scope={'issuer':'https://accounts.vxture.com','org_id':'org_1','workspace_id':'ws_1'},
        preset_id='office',manager_subjects=['usr_alice'],actor='trusted_test_operator',reason='P5 bootstrap test')
    return service,request


def apply(service,request):
    plan=service.plan(request)
    return service.apply(request,plan['policy_revision'],plan['plan_sha256'])


def files(root):return {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_readonly_plan_then_idempotent_initialization_and_restart(setup):
    service,request=setup;before=files(service.runtime.parent)
    plan=service.plan(request)
    assert plan['state']=='not_started' and plan['policy_revision']==0
    assert files(service.runtime.parent)==before and not service.runtime.exists() and not service.policies.path.exists()
    first=service.apply(request,0,plan['plan_sha256']);assert first['created']
    before=files(service.runtime.parent)
    restarted=SceneInitialization(service.runtime,service.policies,service.sources,{'profile':'cospace.scene-presets/0.1','presets':list(service.presets.values())})
    repeat=apply(restarted,request)
    assert repeat==first|{'created':False}
    # SQLite readers and lock contents do not manufacture new records or history.
    assert files(service.runtime.parent)==before
    assert len(PreviewSpaces(service.runtime/'preview-directory').list('space'))==1
    assert len(PreviewInputs(service.runtime/'preview-inputs').list())==1
    _,policy=service.policies.load()
    assert policy.capabilities(principal(),first['space_id'])==frozenset({'space.preview','space.query','space.export','data.manage','build.run','association.edit','publication.manage','space.manage','recipient.read','recipient.manage'})
    assert not (service.runtime/'preview-builds').exists()


def test_two_scenes_share_workspace_project_other_workspace_isolated(setup):
    service,request=setup;office=apply(service,request)
    laser=apply(service,request.model_copy(update={'preset_id':'laser'}))
    other=apply(service,request.model_copy(update={'scope':request.scope.model_copy(update={'workspace_id':'ws_2'})}))
    assert office['space_id']!=laser['space_id']!=other['space_id']
    assert office['project_id']==laser['project_id']!=other['project_id']
    directory=PreviewSpaces(service.runtime/'preview-directory');spaces=directory.list('space')
    _,policy=service.policies.load()
    assert {s['id'] for s in policy.visible(principal(),spaces)}=={office['space_id'],laser['space_id']}
    assert [s['id'] for s in policy.visible(replace(principal(),workspace_id='ws_2'),spaces)]==[other['space_id']]
    assert len(PreviewInputs(service.runtime/'preview-inputs').list())==3
    assert not policy.capabilities(principal(subject='usr_bob'),office['space_id'])


@pytest.mark.parametrize('fault',['after_directory','after_input','inside_policy_commit'])
def test_partial_failure_audited_unbound_and_resume_without_duplicates(setup,monkeypatch,fault):
    service,request=setup;plan=service.plan(request)
    if fault=='after_directory':
        original=PreviewInputs.register
        def fail(*args,**kwargs):raise OSError('controlled registration interruption')
        monkeypatch.setattr(PreviewInputs,'register',fail)
    elif fault=='after_input':
        original=PreviewInputs.register
        def fail(*args,**kwargs):
            original(*args,**kwargs);raise OSError('controlled lost registration acknowledgement')
        monkeypatch.setattr(PreviewInputs,'register',fail)
    else:
        original=SpacePolicyStore.write_transaction
        def fail(*args,**kwargs):
            original(*args,**kwargs);raise OSError('controlled precommit interruption')
        monkeypatch.setattr(SpacePolicyStore,'write_transaction',staticmethod(fail))
    with pytest.raises(OSError):service.apply(request,0,plan['plan_sha256'])
    saved=service._load(plan['id']);assert saved['state']!='complete' and saved['last_error'] and saved['events']
    with sqlite3.connect(service.policies.path) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='policy'").fetchone():assert not db.execute('SELECT * FROM policy').fetchall()
    monkeypatch.undo()
    result=apply(service,request)
    assert result['created'] and len(PreviewInputs(service.runtime/'preview-inputs').list())==1
    assert len(PreviewSpaces(service.runtime/'preview-directory').list('space'))==1
    assert service._load(plan['id'])['events'][-1]['state']=='complete'


def test_plan_cas_and_concurrent_apply_have_one_winner(setup):
    service,request=setup;plan=service.plan(request)
    with pytest.raises(ValueError,match='initialization_plan_changed'):service.apply(request,0,'0'*64)
    assert not service.policies.path.exists()
    def run(_):
        try:return service.apply(request,0,plan['plan_sha256'])['created']
        except ValueError as exc:return str(exc)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
    assert results.count(True)==1 and 'policy_revision_changed' in results
    assert len(PreviewInputs(service.runtime/'preview-inputs').list())==1


@pytest.mark.parametrize('kind',['grant','binding','directory','input','sources','missing_sources'])
def test_completed_replay_never_repairs_revocation_or_missing_records(setup,kind):
    service,request=setup;result=apply(service,request);sid=result['space_id']
    if kind in ('grant','binding'):
        rev,policy=service.policies.load();value=policy.model_dump()
        value['grants']=[]
        if kind=='binding':value['bindings']=[]
        service.policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=rev,actor='admin',reason='revoke')
    elif kind=='directory':(service.runtime/'preview-directory/space'/(sid+'.json')).unlink()
    elif kind=='input':(service.runtime/'preview-inputs'/(result['inputs'][0]['id']+'.json')).write_text('{}')
    elif kind=='missing_sources':(service.runtime/'preview-directory/registration-sources.sqlite3').unlink()
    else:
        with sqlite3.connect(service.runtime/'preview-directory/registration-sources.sqlite3') as db:
            record=json.loads(db.execute('SELECT record FROM settings WHERE space_id=?',(sid,)).fetchone()[0]);record['bindings']={}
            db.execute('UPDATE settings SET record=? WHERE space_id=?',(json.dumps(record),sid))
    before=files(service.runtime.parent)
    with pytest.raises((ValueError,KeyError)):apply(service,request)
    assert files(service.runtime.parent)==before


def test_existing_sample_requires_explicit_adoption_preserving_originals(setup):
    service,request=setup;directory=PreviewSpaces(service.runtime/'preview-directory')
    project=directory.create('project','existing');space=directory.create('space','original office',project['id'])
    binding=request.scope.model_dump()|{'space_id':space['id']}
    service.policies.replace(SpaceAccessPolicy(bindings=[binding],grants=[{'issuer':request.scope.issuer,'subject':'usr_alice','space_id':space['id'],'role':'manager'}]),expected_revision=0,actor='admin',reason='existing binding')
    src=service.sources['office'];entry=PreviewInputs(service.runtime/'preview-inputs',directory).register('original label',src['snapshot'],src['tracking'],space['id'])
    before={p:p.read_bytes() for p in [directory.root/'space'/(space['id']+'.json'),directory.root/'project'/(project['id']+'.json'),service.runtime/'preview-inputs'/(entry['id']+'.json')]}
    with pytest.raises(ValueError,match='explicit_adoption_required'):service.plan(request)
    result=apply(service,request.model_copy(update={'existing_space_id':space['id']}))
    assert result['adopted'] and result['space_id']==space['id'] and result['inputs'][0]['id']==entry['id']
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert service.policies.load()[0]==1
    with pytest.raises(ValueError,match='contains_other_sample'):
        service.plan(request.model_copy(update={'existing_space_id':space['id'],'preset_id':'laser'}))


@pytest.mark.parametrize('field,value',[('preset_id','missing'),('runtime','var/nyu/forbidden'),('sources',{})])
def test_invalid_target_or_source_refused_without_mutation(setup,field,value):
    service,request=setup;before=files(service.runtime.parent)
    with pytest.raises(ValueError):
        if field=='runtime':SceneInitialization(value,service.policies,service.sources,{'profile':'cospace.scene-presets/0.1','presets':list(service.presets.values())})
        else:
            if field=='sources':service.sources={}
            if field=='preset_id':request=request.model_copy(update={'preset_id':value})
            service.plan(request)
    assert files(service.runtime.parent)==before


def test_definition_or_source_changes_require_new_review(setup):
    service,request=setup;plan=service.plan(request)
    service.sources['office']['label']='Changed label before apply'
    # Labels affect registration output and must be pinned by the reviewed plan too.
    with pytest.raises(ValueError,match='plan_changed'):service.apply(request,0,plan['plan_sha256'])
    result=apply(service,request)
    with pytest.raises(ValueError,match='definition_changed'):service.plan(request.model_copy(update={'reason':'different request'}))
    assert result['created'] and plan['state']=='not_started'


@pytest.mark.parametrize('user,owner',[('usr_local_test',False),('usr_manager',False),('usr_manager',True)])
def test_online_creation_is_not_inferred_even_for_workspace_owner(secured,user,owner):
    _,client,accounts,_,jobs,directory,spaces,*_=secured
    if owner:accounts.roles=['workspace:owner']
    headers,_=sign_in(secured,user)
    before=files(directory.root)|files(jobs.inputs.root)
    for path in ('/api/spaces','/api/scene-initializations'):
        response=client.post(path,json={'name':'unapproved scene','project_id':spaces[0]['project_id'],'workspace_id':'ws_mock'},headers=headers)
        assert response.status_code==403
    assert files(directory.root)|files(jobs.inputs.root)==before
