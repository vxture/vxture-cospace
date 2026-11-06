import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import pytest
from pydantic import ValidationError
from packages.data.input_descriptions import InputDescriptions, DescriptionChange, DescriptionConflict, DescriptionUnavailable
from packages.data.input_facts import facts, FactsUnavailable
from packages.data.preview_preflight import preflight
from packages.data.preflight_records import PreflightRecords
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_preview_batches import prepared, sealed, files
from test_preview_lidar import specimen
from packages.construction.preview_model import digest


def request(space, **kwargs):
    return dict(space_id=space, expected_revision=0, display_name='设备间资料', description='流程样本', intended_use='局部构建', reason='整理资料') | kwargs


def test_lazy_reads_revision_history_restart_and_binding(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path)
    record=records[0];identity=record['id'];space=spaces[0]['id'];store=InputDescriptions(jobs.inputs)
    baseline=files(tmp_path)
    initial=store.read(identity,space)
    assert initial['revision']==0 and initial['display_name']==record['label'] and files(tmp_path)==baseline
    batch=sealed(jobs,space,identity);batch=jobs.batches.read(batch['id'],space);fingerprint=PreflightRecords(jobs.inputs).fingerprint(identity)
    saved=store.change(identity,DescriptionChange(**request(space)),'usr_engineer')
    assert saved['revision']==1 and saved['history'][0]['before']['display_name']==record['label']
    assert saved['history'][0]['actor']=='usr_engineer' and saved['history'][0]['changed_at'].endswith('+00:00')
    assert InputDescriptions(jobs.inputs).read(identity,space)==saved
    assert store.change(identity,DescriptionChange(**request(space,expected_revision=1)),'usr_engineer')==saved
    with pytest.raises(DescriptionConflict):store.change(identity,DescriptionChange(**request(space)),'usr_other')
    assert jobs.inputs.resolve(identity)==record
    assert PreflightRecords(jobs.inputs).fingerprint(identity)==fingerprint
    assert preflight(jobs.inputs,identity)['status']=='passed'
    assert jobs.batches.read(batch['id'],space)==batch


def test_concurrent_changes_have_one_winner(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);store=InputDescriptions(jobs.inputs)
    def save(i):
        try:return store.change(records[0]['id'],DescriptionChange(**request(spaces[0]['id'],display_name=str(i))),'actor')['revision']
        except DescriptionConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(save,[1,2]))
    assert sorted(map(str,out))==['1','conflict']


@pytest.mark.parametrize('changes',[{'display_name':''},{'display_name':'   '},{'display_name':'x'*101},{'description':'x'*501},{'intended_use':'x'*501},{'reason':''},{'expected_revision':True},{'actor':'forged'},{'space_id':'unknown'}])
def test_invalid_description(changes):
    with pytest.raises(ValidationError):DescriptionChange(**request('space-'+'a'*16,**changes))


def test_scope_and_corruption_fail_closed(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);store=InputDescriptions(jobs.inputs)
    with pytest.raises(PermissionError):store.read(records[0]['id'],spaces[1]['id'])
    store.path.write_bytes(b'broken')
    with pytest.raises(DescriptionUnavailable):store.read(records[0]['id'],spaces[0]['id'])
    with pytest.raises(DescriptionUnavailable):store.change(records[0]['id'],DescriptionChange(**request(spaces[0]['id'])),'actor')


def test_semantic_record_corruption_rejected(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);store=InputDescriptions(jobs.inputs)
    store.change(records[0]['id'],DescriptionChange(**request(spaces[0]['id'])),'actor')
    with sqlite3.connect(store.path) as db:
        value=json.loads(db.execute('SELECT record FROM descriptions').fetchone()[0]);value['display_name']='tampered'
        db.execute('UPDATE descriptions SET record=?',(json.dumps(value),))
    with pytest.raises(DescriptionUnavailable):store.read(records[0]['id'],spaces[0]['id'])


def test_facts_rgbd_missing_timestamps_do_not_invent_utc(tmp_path,monkeypatch):
    _,jobs,_,spaces,records=prepared(tmp_path);record=records[0];before=files(tmp_path)
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *_:pytest.fail('facts must not decode payloads'))
    report=facts(jobs.inputs,record['id'],spaces[0]['id'])
    assert report['fields']['unit']['value']=='m' and report['fields']['frame_id']['value']=='first_depth_camera_anchor'
    assert report['fields']['image_window_us']['status']=='unknown'
    assert report['fields']['utc_sync']['status']==report['fields']['epsg']['status']=='unknown'
    assert not report['payload_checked'] and files(tmp_path)==before


def test_facts_lidar_precise_integer_strings_and_manifest_only(tmp_path):
    _,jobs,_,spaces,_=prepared(tmp_path)
    root=specimen(tmp_path);record=jobs.inputs.register('lidar',root,space_id=spaces[0]['id'],format='ros1_lidar_single_frame')
    report=facts(jobs.inputs,record['id'],spaces[0]['id'])
    assert report['fields']['sensor_header_ns']['value']=='100000000000'
    assert report['fields']['frame_id']['value']=='lidar'
    assert report['roles'][1]['use']=='仅核对消息，不参与融合'
    (root/'sample.bag').write_bytes(b'changed payload')
    assert facts(jobs.inputs,record['id'],spaces[0]['id'])['payload_checked'] is False
    assert preflight(jobs.inputs,record['id'])['status']=='failed'


@pytest.mark.parametrize('problem',['missing','changed','oversized'])
def test_facts_source_errors_do_not_return_stale_success(tmp_path,problem):
    _,jobs,_,spaces,records=prepared(tmp_path);record=records[0];path=Path(record['snapshot'])/'report.json'
    facts(jobs.inputs,record['id'],spaces[0]['id'])
    if problem=='missing':path.unlink()
    elif problem=='changed':path.write_bytes(b'{}')
    else:path.write_bytes(b' '*2_000_001)
    with pytest.raises(FactsUnavailable):facts(jobs.inputs,record['id'],spaces[0]['id'])


@pytest.mark.parametrize('user,allowed',[('usr_local_test',False),('usr_other',False),('usr_engineer',True),('usr_manager',True)])
def test_authorization_and_csrf(secured,user,allowed):
    _,client,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured,user)
    identity=next(r['id'] for r in jobs.inputs.list() if r['space_id']==spaces[0]['id'])
    base='/api/inputs/'+identity;query={'space_id':spaces[0]['id']}
    before=files(jobs.inputs.root)
    for suffix in ('description','facts'):
        response=client.get(base+'/'+suffix,params=query)
        assert response.status_code==(200 if allowed else 403),response.text
        assert client.get(base+'/'+suffix,params={'space_id':spaces[1]['id']}).status_code==403
        assert client.get(base+'/'+suffix).status_code==403
    assert files(jobs.inputs.root)==before
    assert client.post(base+'/description',json=request(spaces[0]['id'])).status_code==403
    response=client.post(base+'/description',json=request(spaces[0]['id']),headers=headers)
    assert response.status_code==(200 if allowed else 403),response.text
    assert client.post(base+'/facts',json=request(spaces[0]['id']),headers=headers).status_code==403
    if allowed:
        assert response.json()['history'][0]['actor']==user
        assert client.post(base+'/description',json=request(spaces[0]['id']),headers=headers).status_code==409
        assert client.post(base+'/description',json=request(spaces[0]['id'],expected_revision=1,display_name=''),headers=headers).status_code==422


def test_authorized_list_workflow_and_corrupt_store(secured):
    _,client,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured,'usr_engineer');space=spaces[0]['id']
    record=next(r for r in jobs.inputs.list() if r['space_id']==space);identity=record['id']
    original=jobs.inputs.read(identity)
    assert client.post('/api/inputs/'+identity+'/description',json=request(space),headers=headers).status_code==200
    row=next(r for r in client.get('/api/inputs',params={'space_id':space}).json()['inputs'] if r['id']==identity)
    assert row['label']==record['label'] and row['presentation']['display_name']=='设备间资料'
    workflow=client.get('/api/workflow',params={'space_id':space,'input_id':identity})
    assert workflow.status_code==200,workflow.text
    row=next(r for r in workflow.json()['preparation']['inputs'] if r['input_id']==identity)
    assert row['presentation']['display_name']=='设备间资料'
    assert jobs.inputs.resolve(identity)==original
    store=InputDescriptions(jobs.inputs);store.path.write_bytes(b'broken')
    assert client.get('/api/inputs',params={'space_id':space}).status_code==503
    assert client.get('/api/workflow',params={'space_id':space}).status_code==503
    assert client.get('/api/inputs/'+identity+'/description',params={'space_id':space}).status_code==503
    # A display metadata failure cannot revoke a historical publication.
    assert client.get('/publications/'+secured[-1]['id']+'/api/preview').status_code==200


def test_changed_workspace_rejects_description(secured):
    _,client,accounts,_,jobs,_,spaces,*_=secured;sign_in(secured,'usr_engineer')
    record=jobs.inputs.list()[0];accounts.workspace='ws_other';headers,_=sign_in(secured,'usr_engineer')
    assert client.get('/api/inputs/'+record['id']+'/description',params={'space_id':record['space_id']}).status_code==403
    assert client.post('/api/inputs/'+record['id']+'/description',json=request(record['space_id']),headers=headers).status_code==403


def test_preparation_matches_pathless_fixed_binding_after_description_change(tmp_path):
    from packages.service.space_preparation import preparation
    from packages.data.space_sources import SpaceSources
    _,jobs,_,spaces,records=prepared(tmp_path);record=records[0];space=spaces[0]['id']
    path=jobs.root/'build-pathless';path.mkdir()
    (path/'job.json').write_text(json.dumps({'id':'build-pathless','space_id':space,'input_id':record['id'],
        'state':'succeeded','input_binding':{k:v for k,v in record.items() if k not in ('snapshot','tracking')}}))
    InputDescriptions(jobs.inputs).change(record['id'],DescriptionChange(**request(space)),'actor')
    row=preparation(jobs,SpaceSources(tmp_path/'sources',{}),space,record['id'])['inputs'][0]
    assert row['saved_build_counts']['succeeded']==1
    assert row['label']==record['label'] and row['presentation']['display_name']=='设备间资料'
