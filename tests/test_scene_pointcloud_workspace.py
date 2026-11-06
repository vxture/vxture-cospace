import hashlib
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from packages.data.scene_pointcloud_intake import digest, intake
from packages.data.scene_pointcloud_tiles import prepare_tiles
from packages.data.scene_pointcloud_workspace import ScenePointcloudWorkspace,ComposeRegion,SceneCloudConflict,SceneCloudUnavailable
from packages.service.platform_business_http import BusinessAccess
from packages.service.platform_auth_http import create_auth_app
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_scene_pointcloud_intake import fixture,opener_at
from test_platform_business import secured,sign_in
from test_platform_login import runtime


def assets_at(root,space):
    root.mkdir(exist_ok=True)
    one=fixture(root);two=fixture(root,'two.laz');two[1]['red']=65535
    scene=root/'scene'
    intake([one[0],two[0]],scene,scene_name='test',unit_basis='assumed_metre_for_flow_validation',
           chunk_points=3,opener=opener_at({'one.laz':one,'two.laz':two}))
    tiles=root/'tiles';index=prepare_tiles(scene,digest(scene/'scene.json'),tiles)
    config=root/'bindings.json'
    config.write_text(json.dumps({'profile':'cospace.scene-pointcloud-bindings/0.1','bindings':[
        {'space_id':space,'root':str(scene),'scene_sha256':digest(scene/'scene.json'),
         'tiles_root':str(tiles),'index_sha256':digest(tiles/'index.json')}]}))
    return config,index,scene,tiles


@pytest.fixture
def cloud_secured(secured,tmp_path):
    rp,_,accounts,clock,jobs,directory,spaces,policies,old,new=secured
    config,index,scene,tiles=assets_at(tmp_path/'cloud',spaces[0]['id'])
    access=BusinessAccess(rp,policies,directory,jobs,scene_pointcloud_config=config)
    app=create_auth_app(rp,business=create_app(None,jobs,space_directory=directory,platform_origin=rp.config.origin),access=access)
    with TestClient(app,base_url=rp.config.origin,follow_redirects=False) as client:
        yield (rp,client,accounts,clock,jobs,directory,spaces,policies,old,new),access,index,scene,tiles


def request_for(service,space,**updates):
    index=service.directory(space)
    return ComposeRegion.model_validate(dict(space_id=space,request_id='a'*32,index_sha256=index['index_sha256'],
        sources=['one.laz','two.laz'],bounds=[[-1.,-1.,-1.],[100.,100.,100.]],voxel_size=1.,label='selected region')|updates)


def finished(service,space,identity):
    for _ in range(200):
        value=service.status(space,identity)
        if value['state'] not in ('queued','running'):return value
        time.sleep(.02)
    pytest.fail('composition worker did not complete')


def test_offline_tiles_are_deterministic_original_point_derivatives(tmp_path):
    _,index,scene,tiles=assets_at(tmp_path,'space-'+'1'*16)
    again=tmp_path/'again';repeated=prepare_tiles(scene,digest(scene/'scene.json'),again)
    assert index==repeated and sum(t['source_points'] for t in index['tiles'])==14
    assert index['display_only'] and index['sampling']=='lowest_source_ordinal_per_voxel'
    for tile in index['tiles']:
        for lod in tile['lods']:
            raw=(tiles/f"{tile['id']}-{lod['level']}.bin").read_bytes()
            assert len(raw)==lod['points']*15 and hashlib.sha256(raw).hexdigest()==lod['sha256']
            xyz=np.frombuffer(raw[:lod['points']*12],dtype='<f4').reshape(-1,3)
            assert np.isfinite(xyz).all()
            assert len(np.unique(np.floor(xyz/lod['step']),axis=0))==len(xyz)
    first=index['tiles'][0]
    raw=(tiles/f"{first['id']}-2.bin").read_bytes()
    assert np.frombuffer(raw[:12],dtype='<f4').tolist()==[0.,1.,0.]


def test_scene_workspace_schemas_match_runtime():
    from packages.data.scene_pointcloud_workspace import SceneCloudConfig
    for model,name in ((SceneCloudConfig,'scene-pointcloud-bindings'),(ComposeRegion,'scene-pointcloud-compose')):
        schema=json.loads(Path(f'contracts/schemas/{name}-v0.1.schema.json').read_bytes())
        assert {k:v for k,v in schema.items() if k!='$schema'}==model.model_json_schema()


@pytest.mark.parametrize('user,expected',[('usr_local_test',403),('usr_other',403),('usr_engineer',200),('usr_manager',200)])
def test_source_directory_and_tiles_require_scene_data_permission(cloud_secured,user,expected):
    secured,access,index,_,_=cloud_secured;_,client,_,_,_,_,spaces,*_=secured
    space=spaces[0]['id'];sign_in(secured,user)
    response=client.get('/api/scene-pointclouds',params={'space_id':space})
    assert response.status_code==expected,response.text
    if expected==200:
        value=response.json();assert value['configured'] and value['space_id']==space
        assert 'tiles_root' not in response.text and 'snapshot' not in response.text
        tile=index['tiles'][0];query={'space_id':space,'index_sha256':value['index_sha256']}
        for method in ('GET','HEAD'):
            r=client.request(method,f"/api/scene-pointclouds/tiles/{tile['id']}/0",params=query)
            assert r.status_code==200 and r.headers['cache-control']=='no-store'
        assert client.get('/api/scene-pointclouds',params={'space_id':spaces[1]['id']}).status_code==403


def test_missing_binding_is_explicit_and_unbound_scene_cannot_read_tiles(cloud_secured):
    secured,access,_,_,_=cloud_secured;_,client,accounts,_,_,_,spaces,*_=secured
    accounts.roles=['workspace:owner'];sign_in(secured,'usr_owner')
    value=client.get('/api/scene-pointclouds',params={'space_id':spaces[1]['id']}).json()
    assert value['configured'] is False
    query={'space_id':spaces[1]['id'],'index_sha256':'a'*64}
    assert client.get('/api/scene-pointclouds/tiles/t00000/0',params=query).status_code==409


@pytest.mark.parametrize('problem',['index','source_manifest','tile','unknown','wrong_revision','duplicate_query','extra_query'])
def test_changed_or_ambiguous_assets_refuse_without_partial_payload(cloud_secured,problem):
    secured,access,index,scene,tiles=cloud_secured;_,client,_,_,_,_,spaces,*_=secured
    sign_in(secured,'usr_engineer');space=spaces[0]['id'];doc=access.scene_pointclouds.directory(space)
    tile=index['tiles'][0];identity=tile['id']
    if problem=='index':(tiles/'index.json').write_bytes(b'changed')
    if problem=='source_manifest':(scene/'scene.json').write_bytes(b'changed')
    if problem=='tile':(tiles/f'{identity}-0.bin').write_bytes(b'changed')
    if problem=='unknown':identity='t99999'
    query=[('space_id',space),('index_sha256','a'*64 if problem=='wrong_revision' else doc['index_sha256'])]
    if problem=='duplicate_query':query.append(('space_id',space))
    if problem=='extra_query':query.append(('path','../secret'))
    result=client.get(f'/api/scene-pointclouds/tiles/{identity}/0',params=query)
    assert result.status_code in (403,409,422) and result.headers['cache-control']=='no-store'
    assert result.headers['content-type'].startswith('application/json') and set(result.json())=={'detail'}


def test_composition_registers_once_in_same_scene_with_frozen_receipt(cloud_secured):
    secured,access,_,_,_=cloud_secured;_,client,_,_,jobs,_,spaces,*_=secured
    headers,_=sign_in(secured,'usr_engineer');space=spaces[0]['id'];service=access.scene_pointclouds
    body=request_for(service,space).model_dump()
    assert client.post('/api/scene-pointclouds/compositions',json=body).status_code==403
    r=client.post('/api/scene-pointclouds/compositions',json=body,headers=headers);assert r.status_code==202,r.text
    value=finished(service,space,r.json()['id']);assert value['state']=='succeeded',value
    record=jobs.inputs.read(value['input_id']);assert record['space_id']==space and record['point_count']==7
    receipt=json.loads((Path(record['snapshot'])/'composition.json').read_bytes())
    assert receipt['matched_points']==14 and [s['name'] for s in receipt['sources']]==body['sources']
    assert not receipt['alignment_verified']
    repeat=client.post('/api/scene-pointclouds/compositions',json=body,headers=headers)
    assert repeat.status_code==202 and repeat.json()['input_id']==value['input_id']
    assert client.post('/api/scene-pointclouds/compositions',json=body|{'voxel_size':2.},headers=headers).status_code==409
    assert client.get('/api/scene-pointclouds/compositions/'+value['id'],params={'space_id':spaces[1]['id']}).status_code==403
    assert client.post('/api/scene-pointclouds/compositions',json=body|{'root':'../outside'},headers=headers).status_code==422


def test_background_work_rechecks_permission_before_registration(cloud_secured,monkeypatch):
    from packages.data.scene_pointcloud_region import SceneRegions
    from packages.service.space_access import SpaceAccessPolicy
    secured,access,_,_,_=cloud_secured;_,client,_,_,jobs,_,spaces,policies,*_=secured
    headers,_=sign_in(secured,'usr_engineer');space=spaces[0]['id'];service=access.scene_pointclouds
    before={r['id'] for r in jobs.inputs.list()};entered=threading.Event();release=threading.Event();prepare=SceneRegions.prepare
    def delayed(*args,**kwargs):entered.set();assert release.wait(10);return prepare(*args,**kwargs)
    monkeypatch.setattr(SceneRegions,'prepare',delayed)
    r=client.post('/api/scene-pointclouds/compositions',json=request_for(service,space).model_dump(),headers=headers)
    try:
        assert r.status_code==202 and entered.wait(10)
        revision,policy=policies.load();doc=policy.model_dump();doc['grants']=[g for g in doc['grants'] if g['subject']!='usr_engineer']
        policies.replace(SpaceAccessPolicy.model_validate(doc),expected_revision=revision,actor='test',reason='revoke during work')
    finally:release.set()
    result=finished(service,space,r.json()['id'])
    assert result['state']=='failed' and result['issue']=='authorization_changed'
    assert {r['id'] for r in jobs.inputs.list()}==before


def test_budget_empty_and_interrupted_work_are_not_success(cloud_secured):
    secured,access,_,_,_=cloud_secured;_,_,_,_,jobs,_,spaces,*_=secured;space=spaces[0]['id'];service=access.scene_pointclouds
    value=service.start(request_for(service,space,bounds=[[500.,500.,500.],[501.,501.,501.]]),'test',lambda:None)
    result=finished(service,space,value['id']);assert result['state']=='failed' and result['issue']=='region_empty'
    path=service.root/value['id']/'job.json';result['state']='running';path.write_text(json.dumps(result))
    restarted=ScenePointcloudWorkspace(jobs.inputs,service.config)
    assert restarted.status(space,value['id'])['state']=='interrupted'


def test_worker_budget_busy_and_reused_request_are_explicit(cloud_secured,monkeypatch):
    from packages.data.scene_pointcloud_region import SceneRegions,RegionBudgetExceeded
    secured,access,_,_,_=cloud_secured;space=secured[6][0]['id'];service=access.scene_pointclouds
    entered=threading.Event();release=threading.Event()
    def fail(*args,**kwargs):entered.set();assert release.wait(10);raise RegionBudgetExceeded('limit')
    monkeypatch.setattr(SceneRegions,'prepare',fail)
    request=request_for(service,space)
    first=service.start(request,'test',lambda:None)
    try:
        assert entered.wait(10)
        assert service.start(request,'test',lambda:None)['id']==first['id']
        with pytest.raises(SceneCloudConflict,match='worker_busy'):
            service.start(request_for(service,space,request_id='b'*32),'test',lambda:None)
    finally:release.set()
    value=finished(service,space,first['id'])
    assert value['state']=='failed' and value['issue']=='region_budget_exceeded' and not value['input_id']


@pytest.mark.parametrize('updates',[
    {'bounds':[[0.,0.,0.],[0.,1.,1.]]},{'bounds':[[0.,0.],[1.,1.]]},
    {'voxel_size':.00001},{'sources':['one.laz','one.laz']},{'label':'   '},
    {'bounds':[[0.,0.,0.],[float('inf'),1.,1.]]},
])
def test_invalid_compose_parameters_rejected_before_work(cloud_secured,updates):
    from pydantic import ValidationError
    secured,access,_,_,_=cloud_secured
    with pytest.raises(ValidationError):request_for(access.scene_pointclouds,secured[6][0]['id'],**updates)


@pytest.mark.parametrize('change',['none','tampered_bundle','other_actor','revoked'])
def test_expired_confirmation_preserves_derivative_and_fresh_post_registers_once(cloud_secured,monkeypatch,change):
    from packages.data.scene_pointcloud_region import SceneRegions
    from packages.service.space_access import SpaceAccessPolicy
    secured,access,_,_,_=cloud_secured;rp,client,_,clock,jobs,_,spaces,policies,*_=secured
    headers,sid=sign_in(secured,'usr_engineer');space=spaces[0]['id'];service=access.scene_pointclouds
    prepare=SceneRegions.prepare;calls=[];before={r['id'] for r in jobs.inputs.list()}
    def expire(*args,**kwargs):
        result=prepare(*args,**kwargs);calls.append(True);clock[0]+=100;return result
    monkeypatch.setattr(SceneRegions,'prepare',expire)
    response=client.post('/api/scene-pointclouds/compositions',json=request_for(service,space).model_dump(),headers=headers)
    value=finished(service,space,response.json()['id'])
    assert value['state']=='awaiting_authorization' and value['issue']=='confirm_session_to_register'
    restarted=ScenePointcloudWorkspace(jobs.inputs,service.config)
    assert restarted.status(space,value['id'])['state']=='awaiting_authorization'
    assert value['retained_points']==7 and {r['id'] for r in jobs.inputs.list()}==before
    url='/api/scene-pointclouds/compositions/'+value['id']+'/register';body={'space_id':space}
    assert client.post(url,json=body,headers=headers).status_code==503
    assert client.post('/api/auth/session',headers=headers).status_code==200
    assert service.status(space,value['id'])['state']=='awaiting_authorization'
    if change=='tampered_bundle':(service.root/value['id']/'input.zip').write_bytes(b'changed')
    if change=='other_actor':headers,_=sign_in(secured,'usr_manager')
    if change=='revoked':
        revision,policy=policies.load();doc=policy.model_dump();doc['grants']=[g for g in doc['grants'] if g['subject']!='usr_engineer']
        policies.replace(SpaceAccessPolicy.model_validate(doc),expected_revision=revision,actor='test',reason='revoke before resume')
    assert client.post(url,json=body).status_code==403
    result=client.post(url,json=body,headers=headers)
    if change=='none':
        assert result.status_code==202,result.text
        assert result.json()['state']=='succeeded' and result.json()['input_id']
        assert client.post(url,json=body,headers=headers).json()['input_id']==result.json()['input_id']
        assert len(jobs.inputs.list())==len(before)+1
    else:
        assert result.status_code==(409 if change=='tampered_bundle' else 403)
        assert {r['id'] for r in jobs.inputs.list()}==before
    assert len(calls)==1  # No second scan, even after confirmation or repeated POST.
