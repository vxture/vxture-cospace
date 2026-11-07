import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from packages.data.ifc_inspection import digest
from packages.data.ifc_workspace import IfcWorkspace
from packages.service.platform_business_http import BusinessAccess
from packages.service.platform_auth_http import create_auth_app
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_platform_business import secured,sign_in
from test_platform_login import runtime
from test_ifc_inspection import assets_at,VERTICES


@pytest.fixture
def ifc_secured(secured,tmp_path):
    rp,_,accounts,clock,jobs,directory,spaces,policies,old,new=secured
    config,doc,root=assets_at(tmp_path/'ifc',spaces[0]['id'])
    access=BusinessAccess(rp,policies,directory,jobs,scene_ifc_config=config)
    app=create_auth_app(rp,business=create_app(None,jobs,space_directory=directory,platform_origin=rp.config.origin),access=access)
    with TestClient(app,base_url=rp.config.origin,follow_redirects=False) as client:
        yield (rp,client,accounts,clock,jobs,directory,spaces,policies,old,new),access,root,config


@pytest.mark.parametrize('user,expected',[('usr_local_test',403),('usr_other',403),('usr_engineer',200),('usr_manager',200)])
def test_scene_and_workspace_permission_precedes_ifc_file_read(ifc_secured,user,expected):
    env,access,root,_=ifc_secured;rp,client,accounts,_,_,_,spaces,*_=env
    assert client.get('/api/scene-ifc',params={'space_id':spaces[0]['id']}).status_code==401
    sign_in(env,user)
    response=client.get('/api/scene-ifc',params={'space_id':spaces[0]['id']})
    assert response.status_code==expected,response.text
    assert response.headers['cache-control']=='no-store'
    if expected==200:
        data=response.json();assert data['configured'] and data['space_id']==spaces[0]['id']
        assert 'mesh' not in data['products'][1] and str(root) not in response.text
        query=dict(space_id=spaces[0]['id'],element_id='e00001',catalog_sha256=data['catalog_sha256'])
        preview=client.get('/api/scene-ifc/element',params=query);assert preview.status_code==200
        assert preview.json()['points']==VERTICES.tolist() and preview.json()['point_count']==4
        accounts.workspace='foreign';sign_in(env,user)
        assert client.get('/api/scene-ifc/element',params=query).status_code==403
    assert client.get('/api/scene-ifc',params={'space_id':spaces[1]['id']}).status_code==403


def test_directory_preview_binding_changed_files_and_parameters(ifc_secured):
    env,access,root,_=ifc_secured;_,client,_,_,_,_,spaces,*_=env;sign_in(env,'usr_engineer');space=spaces[0]['id']
    response=client.get('/api/scene-ifc',params={'space_id':space});sha=response.json()['catalog_sha256']
    query=dict(space_id=space,element_id='e00001',catalog_sha256=sha)
    for change,expected in [({'catalog_sha256':'0'*64},409),({'element_id':'e00000'},409),({'element_id':'../outside'},409),({'root':'private'},422)]:
        r=client.get('/api/scene-ifc/element',params=query|change);assert r.status_code==expected
    assert client.get('/api/scene-ifc',params={'space_id':space,'extra':'1'}).status_code==422
    (root/'e00001.npz').write_bytes(b'changed')
    r=client.get('/api/scene-ifc/element',params=query);assert r.status_code==409 and r.json()['detail']=='ifc_evidence_unavailable'
    assert str(root) not in r.text
    (root/'ifc.json').write_bytes(b'changed')
    assert client.get('/api/scene-ifc',params={'space_id':space}).status_code==409


def test_unconfigured_scene_is_explicit(tmp_path):
    from types import SimpleNamespace
    directory=SimpleNamespace(read=lambda *args:None)
    result=IfcWorkspace(directory,None).directory_view('space-'+'1'*16)
    assert result['configured'] is False


def test_coordinate_mutations_have_no_http_entrypoint(ifc_secured):
    env,*_=ifc_secured;_,client,_,_,_,_,spaces,*_=env
    headers,_=sign_in(env,'usr_engineer')
    assert client.post('/api/scene-ifc/coordinate-check',json={'space_id':spaces[0]['id']},headers=headers).status_code==403


def test_preserved_ifc_source_must_match_catalog(ifc_secured):
    env,_,root,_=ifc_secured;_,client,_,_,_,_,spaces,*_=env;sign_in(env,'usr_engineer')
    (root/'source.ifc').write_bytes(b'changed')
    response=client.get('/api/scene-ifc',params={'space_id':spaces[0]['id']})
    assert response.status_code==409 and response.json()['detail']=='ifc_evidence_unavailable'
