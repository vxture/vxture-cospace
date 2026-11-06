import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import pytest
from fastapi.testclient import TestClient
from packages.lifecycle.preview_control import ControlChange,PreviewControls
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.lifecycle.preview_scope import scope
from packages.data.preview_batches import BatchDraft,BatchChange
from packages.construction.preview_model import digest
from packages.construction.preview_semantics import annotate
from packages.construction.preview_business import associate
from packages.construction.preview_relations import relate
from packages.spatial.preview_objects import SemanticRequest
from packages.spatial.preview_business import BusinessRequest
from packages.spatial.preview_relations import RelationRequest
from packages.service.preview_publications import PreviewPublications
from packages.data.preview_artifacts import artifact_catalog
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_impact import seed

def payload(store,pubs,space,key,op,reason='流程验证'):
    report=store.report(pubs,space,key)
    return ControlChange(space_id=space,artifact=key,operation=op,expected_revision=report['record']['revision'],expected_snapshot_sha256=report['snapshot_sha256'],reason=reason)

def run(store,pubs,space,key,op):return store.change(pubs,payload(store,pubs,space,key,op))
def inventory(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def semantic_request(jobs,store,space,candidate):
    model=jobs.model(candidate);rule=store.list()[0]
    return SemanticRequest(space_id=space,base_candidate_id=candidate,base_manifest_sha256=digest(model.root/'model.json'),ontology_ref={k:rule[k] for k in ('ontology_id','version','sha256')},objects=[{'object_id':'room-new','type_id':'room','properties':{'name':'待核实'},'point_index':0}])

def test_report_readonly_default_scope_and_schema(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);store=jobs.controls;space=spaces[0]['id'];before=inventory(tmp_path)
    report=store.report(pubs,space,'input:'+input_id)
    assert report['record']['lifecycle_state']=='active' and report['record']['revision']==0 and not store.path.exists()
    assert {a['operation'] for a in report['actions']}=={'disable_input','archive_input'}
    assert inventory(tmp_path)==before
    from jsonschema import Draft202012Validator,FormatChecker
    schema=json.loads(Path('contracts/schemas/preview-artifact-control-v0.1.schema.json').read_bytes())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(report)

def test_disable_restore_keeps_frozen_data_and_persists_history(tmp_path):
    _,jobs,_,spaces,_,pubs,_,new,input_id=seed(tmp_path);store=jobs.controls;space=spaces[0]['id'];key='input:'+input_id
    protected={str(p):p.read_bytes() for root in (jobs.root,jobs.inputs.root) for p in root.rglob('*') if p.is_file()}
    disabled=run(store,pubs,space,key,'disable_input');assert disabled['lifecycle_state']=='disabled'
    with pytest.raises(ValueError,match='disabled_new_use'):jobs.start(input_id,space)
    restored=run(store,pubs,space,key,'restore');assert restored['lifecycle_state']=='active' and restored['revision']==2
    assert len(PreviewControls(store.runtime,jobs.directory).read(space,key)['history'])==2
    assert all(Path(path).read_bytes()==raw for path,raw in protected.items())
    assert pubs.read(new['id'])[0]['candidate_id']==new['candidate_id']

def test_restore_rechecks_source_and_failed_write_keeps_state(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);store=jobs.controls;space=spaces[0]['id'];key='input:'+input_id
    run(store,pubs,space,key,'disable_input');request=payload(store,pubs,space,key,'restore')
    source=jobs.inputs.read(input_id);Path(source['snapshot']).joinpath('raw/d.pgm').write_bytes(b'changed')
    with pytest.raises(ValueError):store.change(pubs,request)
    assert store.read(space,key)['revision']==1 and store.read(space,key)['lifecycle_state']=='disabled'

def test_archived_input_restores_prior_disabled_state_and_cannot_build(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls
    raw=jobs.inputs.read(input_id);spare=jobs.inputs.register('spare',raw['snapshot'],raw['tracking'],space);key='input:'+spare['id']
    run(store,pubs,space,key,'disable_input');archived=run(store,pubs,space,key,'archive_input')
    assert archived['resume_state']=='disabled'
    with pytest.raises(ValueError,match='archived_new_use'):jobs.start(spare['id'],space)
    restored=run(store,pubs,space,key,'restore');assert restored['lifecycle_state']=='disabled'
    assert store.report(pubs,space,key)['record']['history'][-1]['operation']=='restore'

def test_current_candidate_and_source_archive_blocked(tmp_path):
    _,jobs,_,spaces,_,pubs,_,new,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls
    for key,op in [('candidate:'+new['candidate_id'],'archive_candidate'),('input:'+input_id,'archive_input')]:
        with pytest.raises(ValueError,match='operation_blocked'):run(store,pubs,space,key,op)
    assert not store.path.exists()

def test_candidate_archive_blocks_select_and_all_derivations_keeps_existing_descendants(tmp_path):
    _,jobs,_,spaces,ontologies,pubs,old,new,_=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls;base=old['candidate_id'];key='candidate:'+base
    request=semantic_request(jobs,ontologies,space,base)
    run(store,pubs,space,key,'archive_candidate')
    with pytest.raises(ValueError,match='archived_new_use'):jobs.select(base,2,space)
    with pytest.raises(ValueError,match='archived_new_use'):annotate(jobs,ontologies,request)
    model=jobs.model(base)
    with pytest.raises(ValueError,match='archived_new_use'):associate(jobs,ontologies,None,BusinessRequest(space_id=space,base_candidate_id=base,base_manifest_sha256=digest(model.root/'model.json'),bindings=[]))
    rule=ontologies.register('configs/ontology/indoor-equipment-v0.2.json')
    with pytest.raises(ValueError,match='archived_new_use'):relate(jobs,ontologies,RelationRequest(space_id=space,base_candidate_id=base,base_manifest_sha256=digest(model.root/'model.json'),ontology_ref={k:rule[k] for k in ('ontology_id','version','sha256')},relations=[]))
    assert pubs.read(old['id'])[0]['candidate_id']==base and jobs.model(new['candidate_id'])
    # Existing descendant remains available; archiving an ancestor is not cascading revocation.
    assert pubs.publish(new['candidate_id'],2,space)
    run(store,pubs,space,key,'restore');assert annotate(jobs,ontologies,request)['state']=='succeeded'

def test_archived_candidate_publish_direct_route_is_blocked_even_stale_pointer(tmp_path):
    _,jobs,_,spaces,_,pubs,old,_,_=seed(tmp_path);space=spaces[0]['id'];base=old['candidate_id']
    run(jobs.controls,pubs,space,'candidate:'+base,'archive_candidate')
    with pytest.raises(ValueError,match='archived_new_use'):pubs.publish(base,2,space)

def test_disabled_input_batch_seal_and_direct_or_batch_admission_blocked(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls
    batch=jobs.batches.create(BatchDraft(space_id=space,name='sample',origin='imported_sample',note='test'))
    batch=jobs.batches.change(batch['id'],BatchChange(space_id=space,expected_revision=0,operation='replace_members',reason='choose',input_ids=[input_id]))
    run(store,pubs,space,'input:'+input_id,'disable_input')
    with pytest.raises(ValueError,match='disabled_new_use'):jobs.batches.change(batch['id'],BatchChange(space_id=space,expected_revision=1,operation='seal',reason='seal'))
    run(store,pubs,space,'input:'+input_id,'restore')
    batch=jobs.batches.change(batch['id'],BatchChange(space_id=space,expected_revision=1,operation='seal',reason='seal'))
    run(store,pubs,space,'input:'+input_id,'disable_input')
    for params in ({},{'batch_id':batch['id'],'batch_revision':2}):
        with pytest.raises(ValueError,match='disabled_new_use'):jobs.start(input_id,space,**params)
    assert jobs.batches.read(batch['id'],space)['state']=='sealed'

def test_revision_digest_scope_origin_and_strict_request(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];key='input:'+input_id;store=jobs.controls
    request=payload(store,pubs,space,key,'disable_input');run(store,pubs,space,key,'disable_input')
    with pytest.raises(ValueError,match='changed_refresh'):store.change(pubs,request)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        assert client.get('/api/artifact-control').status_code==422
        assert client.get('/api/artifact-control',params={'space_id':spaces[1]['id'],'artifact':key}).status_code==404
        assert client.get('/api/artifact-control',params={'space_id':space,'artifact':'publication:whatever'}).status_code==422
        body=payload(store,pubs,space,key,'restore').model_dump()
        assert client.post('/api/artifact-control/transitions',json=body,headers={'Origin':'https://example.com'}).status_code==403
        assert client.post('/api/artifact-control/transitions',json=body|{'expected_revision':True}).status_code==422
        assert client.post('/api/artifact-control/transitions',json=body|{'reason':'   '}).status_code==409
        assert client.post('/api/artifact-control/transitions',json=body|{'actor':'admin'}).status_code==422
        assert client.post('/api/artifact-control/transitions',json=body).status_code==200
        assert client.post('/api/artifact-control/transitions',json=body).status_code==409

def test_digest_rejects_new_references_and_other_state_changes(tmp_path):
    _,jobs,_,spaces,_,pubs,old,_,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls;key='input:'+input_id
    request=payload(store,pubs,space,key,'disable_input')
    batch=jobs.batches.create(BatchDraft(space_id=space,name='new',origin='imported_sample',note='test'))
    with pytest.raises(ValueError,match='references_changed'):store.change(pubs,request)
    request=payload(store,pubs,space,key,'disable_input');run(store,pubs,space,'candidate:'+old['candidate_id'],'archive_candidate')
    with pytest.raises(ValueError,match='references_changed'):store.change(pubs,request)
    assert store.read(space,key)['revision']==0

def test_history_corruption_and_store_damage_fail_closed(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls;key='input:'+input_id
    run(store,pubs,space,key,'disable_input')
    with sqlite3.connect(store.path) as db:db.execute('DELETE FROM events')
    with pytest.raises(ValueError,match='history_mismatch'):store.report(pubs,space,key)
    with pytest.raises(ValueError,match='history_mismatch'):jobs.start(input_id,space)
    store.path.write_bytes(b'damaged database')
    with pytest.raises(ValueError,match='records_unavailable'):jobs.start(input_id,space)

def test_two_writers_one_revision_commits(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];key='input:'+input_id;store=jobs.controls;request=payload(store,pubs,space,key,'disable_input')
    def writer():
        try:return store.change(pubs,request)['revision']
        except ValueError as e:return str(e)
    with ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda _:writer(),range(2)))
    assert result.count(1)==1 and len(store.read(space,key)['history'])==1

def test_failed_sql_transaction_keeps_current_and_history_consistent(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];key='input:'+input_id;store=jobs.controls
    run(store,pubs,space,key,'disable_input');request=payload(store,pubs,space,key,'restore')
    with sqlite3.connect(store.path) as db:db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON controls BEGIN SELECT RAISE(ABORT,'injected_storage_failure'); END")
    with pytest.raises(sqlite3.IntegrityError):store.change(pubs,request)
    assert store.read(space,key)['revision']==1 and len(store.read(space,key)['history'])==1
    with sqlite3.connect(store.path) as db:db.execute('DROP TRIGGER reject_update')
    assert store.change(pubs,request)['revision']==2

def test_archive_vs_select_serializes_and_rechecks_after_lock(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,pubs,old,_,_=seed(tmp_path);space=spaces[0]['id'];key='candidate:'+old['candidate_id'];store=jobs.controls
    request=payload(store,pubs,space,key,'archive_candidate');entered=threading.Event();release=threading.Event();original=store.report
    def paused(*args):
        result=original(*args);entered.set();assert release.wait(5);return result
    monkeypatch.setattr(store,'report',paused)
    def select():
        try:jobs.select(old['candidate_id'],2,space);return 'selected'
        except ValueError as exc:return str(exc)
    with ThreadPoolExecutor(2) as pool:
        commit=pool.submit(store.change,pubs,request);assert entered.wait(5);future=pool.submit(select);time.sleep(.05);assert not future.done();release.set();assert commit.result()['lifecycle_state']=='archived';assert 'archived_new_use' in future.result()
    assert jobs.selection(space)['candidate_id']!=old['candidate_id']

def test_build_admitted_before_disable_finishes_admission_and_is_not_cancelled(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls;key='input:'+input_id;request=payload(store,pubs,space,key,'disable_input')
    entered=threading.Event();release=threading.Event()
    def launch(*args):entered.set();assert release.wait(5);return {'admitted':True}
    monkeypatch.setattr(jobs,'_launch',launch)
    with ThreadPoolExecutor(2) as pool:
        build=pool.submit(jobs.start,input_id,space);assert entered.wait(5);disable=pool.submit(store.change,pubs,request);time.sleep(.05);assert not disable.done();release.set();assert build.result()['admitted'];assert disable.result()['lifecycle_state']=='disabled'

def test_os_guard_orders_a_separate_process_and_reentrant_calls(tmp_path):
    marker=tmp_path/'marker';script='from pathlib import Path; from packages.lifecycle.preview_control_lock import mutation_guard; import sys;\nwith mutation_guard(sys.argv[1]):Path(sys.argv[2]).write_text("acquired")'
    with mutation_guard(tmp_path):
        with mutation_guard(tmp_path):pass
        process=subprocess.Popen([sys.executable,'-c',script,str(tmp_path),str(marker)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        time.sleep(.25);assert not marker.exists()
    assert process.wait(timeout=10)==0 and marker.read_text()=='acquired'

def test_api_catalog_and_build_lists_show_state_without_changing_fixed_bytes(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,old,new,input_id=seed(tmp_path);space=spaces[0]['id'];store=jobs.controls
    before={str(p):p.read_bytes() for p in pubs.root.rglob('*') if p.is_file()}
    run(store,pubs,space,'input:'+input_id,'disable_input');run(store,pubs,space,'candidate:'+old['candidate_id'],'archive_candidate')
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        assert client.get('/api/inputs',params={'space_id':space}).json()['inputs'][0]['lifecycle_state']=='disabled'
        assert next(j for j in client.get('/api/builds',params={'space_id':space}).json()['jobs'] if j['id']==old['candidate_id'])['lifecycle_state']=='archived'
        data=artifact_catalog(pubs,space);items={i['key']:i for i in data['items']};assert items['candidate:'+old['candidate_id']]['lifecycle_state']=='archived'
        from jsonschema import Draft202012Validator
        Draft202012Validator(json.loads(Path('contracts/schemas/preview-artifacts-v0.1.schema.json').read_bytes())).validate(data)
        assert client.get('/publications/'+new['id']+'/api/objects').status_code==200
    assert all(Path(p).read_bytes()==raw for p,raw in before.items())
