from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
import subprocess
import sys
import os
from pathlib import Path
import pytest
from packages.lifecycle.workspace_scenes import WorkspaceScenes,CreateScene,WorkspaceScenesConflict,WorkspaceScenesUnavailable
from packages.data.space_sources import SpaceSources
from packages.service.space_access import SpaceAccessPolicy
from test_platform_business import secured,sign_in
from test_platform_login import runtime
from test_space_access import principal
from test_space_sources import sources_secured


@pytest.fixture
def online(secured):
    rp,client,accounts,_,jobs,directory,spaces,policies,*_=secured
    sources=SpaceSources(directory.root,{'office':{'label':'Office','snapshot':directory.root/'office'},
                                          'laser':{'label':'Laser','snapshot':directory.root/'laser'}})
    service=WorkspaceScenes(directory,policies,sources)
    value={'profile':'cospace.workspace-scenes/0.1','revision':1,'workspaces':[
        {'issuer':rp.config.issuer,'org_id':'org_mock','workspace_id':'ws_mock','allow_create':True,
         'creator_subjects':['usr_manager'],'source_bindings':{'office':sources.fingerprints['office']}}]}
    service.config.write_text(json.dumps(value),encoding='utf-8')
    user=replace(principal(),issuer=rp.config.issuer,org_id='org_mock',workspace_id='ws_mock',subject='usr_manager')
    return secured,service,user,value


def request(service,user,**values):
    return CreateScene.model_validate({'request_id':'a'*32,'context_sha256':service.context(user)['context_sha256'],
                                       'name':'Equipment room','description':'One physical scene'}|values)


def test_create_binds_current_workspace_without_model_or_input_and_reuses_after_restart(online):
    secured,service,user,_=online;_,_,_,_,jobs,directory,_,policies,*_=secured
    old={p:p.read_bytes() for p in jobs.root.rglob('*') if p.is_file()}
    result=service.create(user,request(service,user));space=result['space_id']
    assert result['created'] and result['actor']==user.subject
    assert directory.read('space',space)['name']=='Equipment room'
    _,policy=policies.load();assert policy.capabilities(user,space)==frozenset(('space.preview','space.query','space.export','data.manage','build.run','association.edit','publication.manage','space.manage'))
    assert not policy.capabilities(replace(user,workspace_id='ws_other'),space)
    restored=WorkspaceScenes(directory,policies,service.sources)
    assert restored.create(user,request(restored,user))==result|{'created':False}
    assert all(p.read_bytes()==raw for p,raw in old.items())
    assert not any(i['space_id']==space for i in jobs.inputs.list())


@pytest.mark.parametrize('roles,subject,allowed',[(('workspace:owner',),'usr_owner',True),
    (('org:owner',),'usr_owner',False),(('workspace:manager',),'usr_other',False),
    (('workspace:member',),'usr_manager',True),(('workspace:member',),'usr_other',False)])
def test_owner_baseline_and_explicit_product_creators(online,roles,subject,allowed):
    _,service,user,_=online;user=replace(user,governance_roles=roles,subject=subject)
    assert service.context(user)['can_create'] is allowed
    if not allowed:
        with pytest.raises(PermissionError):service.create(user,request(service,user))


def test_configuration_is_exact_workspace_scoped_and_fail_closed(online):
    _,service,user,_=online
    assert not service.context(replace(user,workspace_id='foreign'))['can_create']
    assert service.scoped_sources(replace(user,workspace_id='foreign')).sources=={}
    service.config.unlink()
    with pytest.raises(WorkspaceScenesUnavailable):service.context(user)
    restarted=WorkspaceScenes(service.directory,service.policies,service.sources)
    with pytest.raises(WorkspaceScenesUnavailable):restarted.context(user)
    service.config.write_text('{invalid',encoding='utf-8')
    with pytest.raises(WorkspaceScenesUnavailable):service.context(user)


def test_source_allocation_pins_fingerprint_and_config_revision(online):
    _,service,user,value=online
    assert set(service.scoped_sources(user).sources)=={'office'}
    before=request(service,user)
    service.sources=SpaceSources(service.directory.root,{'office':{'label':'Moved','snapshot':'elsewhere'}})
    assert service.scoped_sources(user).sources=={}
    with pytest.raises(WorkspaceScenesConflict,match='context_changed'):service.create(user,before)
    value['revision']=2;value['workspaces'][0]['source_bindings']={}
    service.config.write_text(json.dumps(value),encoding='utf-8')
    assert service.scoped_sources(user).sources=={}


def test_concurrent_duplicate_and_distinct_requests(online):
    _,service,user,_=online
    def create(i):return service.create(user,request(service,user,request_id=i*32))
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(create,['a','a','b']))
    assert len({r['space_id'] for r in results})==2
    assert sum(r['created'] for r in results)==2
    assert len({r['project_id'] for r in results})==1


def test_response_loss_retry_and_request_reuse_refusal(online):
    _,service,user,_=online
    created=service.create(user,request(service,user))
    assert not service.create(user,request(service,user))['created']
    with pytest.raises(WorkspaceScenesConflict,match='request_id_reused'):
        service.create(user,request(service,user,name='Different scene'))
    assert created['space_id']


@pytest.mark.parametrize('point',['directory','transaction'])
def test_partial_scene_remains_unbound_until_explicit_retry(online,monkeypatch,point):
    secured,service,user,_=online;policies=secured[7];before=policies.load()[0]
    original=service.write_directory if point=='directory' else policies.write_transaction
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError('injected process boundary')
    target=service if point=='directory' else policies
    name='write_directory' if point=='directory' else 'write_transaction'
    monkeypatch.setattr(target,name,fail)
    with pytest.raises(OSError):service.create(user,request(service,user))
    assert policies.load()[0]==before
    assert all(b.space_id in {s['id'] for s in secured[6]} for b in policies.load()[1].bindings)
    monkeypatch.setattr(target,name,original)
    assert service.create(user,request(service,user))['created']


@pytest.mark.parametrize('revoke',['grant','binding','directory','creation'])
def test_completed_replay_never_restores_revoked_access_or_missing_files(online,revoke):
    secured,service,user,value=online;policies=secured[7]
    result=service.create(user,request(service,user));space=result['space_id']
    if revoke in ('grant','binding'):
        rev,policy=policies.load();data=policy.model_dump()
        data['grants']=[g for g in data['grants'] if g['space_id']!=space]
        if revoke=='binding':data['bindings']=[b for b in data['bindings'] if b['space_id']!=space]
        policies.replace(SpaceAccessPolicy.model_validate(data),expected_revision=rev,actor='test',reason='revoke')
    elif revoke=='directory':(service.directory.root/'space'/(space+'.json')).unlink()
    else:
        value['workspaces'][0]['allow_create']=False;service.config.write_text(json.dumps(value),encoding='utf-8')
    rev=policies.load()[0]
    with pytest.raises((WorkspaceScenesConflict,PermissionError)):service.create(user,request(service,user))
    assert policies.load()[0]==rev


def test_http_creation_identity_csrf_replay_and_legacy_route_closed(online):
    secured,service,_,_=online;_,c,accounts,_,jobs,directory,_,policies,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    context=c.get('/api/workspace-scenes').json();assert context['can_create']
    body={'name':'HTTP scene','description':'','request_id':'d'*32,'context_sha256':context['context_sha256']}
    assert c.post('/api/workspace-scenes',json=body).status_code==403
    for extra in ({'workspace_id':'foreign'},{'scope':{}},{'project_id':'anything'},{'manager_subjects':['usr_other']}):
        assert c.post('/api/workspace-scenes',json=body|extra,headers=headers).status_code==422
    first=c.post('/api/workspace-scenes',json=body,headers=headers);assert first.status_code==201,first.text
    assert c.post('/api/workspace-scenes',json=body,headers=headers).status_code==200
    space=first.json()['space_id'];assert c.get('/api/spaces/'+space).status_code==200
    assert c.get('/api/inputs',params={'space_id':space}).json()['inputs']==[]
    assert c.post('/api/spaces',json=body,headers=headers).status_code==403
    headers,_=sign_in(secured,'usr_local_test')
    assert not c.get('/api/workspace-scenes').json()['can_create']
    assert c.post('/api/workspace-scenes',json=body,headers=headers).status_code==403
    assert c.get('/api/spaces/'+space).status_code==403
    accounts.workspace='ws_other';headers,_=sign_in(secured,'usr_manager')
    assert not c.get('/api/workspace-scenes').json()['can_create']
    assert c.get('/api/spaces').json()['spaces']==[]


def test_two_workspace_same_request_id_isolated(online):
    _,service,user,value=online
    value['workspaces'].append(value['workspaces'][0]|{'workspace_id':'ws_other'})
    service.config.write_text(json.dumps(value),encoding='utf-8')
    other=replace(user,workspace_id='ws_other')
    a=service.create(user,request(service,user));b=service.create(other,request(service,other))
    assert a['space_id']!=b['space_id'] and a['project_id']!=b['project_id']


def test_missing_online_configuration_keeps_creation_off(secured):
    _,c,*_=secured;headers,_=sign_in(secured,'usr_manager')
    assert c.get('/api/workspace-scenes').json()['can_create'] is False
    assert c.post('/api/workspace-scenes',json={},headers=headers).status_code==403


def test_signed_workspace_owner_can_bootstrap_without_existing_scene_grant(online):
    secured,_,_,_=online;_,c,accounts,*_=secured
    accounts.roles=['workspace:owner'];headers,_=sign_in(secured,'usr_new_owner')
    context=c.get('/api/workspace-scenes').json();assert context['can_create']
    response=c.post('/api/workspace-scenes',json={'name':'Owner first scene','request_id':'f'*32,
                                                'context_sha256':context['context_sha256']},headers=headers)
    assert response.status_code==201,response.text


def test_http_source_catalog_and_registration_obey_workspace_allocation(sources_secured):
    secured,store,input=sources_secured;rp,c,_,_,jobs,_,spaces,policies,*_=secured
    path=policies.path.parent/'workspace-scenes.json'
    config={'profile':'cospace.workspace-scenes/0.1','revision':1,'workspaces':[
        {'issuer':rp.config.issuer,'org_id':'org_mock','workspace_id':'ws_mock','allow_create':True,
         'source_bindings':{'office':store.fingerprints['office']}}]}
    path.write_text(json.dumps(config),encoding='utf-8');headers,_=sign_in(secured,'usr_manager')
    space=spaces[0]['id'];url='/api/source-settings?space_id='+space
    catalog=c.get(url).json();assert [s['id'] for s in catalog['catalog']]==['office']
    body={'space_id':space,'expected_revision':0,'catalog_sha256':catalog['catalog_sha256'],
          'enabled_source_ids':['office-new'],'reason':'cross allocation attempt'}
    assert c.post('/api/source-settings',json=body,headers=headers).status_code==403
    assert c.post('/api/source-settings',json=body|{'enabled_source_ids':['office']},headers=headers).status_code==200
    assert c.post('/api/inputs',json={'space_id':space,'source_id':'office','label':'Owned'},headers=headers).status_code==200
    config['revision']=2;config['workspaces'][0]['source_bindings']={};path.write_text(json.dumps(config),encoding='utf-8')
    assert c.get('/api/registration-sources?space_id='+space).json()['sources']==[]
    assert c.post('/api/inputs',json={'space_id':space,'source_id':'office','label':'Revoked'},headers=headers).status_code==409
    assert jobs.inputs.resolve(input['id'])['id']==input['id']
    path.unlink();assert c.get(url).status_code==503


def test_actual_process_exit_after_files_then_explicit_resume(online):
    secured,service,user,_=online;before=secured[7].load()[0]
    data=service.runtime.parent/'crash-request.json'
    from dataclasses import asdict
    data.write_text(json.dumps({'principal':asdict(user),'request':request(service,user).model_dump(),
        'directory':str(service.directory.root),'policy':str(service.policies.path.parent),
        'sources':{k:{**v,'snapshot':str(v['snapshot'])} for k,v in service.sources.sources.items()}}),encoding='utf-8')
    code='''
import json,os,sys
from pathlib import Path
from packages.lifecycle.workspace_scenes import WorkspaceScenes,CreateScene
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.infrastructure.platform_identity import PlatformPrincipal
from packages.data.space_sources import SpaceSources
d=json.loads(Path(sys.argv[1]).read_bytes())
directory=PreviewSpaces(d['directory']);policies=SpacePolicyStore(d['policy'])
service=WorkspaceScenes(directory,policies,SpaceSources(directory.root,d['sources']))
original=service.write_directory
def crash(*a,**k):
 original(*a,**k)
 os._exit(23)
service.write_directory=crash
service.create(PlatformPrincipal(**d['principal']),CreateScene.model_validate(d['request']))
'''
    result=subprocess.run([sys.executable,'-X','utf8','-c',code,str(data)],capture_output=True,timeout=30,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==23,result.stderr.decode(errors='replace')
    assert secured[7].load()[0]==before
    with sqlite3.connect(service.policies.path) as db:
        assert json.loads(db.execute('SELECT record FROM workspace_scene_creations').fetchone()[0])['state']=='prepared'
    result=service.create(user,request(service,user));assert result['created']
    assert not service.create(user,request(service,user))['created']
