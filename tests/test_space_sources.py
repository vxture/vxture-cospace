from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import shutil
import pytest
from fastapi.testclient import TestClient
from packages.data.space_sources import SpaceSources,SourceChange,SourcesConflict,SourcesUnavailable
from packages.service.platform_business_http import BusinessAccess
from packages.service.platform_auth_http import create_auth_app
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_platform_business import secured,sign_in
from test_platform_login import runtime


def change(store,space,**overrides):
    return dict(space_id=space,expected_revision=0,catalog_sha256=store.catalog_sha256,
                enabled_source_ids=['office'],reason='Confirm approved input source')|overrides


@pytest.fixture
def sources_secured(secured):
    rp,_,_,_,jobs,directory,_,policies,*_=secured
    input=jobs.inputs.read(jobs.inputs.list()[0]['id'])
    sources={'office':{'label':'Approved office','snapshot':input['snapshot'],'tracking':input['tracking']}}
    from pathlib import Path
    copy=Path(input['snapshot']).parent/'second-snapshot'
    shutil.copytree(input['snapshot'],copy)
    sources['office-new']=sources['office']|{'label':'New sealed office','snapshot':copy}
    access=BusinessAccess(rp,policies,directory,jobs,sources)
    business=create_app(jobs.root/'build-one/output',jobs,space_directory=directory,platform_origin=rp.config.origin)
    with TestClient(create_auth_app(rp,business=business,access=access),base_url=rp.config.origin,follow_redirects=False) as client:
        values=list(secured);values[1]=client
        yield tuple(values),access.sources,input


def test_store_cas_history_restart_and_catalog_rebinding(tmp_path):
    sources={'office':{'label':'Office','snapshot':tmp_path/'source','tracking':tmp_path/'tracking'}}
    space='space-'+'a'*16;store=SpaceSources(tmp_path,sources)
    assert store.read(space)=={'revision':0,'bindings':{},'history':[]} and not store.path.exists()
    request=SourceChange.model_validate(change(store,space))
    saved=store.change(request,'usr_manager')
    assert SpaceSources(tmp_path,sources).read(space)==saved
    assert saved['history'][0]['actor']=='usr_manager'
    with pytest.raises(SourcesConflict):store.change(request,'usr_other')
    assert store.change(request.model_copy(update={'expected_revision':1}),'usr_manager')==saved
    moved=SpaceSources(tmp_path,{'office':sources['office']|{'snapshot':tmp_path/'other'}})
    assert moved.effective(saved)=={} and moved.view(space,True)['catalog'][0]['needs_confirmation']
    with pytest.raises(SourcesConflict):moved.change(request.model_copy(update={'expected_revision':1}),'usr_manager')
    reaffirm=SourceChange.model_validate(change(moved,space,expected_revision=1))
    assert moved.change(reaffirm,'usr_manager')['revision']==2
    assert moved.view(space,True)['sources'][0]['id']=='office'


def test_concurrent_changes_have_one_winner(tmp_path):
    sources={key:{'label':key,'snapshot':tmp_path/key} for key in ('office','laser')}
    store=SpaceSources(tmp_path,sources);space='space-'+'a'*16
    def run(key):
        try:return store.change(SourceChange.model_validate(change(store,space,enabled_source_ids=[key])),'usr_m')['revision']
        except SourcesConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(run,['office','laser']))
    assert sorted(map(str,result))==['1','conflict']
    assert len(store.read(space)['history'])==1


def test_enable_register_disable_preserves_existing_records(sources_secured):
    secured,store,input=sources_secured;_,c,_,_,jobs,_,spaces,*_=secured
    headers,_=sign_in(secured,'usr_manager');space=spaces[0]['id']
    query={'space_id':space};payload=change(store,space)
    body={'space_id':space,'source_id':'office','label':'Approved input'}
    before={p:p.read_bytes() for p in jobs.root.rglob('*') if p.is_file()}
    assert c.get('/api/registration-sources',params=query).json()['sources']==[]
    assert c.post('/api/inputs',json=body,headers=headers).status_code==409
    assert c.post('/api/source-settings',json=payload).status_code==403
    result=c.post('/api/source-settings',json=payload,headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['revision']==1 and result.json()['history'][0]['actor']=='usr_manager'
    assert input['snapshot'] not in result.text and 'tracking' not in result.text
    assert c.post('/api/source-settings',json=payload,headers=headers).status_code==409
    assert c.get('/api/registration-sources',params=query).json()['sources'][0]['id']=='office'
    headers,_=sign_in(secured,'usr_engineer')
    r=c.post('/api/inputs',json=body,headers=headers);assert r.status_code==200,r.text
    assert not r.json()['created'] and r.json()['input']['id']==input['id']
    read=c.get('/api/source-settings',params=query).json()
    assert not read['can_manage'] and read['history']==read['catalog']==[]
    assert c.post('/api/source-settings',json=payload,headers=headers).status_code==403
    headers,_=sign_in(secured,'usr_manager')
    assert c.post('/api/source-settings',json=payload|{'expected_revision':1,'enabled_source_ids':[]},headers=headers).status_code==200
    assert c.post('/api/inputs',json=body,headers=headers).status_code==409
    assert jobs.inputs.resolve(input['id'])['id']==input['id']
    assert all(p.read_bytes()==data for p,data in before.items())


@pytest.mark.parametrize('user',['usr_local_test','usr_other'])
def test_denied_before_catalog_or_source_io(sources_secured,user,monkeypatch):
    secured,store,_=sources_secured;_,c,_,_,_,_,spaces,*_=secured;headers,_=sign_in(secured,user)
    def forbidden(*a,**k):pytest.fail('must authorize before source settings access')
    monkeypatch.setattr(store,'read',forbidden)
    query={'space_id':spaces[0]['id']}
    assert c.get('/api/source-settings',params=query).status_code==403
    assert c.get('/api/registration-sources',params=query).status_code==403
    assert c.post('/api/inputs',json={'space_id':spaces[0]['id'],'source_id':'office','label':'X'},headers=headers).status_code==403


@pytest.mark.parametrize('overrides',[{'enabled_source_ids':['office','office']},{'enabled_source_ids':['unknown']},
    {'snapshot':'C:/outside'},{'reason':'  '},{'expected_revision':True}])
def test_bad_configuration_is_not_saved(sources_secured,overrides):
    secured,store,_=sources_secured;_,c,_,_,_,_,spaces,*_=secured;headers,_=sign_in(secured,'usr_manager')
    assert c.post('/api/source-settings',json=change(store,spaces[0]['id'],**overrides),headers=headers).status_code==403
    assert not store.path.exists()


def test_catalog_scope_missing_store_corruption_and_invalid_files(sources_secured):
    secured,store,input=sources_secured;_,c,_,_,_,_,spaces,*_=secured;headers,_=sign_in(secured,'usr_manager')
    assert c.get('/api/registration-sources').status_code==403
    assert c.get('/api/source-settings',params={'space_id':spaces[1]['id']}).status_code==403
    space=spaces[0]['id'];payload=change(store,space)
    assert c.post('/api/source-settings',json=payload|{'catalog_sha256':'0'*64},headers=headers).status_code==409
    assert c.post('/api/source-settings',json=payload,headers=headers).status_code==200
    from pathlib import Path
    (Path(input['snapshot'])/'raw/d.pgm').write_bytes(b'corrupt')
    assert c.post('/api/inputs',json={'space_id':space,'source_id':'office','label':'Corrupt'},headers=headers).status_code==409
    with sqlite3.connect(store.path) as db:db.execute('UPDATE settings SET record=?',('{"revision":true}',))
    assert c.get('/api/source-settings',params={'space_id':space}).status_code==503
    assert c.post('/api/inputs',json={'space_id':space,'source_id':'office','label':'Corrupt'},headers=headers).status_code==503
    with pytest.raises(SourcesUnavailable):store.read(space)


def test_new_registration_freezes_admitted_source_revision(sources_secured):
    secured,store,_=sources_secured;_,c,_,_,jobs,_,spaces,*_=secured
    headers,_=sign_in(secured,'usr_manager');space=spaces[0]['id']
    payload=change(store,space,enabled_source_ids=['office-new'])
    assert c.post('/api/source-settings',json=payload,headers=headers).status_code==200
    headers,_=sign_in(secured,'usr_engineer')
    body={'space_id':space,'source_id':'office-new','label':'New registration'}
    response=c.post('/api/inputs',json=body,headers=headers);assert response.status_code==201,response.text
    saved=response.json()['input'];ref=saved['registration_ref']
    assert ref=={'source_id':'office-new','settings_revision':1,'catalog_sha256':store.catalog_sha256,'actor':'usr_engineer'}
    assert jobs.inputs.read(saved['id'])['registration_ref']==ref
    repeat=c.post('/api/inputs',json=body|{'label':'Ignore renamed duplicate'},headers=headers)
    assert repeat.status_code==200 and not repeat.json()['created']
    assert repeat.json()['input']['label']=='New registration'


def test_optional_adapter_missing_returns_service_unavailable(sources_secured,monkeypatch):
    secured,store,_=sources_secured;_,c,_,_,_,_,spaces,*_=secured
    headers,_=sign_in(secured,'usr_manager');space=spaces[0]['id']
    assert c.post('/api/source-settings',json=change(store,space),headers=headers).status_code==200
    def missing(*a,**k):raise ImportError('optional adapter missing')
    monkeypatch.setattr('packages.data.preview_registration.inspect',missing)
    response=c.post('/api/inputs',json={'space_id':space,'source_id':'office','label':'Input'},headers=headers)
    assert response.status_code==503 and response.json()['detail']=='registration_adapter_unavailable'
