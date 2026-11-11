"""Recovery must preserve admission, identity, and history across repeated requests."""
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import threading
import pytest
from fastapi.testclient import TestClient
from experiments.scripts.serve_nyu_flow_preview import create_app
from packages.construction.preview_jobs import PreviewJobs
from packages.lifecycle.preview_control import ControlChange
from packages.service.preview_publications import PreviewPublications
from test_preview_batches import prepared,sealed,change,files


def failed(tmp_path,monkeypatch):
    initial,jobs,directory,spaces,inputs=prepared(tmp_path)
    # This fixture also seeds unrelated query-only legacy candidates. Keep this
    # recovery fixture geometric-only so lifecycle analysis has complete records.
    for identity in ('build-one','build-two'):shutil.rmtree(jobs.root/identity)
    space=spaces[0]['id'];batch=sealed(jobs,space,inputs[0]['id'])
    class Process:
        def poll(self):return 1
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**kw:Process())
    job=jobs.start(inputs[0]['id'],space,batch['id'],batch['revision']);jobs.list()
    return initial,jobs,directory,spaces,inputs,batch,job


def test_retry_keeps_original_input_batch_and_failed_record(tmp_path,monkeypatch):
    _,jobs,_,spaces,inputs,batch,old=failed(tmp_path,monkeypatch)
    path=jobs.root/old['id']/'job.json';before=path.read_bytes();request='a'*32
    result=jobs.retry(spaces[0]['id'],old['id'],request);new=result['job']
    assert result['created'] and new['id']!=old['id'] and new['retry_of']==old['id']
    assert new['input_id']==inputs[0]['id'] and new['batch_ref']['admitted_revision']==batch['revision']
    assert new['input_binding']==old['input_binding'] and path.read_bytes()==before
    jobs.list()
    assert jobs.retry(spaces[0]['id'],old['id'],request)=={'created':False,'job':next(j for j in jobs.list() if j['id']==new['id'])}


def test_parallel_retries_and_restart_replay_create_one_task(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,_,old=failed(tmp_path,monkeypatch);space=spaces[0]['id'];barrier=threading.Barrier(2)
    class Running:
        def poll(self):return None
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**kw:Running())
    def worker():barrier.wait();return jobs.retry(space,old['id'],'b'*32)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:worker(),range(2)))
    assert sorted(r['created'] for r in results)==[False,True]
    assert results[0]['job']['id']==results[1]['job']['id']
    # Close the test process log without changing the running record; constructor marks it interrupted.
    for _,_,log in jobs.active.values():log.close()
    restarted=PreviewJobs(jobs.root,jobs.snapshot,jobs.tracking,jobs.inputs)
    replay=restarted.retry(space,old['id'],'b'*32)
    assert not replay['created'] and replay['job']['state']=='interrupted'
    assert len([r for r in restarted.list() if r.get('retry_of')==old['id']])==1
    with pytest.raises(ValueError,match='request_conflict'):restarted.retry(space,replay['job']['id'],'b'*32)
    interrupted_retry=restarted.retry(space,replay['job']['id'],'e'*32)
    assert interrupted_retry['created'] and interrupted_retry['job']['retry_of']==replay['job']['id']
    for _,_,log in restarted.active.values():log.close()


@pytest.mark.parametrize('condition',['disabled','archived','batch_changed','file_missing','file_changed','binding_changed','foreign','succeeded','running','unsupported'])
def test_invalid_retry_never_launches_or_mutates_old_job(tmp_path,monkeypatch,condition):
    _,jobs,_,spaces,inputs,batch,old=failed(tmp_path,monkeypatch);space=spaces[0]['id'];record=jobs.list()[0]
    if condition in ('disabled','archived'):
        if condition=='archived':change(jobs.batches,batch,'disable')
        pubs=PreviewPublications(jobs);report=jobs.controls.report(pubs,space,'input:'+inputs[0]['id'])
        jobs.controls.change(pubs,ControlChange(
            space_id=space,artifact='input:'+inputs[0]['id'],expected_revision=0,
            expected_snapshot_sha256=report['snapshot_sha256'],operation='disable_input' if condition=='disabled' else 'archive_input',reason='test'))
    elif condition=='batch_changed':change(jobs.batches,batch,'disable')
    elif condition=='file_missing':(tmp_path/'snapshot/raw/d.pgm').unlink()
    elif condition=='file_changed':(tmp_path/'snapshot/raw/d.pgm').write_bytes(b'changed')
    elif condition=='binding_changed':
        path=jobs.inputs.root/(inputs[0]['id']+'.json');value=json.loads(path.read_bytes());value['label']='changed';path.write_text(json.dumps(value))
    elif condition=='foreign':space=spaces[1]['id']
    elif condition in ('succeeded','running'):record['state']=condition;jobs.save(record)
    elif condition=='unsupported':record['method']='semantic_annotation';jobs.save(record)
    before=files(jobs.root)
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**kw:pytest.fail('rejected retry must not launch'))
    with pytest.raises((ValueError,OSError)):jobs.retry(space,old['id'],'c'*32)
    assert files(jobs.root)==before


def test_retry_api_rejects_bad_scope_fields_and_origin(tmp_path,monkeypatch):
    initial,jobs,directory,spaces,_,_,old=failed(tmp_path,monkeypatch)
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        body={'space_id':spaces[0]['id'],'retry_of':old['id'],'request_id':'d'*32}
        assert client.post('/api/build-retries',json=body,headers={'Origin':'https://other.invalid'}).status_code==403
        for change_body in ({'extra':True},{'request_id':'bad'},{'retry_of':'../outside'}):
            assert client.post('/api/build-retries',json=body|change_body).status_code==422
        assert client.post('/api/build-retries',json=body|{'space_id':spaces[1]['id']}).status_code==409
        response=client.post('/api/build-retries',json=body);assert response.status_code==202,response.text
        again=client.post('/api/build-retries',json=body);assert again.status_code==200
        assert response.json()['job']['id']==again.json()['job']['id']
        jobs.list()


def test_build_description_is_saved_with_new_job(tmp_path,monkeypatch):
    _,jobs,_,spaces,inputs,batch,previous=failed(tmp_path,monkeypatch)
    info={'name':' 东侧更新 ','purpose':'导航验证','changes':'补充设备间点云'}
    job=jobs.start(inputs[0]['id'],spaces[0]['id'],batch['id'],batch['revision'],build_info=info)
    saved=json.loads((jobs.root/job['id']/'job.json').read_bytes())
    assert saved['build_info']==dict(info,name='东侧更新')
    assert 'build_info' not in json.loads((jobs.root/previous['id']/'job.json').read_bytes())
    for bad in ({'name':'x'*101},{'purpose':7},{'unexpected':'value'}):
        with pytest.raises(ValueError,match='build_info_invalid'):
            jobs.start(build_info=bad)


def test_edit_build_description_preserves_artifacts_and_checks_revision(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,_,job=failed(tmp_path,monkeypatch)
    before=json.loads((jobs.root/job['id']/'job.json').read_bytes())
    result=jobs.update_info(spaces[0]['id'],job['id'],{'name':'验证构建','purpose':'验证','changes':''},0)
    assert result['revision']==1
    after=json.loads((jobs.root/job['id']/'job.json').read_bytes())
    assert {k:v for k,v in after.items() if not k.startswith('build_info')}==before
    assert after['build_info_history'][0]['after']==result['build_info']
    with pytest.raises(ValueError,match='build_info_revision_changed'):
        jobs.update_info(spaces[0]['id'],job['id'],{},0)
    with pytest.raises(ValueError):
        jobs.update_info('space-other',job['id'],{},1)
