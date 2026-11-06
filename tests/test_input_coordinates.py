import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest
from pydantic import ValidationError
from packages.data.input_coordinates import InputCoordinates, CoordinateChange, CoordinatesConflict, CoordinatesUnavailable
from packages.data.input_uploads import InputUploads
from packages.data.preview_inputs import PreviewInputs
from packages.data.preflight_records import PreflightRecords
from packages.data.preview_preflight import preflight
from packages.data.input_facts import facts
from packages.data.input_preview import preview
from packages.construction.preview_pointcloud import build
from packages.data.preview_batches import PreviewBatches, BatchDraft, BatchChange, checksum, batch_binding
from experiments.scripts.pack_input_upload import pack
from test_preview_pointcloud import specimen
from test_pointcloud_preparation import declared
from test_input_uploads import catalog_at
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def setup(tmp_path):
    root=specimen(tmp_path,True);declared(root)
    catalog,spaces=catalog_at(tmp_path);bundle=tmp_path/'cloud.zip';pack(root,None,bundle,'ply_pointcloud')
    result=InputUploads(catalog).register(bundle,spaces[0],'PLY','actor')
    record=catalog.read(result['input']['id']);store=InputCoordinates(catalog)
    return catalog,spaces,record,store,bundle


def change(record,**kwargs):
    return CoordinateChange(**({'space_id':record['space_id'],'expected_revision':0,'request_id':'a'*32,
        'coordinates':{k:record[k] for k in ('unit','frame_id','axes','scope','scene_alignment')}|{'frame_id':'corrected/local'},
        'reason':'纠正填写错误'}|kwargs))


def test_stable_identity_history_preflight_and_fixed_models(tmp_path):
    catalog,spaces,original,store,bundle=setup(tmp_path);identity=original['id'];space=spaces[0]
    raw={p.name:p.read_bytes() for p in __import__('pathlib').Path(original['snapshot']).iterdir()}
    first=build(original['snapshot'],tmp_path/'before','before',original)
    checks=PreflightRecords(catalog);checks.save(identity,preflight(catalog,identity),'actor',checks.fingerprint(identity))
    state=store.change(identity,change(original),'usr_engineer');effective=catalog.resolve(identity)
    assert len(catalog.list())==1 and effective['id']==identity and effective['frame_id']=='corrected/local'
    assert state['history'][0]['actor']=='usr_engineer' and state['history'][0]['before']['frame_id']==original['frame_id']
    assert not checks.latest(identity)['registration_matches']
    assert preflight(catalog,identity)['status']=='passed'
    assert facts(catalog,identity,space)['fields']['frame_id']['value']=='corrected/local'
    assert preview(catalog,identity,space)['frame_id']=='corrected/local'
    second=build(original['snapshot'],tmp_path/'after','after',effective)
    assert first['frame_id']==original['frame_id'] and second['frame_id']=='corrected/local'
    assert second['source']['input_binding']['coordinate_revision']==effective['coordinate_revision']
    with np.load(tmp_path/'before/spatial.npz') as a,np.load(tmp_path/'after/spatial.npz') as b:
        np.testing.assert_array_equal(a['points'],b['points']);np.testing.assert_array_equal(a['colors'],b['colors'])
    assert {p.name:p.read_bytes() for p in __import__('pathlib').Path(original['snapshot']).iterdir()}==raw
    assert catalog.read_original(identity)==original
    assert PreviewInputs(catalog.root,catalog.directory).resolve(identity)==effective
    assert not InputUploads(catalog).register(bundle,space,'same','actor')['created']
    assert len(catalog.list())==1


def test_audited_revisions_match_historical_artifacts_and_admission(tmp_path):
    from packages.construction.preview_jobs import PreviewJobs
    from packages.service.preview_publications import PreviewPublications
    from packages.data.preview_artifacts import artifact_catalog
    from packages.construction.preview_changes import compare_models
    from packages.lifecycle.preview_scope import owned
    from test_real_model_preview import make_preview
    from packages.construction.preview_model import PreviewModel
    catalog,spaces,original,store,_=setup(tmp_path)
    jobs=PreviewJobs(tmp_path/'builds',original['snapshot'],tmp_path/'none',catalog)
    # Historical binding recognition is separate from admission of the current revision.
    store.change(original['id'],change(original),'actor')
    assert InputCoordinates(catalog).fixed_records(original)==[original,catalog.read(original['id'])]
    with pytest.raises(ValueError,match='confirmation_required'):jobs.start(original['id'],spaces[0])
    with pytest.raises(ValueError,match='coordinate_revision_changed'):jobs.start(original['id'],spaces[0],input_revision=0)
    with pytest.raises(ValueError,match='preflight_required'):jobs.start(original['id'],spaces[0],input_revision=1)
    assert catalog.resolve(original['id'])['coordinate_revision']['revision']==1


def test_idempotent_retry_noop_conflict_and_concurrency(tmp_path):
    catalog,_,original,store,_=setup(tmp_path);request=change(original)
    saved=store.change(original['id'],request,'actor')
    assert store.change(original['id'],request,'actor')==saved
    with pytest.raises(CoordinatesConflict):store.change(original['id'],change(original,reason='other'),'actor')
    with pytest.raises(CoordinatesConflict):store.change(original['id'],change(original,request_id='b'*32),'actor')
    assert store.change(original['id'],change(original,expected_revision=1,request_id='c'*32),'actor')==saved
    def run(i):
        try:return store.change(original['id'],change(original,expected_revision=1,request_id=str(i)*32,coordinates=request.coordinates.model_dump()|{'frame_id':f'new{i}'}),'actor')['revision']
        except CoordinatesConflict:return 'conflict'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,[1,2]))
    assert sorted(map(str,results))==['2','conflict']


def test_sealed_batch_remains_bound_to_old_revision(tmp_path):
    catalog,spaces,original,store,_=setup(tmp_path);batches=PreviewBatches(catalog);space=spaces[0]
    batch=batches.create(BatchDraft(space_id=space,name='sample',origin='imported_sample',note='test'))
    batch=batches.change(batch['id'],BatchChange(space_id=space,expected_revision=0,operation='replace_members',reason='test',input_ids=[original['id']]))
    batch=batches.change(batch['id'],BatchChange(space_id=space,expected_revision=1,operation='seal',reason='test'))
    store.change(original['id'],change(original),'actor')
    assert batch_binding(batch,original,2)['input_record_sha256']==checksum(original)
    with pytest.raises(ValueError,match='batch_input_record_changed'):batch_binding(batch,catalog.read(original['id']),2)
    assert batches.read(batch['id'],space)['members']==batch['members']


@pytest.mark.parametrize('patch',[{'unit':'mm'},{'scene_alignment':'verified'},{'scope':'global'},{'frame_id':''},{'axes':['x','x','z']},{'axes':['x','y','!']}])
def test_invalid_coordinates_rejected(tmp_path,patch):
    _,_,original,store,_=setup(tmp_path)
    with pytest.raises((ValueError,ValidationError)):store.change(original['id'],change(original,coordinates=change(original).coordinates.model_dump()|patch),'actor')


def test_corruption_and_scope_fail_closed(tmp_path):
    catalog,spaces,original,store,_=setup(tmp_path)
    with pytest.raises(PermissionError):store.read(original['id'],spaces[1])
    store.change(original['id'],change(original),'actor')
    with sqlite3.connect(store.path) as db:
        event=json.loads(db.execute('SELECT record FROM revisions').fetchone()[0]);event['coordinates']['frame_id']='tampered'
        db.execute('UPDATE revisions SET record=?',(json.dumps(event),))
    with pytest.raises(CoordinatesUnavailable):catalog.read(original['id'])


@pytest.mark.parametrize('user,allowed',[('usr_local_test',False),('usr_other',False),('usr_engineer',True),('usr_manager',True)])
def test_secured_coordinate_api(secured,tmp_path,user,allowed):
    _,client,_,_,jobs,_,spaces,*_=secured
    root=specimen(tmp_path);declared(root);record=jobs.inputs.register('PLY',root,None,spaces[0]['id'],'ply_pointcloud')
    headers,_=sign_in(secured,user);url=f"/api/inputs/{record['id']}/coordinates";params={'space_id':spaces[0]['id']}
    response=client.get(url,params=params);assert response.status_code==(200 if allowed else 403),response.text
    response=client.post(url,json=change(record).model_dump(),headers=headers)
    assert response.status_code==(200 if allowed else 403),response.text
    if allowed:
        assert response.json()['history'][0]['actor']==user
        assert client.get(url,params={'space_id':spaces[1]['id']}).status_code==403
        assert client.post(url,json=change(record).model_dump()|{'actor':'forged'},headers=headers).status_code==422
