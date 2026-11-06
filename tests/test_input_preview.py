import json
from pathlib import Path
import time
import numpy as np
import pytest
from packages.data.input_preview import preview,sample,bounded,PreviewUnavailable
from packages.construction.build_preview import preview as build_preview
from test_preview_pointcloud import specimen
from test_pointcloud_preparation import declared
from test_platform_business import secured,sign_in
from test_platform_login import runtime
from test_preview_batches import prepared,files


@pytest.mark.parametrize('rgb',[False,True])
@pytest.mark.parametrize('receipt',[False,True])
def test_input_preview_read_only_and_bound(tmp_path,rgb,receipt):
    _,jobs,_,spaces,_=prepared(tmp_path);root=specimen(tmp_path,rgb)
    if receipt:declared(root)
    record=jobs.inputs.register('cloud',root,space_id=spaces[0]['id'],format='ply_pointcloud')
    before=files(tmp_path);a=preview(jobs.inputs,record['id'],record['space_id']);b=preview(jobs.inputs,record['id'],record['space_id'])
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path('contracts/schemas/input-preview-v0.1.schema.json').read_bytes())).validate(a)
    assert a==b and files(tmp_path)==before
    assert a['point_count']==2 and a['sampling']['count']==2 and a['source_sha256']==record['cloud_sha256']
    assert a['colors'][0]==([10,20,30] if rgb else [160]*3)
    assert a['bounds']==[[1.,2.,.5],[2.,3.,float(np.float32(.6))]]
    assert 'snapshot' not in a and a['quality']=='unverified' and not a['robot_ready']
    with pytest.raises(PermissionError):preview(jobs.inputs,record['id'],spaces[1]['id'])


@pytest.mark.parametrize('count',[1,10_000,10_001,1_000_000])
def test_sample_full_bounds_deterministic_and_bounded(count):
    points=np.arange(count*3,dtype=np.float32).reshape(-1,3)+500_000
    colors=np.full(points.shape,160,dtype=np.uint8);a=bounded(sample(points,colors))
    assert a['sampling']['count']<=10_000 and a['point_count']==count
    assert a['bounds']==[points[0].tolist(),points[-1].tolist()]
    assert a==sample(points,colors)


@pytest.mark.parametrize('member',['cloud.ply','pointcloud.json','source.json'])
def test_source_changed_never_returns_cached_geometry(tmp_path,member):
    _,jobs,_,spaces,_=prepared(tmp_path);root=specimen(tmp_path);declared(root)
    record=jobs.inputs.register('cloud',root,space_id=spaces[0]['id'],format='ply_pointcloud')
    preview(jobs.inputs,record['id'],record['space_id']);(root/member).write_bytes(b'changed')
    with pytest.raises(PreviewUnavailable):preview(jobs.inputs,record['id'],record['space_id'])


@pytest.mark.parametrize('user,allowed',[('usr_local_test',False),('usr_other',False),('usr_engineer',True),('usr_manager',True)])
def test_http_preview_permissions_and_params(secured,user,allowed):
    _,client,_,_,jobs,_,spaces,*_=secured;root=specimen(jobs.root.parent)
    record=jobs.inputs.register('cloud',root,space_id=spaces[0]['id'],format='ply_pointcloud')
    url='/api/inputs/'+record['id']+'/preview';params={'space_id':spaces[0]['id']}
    assert client.get(url,params=params).status_code==401
    headers,_=sign_in(secured,user);response=client.get(url,params=params)
    assert response.status_code==(200 if allowed else 403),response.text
    assert client.get(url,params={'space_id':spaces[1]['id']}).status_code==403
    assert client.get(url).status_code==403
    assert client.post(url,json=params,headers=headers).status_code==403
    if allowed:
        assert response.headers['cache-control']=='no-store'
        assert client.get(url,params=params|{'path':'elsewhere'}).status_code==422
        (root/'cloud.ply').unlink();assert client.get(url,params=params).status_code==409
    response=client.get('/api/build-preview',params={'space_id':spaces[0]['id'],'candidate_id':'build-one','kind':'model'})
    assert response.status_code==(409 if allowed else 403)
    assert client.get('/api/build-preview',params={'space_id':spaces[1]['id'],'candidate_id':'build-one','kind':'model'}).status_code==403


def test_real_stages_preview_never_drives_worker_and_survives_missing_source(tmp_path,monkeypatch):
    _,jobs,_,spaces,_=prepared(tmp_path);root=specimen(tmp_path);declared(root)
    record=jobs.inputs.register('cloud',root,space_id=spaces[0]['id'],format='ply_pointcloud')
    job=jobs.start(record['id'],spaces[0]['id']);identity=job['id']
    with pytest.raises(PreviewUnavailable):build_preview(jobs,spaces[0]['id'],identity,'model')
    for _ in range(300):
        job=next(j for j in jobs.list() if j['id']==identity)
        if job['state'] not in ('queued','running'):break
        time.sleep(.05)
    assert job['state']=='succeeded',job
    before=files(tmp_path);monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('preview cannot drive workers'))
    for kind in ('model','human','agent'):
        result=build_preview(jobs,spaces[0]['id'],identity,kind)
        from jsonschema import Draft202012Validator
        Draft202012Validator(json.loads(Path('contracts/schemas/build-preview-v0.1.schema.json').read_bytes())).validate(result)
        assert result['kind']==kind and result['source_sha256']==job['frozen_model']['source_model_sha256']
        assert result['point_count']>0 and result['space_id']==spaces[0]['id']
    assert files(tmp_path)==before
    (root/'cloud.ply').unlink();assert build_preview(jobs,spaces[0]['id'],identity,'model')['point_count']==2
    ref=job['view_tasks']['agent'];path=jobs.root/ref['job_id']/'views'/ref['task_id']/'task.json'
    task=json.loads(path.read_bytes());task['state']='failed';path.write_text(json.dumps(task))
    with pytest.raises(PreviewUnavailable,match='not_ready'):build_preview(jobs,spaces[0]['id'],identity,'agent')
    assert build_preview(jobs,spaces[0]['id'],identity,'model')['point_count']==2
    (jobs.root/identity/'frozen/spatial.npz').write_bytes(b'changed')
    with pytest.raises(PreviewUnavailable):build_preview(jobs,spaces[0]['id'],identity,'model')


@pytest.mark.parametrize('state',['running','failed','interrupted'])
def test_frozen_and_other_view_available_before_candidate_ready(tmp_path,monkeypatch,state):
    from test_preview_derivations import fixture
    _,jobs,_,spaces,job,_,_=fixture(tmp_path,monkeypatch,'agent')
    space=spaces[0]['id'];ref=job['view_tasks']['agent'];path=jobs.root/ref['job_id']/'views'/ref['task_id']/'task.json'
    task=json.loads(path.read_bytes());task['state']=state;path.write_text(json.dumps(task))
    saved=json.loads((jobs.root/job['id']/'job.json').read_bytes());saved['state']='running' if state=='running' else 'views_failed';jobs.save(saved)
    before=files(tmp_path);monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('preview must not poll'))
    assert build_preview(jobs,space,job['id'],'model')['point_count']==2
    assert build_preview(jobs,space,job['id'],'human')['task_id']==job['view_tasks']['human']['task_id']
    with pytest.raises(PreviewUnavailable,match='not_ready'):build_preview(jobs,space,job['id'],'agent')
    assert files(tmp_path)==before
