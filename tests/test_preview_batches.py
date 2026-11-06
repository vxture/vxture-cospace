import json
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import pytest
from jsonschema import Draft202012Validator,FormatChecker
from pathlib import Path
from fastapi.testclient import TestClient
from packages.data.preview_batches import PreviewBatches,BatchDraft,BatchChange,batch_results
from packages.data.preview_inputs import PreviewInputs
from packages.construction.preview_jobs import PreviewJobs
from packages.lifecycle.preview_scope import scope
from packages.service.preview_publications import PreviewPublications
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_space_flow import setup
from test_preview_inputs import source

def prepared(tmp_path):
    initial,jobs,directory,spaces=setup(tmp_path)
    snapshot,tracking=source(tmp_path);inputs=PreviewInputs(tmp_path/'inputs',directory)
    records=[inputs.register('sample '+str(i),snapshot,tracking,s['id']) for i,s in enumerate(spaces)]
    jobs.inputs=inputs;jobs.batches=PreviewBatches(inputs)
    return initial,jobs,directory,spaces,records

def create(jobs,space):return jobs.batches.create(BatchDraft(space_id=space,name='导入测试',origin='imported_sample',note='非现场采集'))

def change(store,record,operation,**values):
    return store.change(record['id'],BatchChange(space_id=record['space_id'],expected_revision=record['revision'],operation=operation,reason='流程核对',**values))

def sealed(jobs,space,input_id):
    record=create(jobs,space);record=change(jobs.batches,record,'replace_members',input_ids=[input_id]);return change(jobs.batches,record,'seal')

def files(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

def test_reads_lazy_no_migration_and_legacy_unaffected(tmp_path):
    initial,jobs,directory,spaces,records=prepared(tmp_path);before=files(tmp_path)
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        assert client.get('/api/batches',params={'space_id':spaces[0]['id']}).json()['batches']==[]
        assert client.get('/api/batches').status_code==422
        assert client.get('/api/batches?space_id=unknown').status_code==404
    assert files(tmp_path)==before and not jobs.batches.path.exists()

def test_batch_seal_membership_freeze_disable_restore_history(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);r=sealed(jobs,spaces[0]['id'],records[0]['id']);digest=r['sealed_members_sha256']
    with pytest.raises(ValueError,match='members_frozen'):change(jobs.batches,r,'replace_members',input_ids=[])
    off=change(jobs.batches,r,'disable');assert off['resume_state']=='sealed'
    restored=change(jobs.batches,off,'restore');assert restored['state']=='sealed' and restored['sealed_members_sha256']==digest
    restarted=PreviewBatches(jobs.inputs);saved=restarted.read(r['id'],spaces[0]['id'])
    assert [h['revision'] for h in saved['history']]==list(range(5))
    assert saved['members']==r['members'] and saved['history'][2]['state']=='sealed'
    schema=json.loads(Path('contracts/schemas/preview-batch-v0.1.schema.json').read_bytes());validator=Draft202012Validator(schema,format_checker=FormatChecker())
    for event in saved['history']:validator.validate(event)

def test_draft_disable_restore_and_empty_seal_rejected(tmp_path):
    _,jobs,_,spaces,_=prepared(tmp_path);r=create(jobs,spaces[0]['id'])
    with pytest.raises(ValueError,match='nonempty_draft'):change(jobs.batches,r,'seal')
    off=change(jobs.batches,r,'disable');restored=change(jobs.batches,off,'restore');assert restored['state']=='draft'
    with pytest.raises(ValueError,match='not_disabled'):change(jobs.batches,restored,'restore')
    assert len(jobs.batches.read(r['id'],spaces[0]['id'])['history'])==3

@pytest.mark.parametrize('case',['foreign','duplicate','missing'])
def test_member_failures_leave_history_unchanged(tmp_path,case):
    _,jobs,_,spaces,records=prepared(tmp_path);r=create(jobs,spaces[0]['id'])
    ids={'foreign':[records[1]['id']],'duplicate':[records[0]['id']]*2,'missing':['input-'+'0'*16]}[case]
    with pytest.raises(ValueError):change(jobs.batches,r,'replace_members',input_ids=ids)
    current=jobs.batches.read(r['id'],spaces[0]['id']);assert current['revision']==0 and len(current['history'])==1 and current['members']==[]

@pytest.mark.parametrize('case',['source','record'])
def test_seal_rechecks_source_and_registration_rolls_back(tmp_path,case):
    _,jobs,_,spaces,records=prepared(tmp_path);r=create(jobs,spaces[0]['id']);r=change(jobs.batches,r,'replace_members',input_ids=[records[0]['id']])
    if case=='source':(tmp_path/'snapshot/raw/d.pgm').write_bytes(b'bad')
    else:
        path=jobs.inputs.root/(records[0]['id']+'.json');value=json.loads(path.read_bytes());value['label']='changed';path.write_text(json.dumps(value))
    with pytest.raises(ValueError):change(jobs.batches,r,'seal')
    current=jobs.batches.read(r['id'],spaces[0]['id']);assert current['state']=='draft' and current['revision']==1

def test_compare_and_swap_concurrent_updates_commit_exactly_one(tmp_path):
    _,jobs,_,spaces,_=prepared(tmp_path);r=create(jobs,spaces[0]['id']);start=threading.Barrier(2)
    def worker():
        start.wait()
        try:return change(PreviewBatches(jobs.inputs),r,'disable')['revision']
        except ValueError as e:return str(e)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:worker(),range(2)))
    assert sorted(map(str,results))==['1','batch_changed_refresh_required']
    assert len(jobs.batches.read(r['id'],spaces[0]['id'])['history'])==2

def test_admission_rejects_disabled_missing_and_stale_batch_without_job(tmp_path,monkeypatch):
    _,jobs,_,spaces,records=prepared(tmp_path);space=spaces[0]['id'];r=sealed(jobs,space,records[0]['id'])
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**k:pytest.fail('no subprocess for rejected admission'))
    before=files(jobs.root)
    for batch,revision in [(None,None),(r['id'],r['revision']-1)]:
        with pytest.raises(ValueError):jobs.start(records[0]['id'],space,batch,revision)
    off=change(jobs.batches,r,'disable')
    for batch,revision in [(off['id'],off['revision']),(None,None)]:
        with pytest.raises(ValueError):jobs.start(records[0]['id'],space,batch,revision)
    assert files(jobs.root)==before

def test_admission_orders_disable_after_launch_and_does_not_cancel(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);space=spaces[0]['id'];r=sealed(jobs,space,records[0]['id']);started=threading.Event()
    def disable():started.set();return change(PreviewBatches(jobs.inputs),r,'disable')
    with ThreadPoolExecutor(1) as pool:
        with jobs.batches.admit(jobs.inputs.resolve(records[0]['id']),scope(jobs.directory,space),r['id'],r['revision']) as ref:
            future=pool.submit(disable);assert started.wait(2);time.sleep(.05);assert not future.done();assert ref['batch_id']==r['id']
        assert future.result(timeout=5)['state']=='disabled'

def test_member_shared_with_another_sealed_batch_requires_explicit_choice(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);space=spaces[0]['id'];one=sealed(jobs,space,records[0]['id']);two=sealed(jobs,space,records[0]['id']);change(jobs.batches,one,'disable')
    with jobs.batches.admit(records[0],scope(jobs.directory,space),two['id'],two['revision']) as ref:assert ref['batch_id']==two['id']

def test_batch_results_reads_no_poll_and_no_retroactive_claim(tmp_path,monkeypatch):
    _,jobs,_,spaces,records=prepared(tmp_path);r=sealed(jobs,spaces[0]['id'],records[0]['id']);pubs=PreviewPublications(jobs)
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('must not poll'));before=files(tmp_path)
    report=batch_results(jobs.batches,jobs,pubs,r['id'],spaces[0]['id']);assert report['attempts']==report['publications']==[]
    assert files(tmp_path)==before

def test_api_strict_fields_scope_origin_and_store_corruption(tmp_path):
    initial,jobs,directory,spaces,records=prepared(tmp_path);space=spaces[0]['id']
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        body={'space_id':space,'name':'sample','origin':'imported_sample','note':'test'}
        assert client.post('/api/batches',json=body|{'extra':1}).status_code==422
        assert client.post('/api/batches',json=body,headers={'Origin':'https://other.invalid'}).status_code==403
        response=client.post('/api/batches',json=body);assert response.status_code==201;r=response.json()
        transition={'space_id':space,'operation':'disable','reason':'test','expected_revision':0}
        assert client.post('/api/batches/'+r['id']+'/transitions',json=transition|{'expected_revision':False}).status_code==422
        assert client.post('/api/batches/'+r['id']+'/transitions',json=transition|{'input_ids':[]}).status_code==409
        assert client.get('/api/batches/'+r['id'],params={'space_id':spaces[1]['id']}).status_code==409
        assert client.get('/api/batches',params={'space_id':spaces[1]['id']}).json()['batches']==[]
        jobs.batches.path.write_bytes(b'not a database')
        assert client.get('/api/batches',params={'space_id':space}).status_code==409

def test_corrupt_current_record_is_not_silently_accepted(tmp_path):
    _,jobs,_,spaces,_=prepared(tmp_path);r=create(jobs,spaces[0]['id'])
    with jobs.batches.connection(True) as db:
        value=r|{'state':'sealed'};db.execute('UPDATE batches SET record=? WHERE id=?',(json.dumps(value),r['id']))
    with pytest.raises(ValueError,match='history_mismatch'):jobs.batches.list(spaces[0]['id'])

@pytest.mark.parametrize('outcome',['launch_failure','failed','interrupted'])
def test_failed_or_interrupted_attempt_retains_batch_reference(tmp_path,monkeypatch,outcome):
    _,jobs,_,spaces,records=prepared(tmp_path);space=spaces[0]['id'];r=sealed(jobs,space,records[0]['id'])
    class Process:
        def poll(self):return 1 if outcome=='failed' else None
    def launch(*a,**kw):
        if outcome=='launch_failure':raise OSError('simulated launcher failure')
        return Process()
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',launch)
    attempt=jobs.start(records[0]['id'],space,r['id'],r['revision'])
    if outcome=='failed':jobs.list()
    if outcome=='interrupted':
        process,_,log=jobs.active.pop(attempt['id']);log.close()
        jobs=PreviewJobs(jobs.root,tmp_path/'unused',tmp_path/'unused',jobs.inputs);jobs.directory=jobs.inputs.directory
    report=batch_results(jobs.batches,jobs,PreviewPublications(jobs),r['id'],space)
    saved=next(j for j in report['attempts'] if j['id']==attempt['id'])
    assert saved['batch_ref']['batch_id']==r['id'] and saved['state']==('interrupted' if outcome=='interrupted' else 'failed')

def test_changed_sealed_input_rejects_new_admission(tmp_path):
    _,jobs,_,spaces,records=prepared(tmp_path);space=spaces[0]['id'];r=sealed(jobs,space,records[0]['id'])
    changed=records[0]|{'label':'modified after sealing'}
    with pytest.raises(ValueError,match='input_record_changed'):
        with jobs.batches.admit(changed,scope(jobs.directory,space),r['id'],r['revision']):pytest.fail('must reject')
