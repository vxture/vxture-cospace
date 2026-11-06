import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator,FormatChecker
from packages.lifecycle.preview_impact import impact
from packages.data.preview_batches import PreviewBatches,BatchDraft,BatchChange
from packages.construction.preview_model import digest
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_workflow import prepared

def inventory(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def plans(report):return {p['operation']:p for p in report['plans']}
def seed(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,old,new=prepared(tmp_path)
    jobs.batches=PreviewBatches(jobs.inputs)
    input_id=json.loads((jobs.root/new['candidate_id']/'job.json').read_bytes())['input_id']
    return initial,jobs,directory,spaces,ontologies,pubs,old,new,input_id

def test_input_impact_exact_graph_and_no_side_effects(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,pubs,_,new,input_id=seed(tmp_path);space=spaces[0]['id']
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('must not poll'))
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *a:pytest.fail('must not inspect source'))
    monkeypatch.setattr('packages.views.agent.preview_offline.export_bundle',lambda *a:pytest.fail('must not export'))
    before=inventory(tmp_path);report=impact(pubs,space,'input:'+input_id)
    assert report['issues']==[]
    assert report['reference_counts']=={'batch':0,'job':4,'candidate':4,'publication':2,'offline_package':2}
    assert plans(report)['disable_input']['decision']=='eligible_by_saved_records'
    assert plans(report)['archive_input']['blockers']==['current_selection_depends_on_input']
    assert report['selected_dependencies']==['candidate:'+new['candidate_id']]
    assert report['mode']=='impact_preview_only' and not report['mutation_supported'] and all(not p['executable'] for p in report['plans'])
    assert not report['jobs_polled'] and not report['source_files_rechecked'] and not report['consumer_state_checked']
    assert inventory(tmp_path)==before and not jobs.batches.path.exists()

def test_selected_candidate_archive_blocked_old_candidate_retains_descendants(tmp_path):
    _,_,_,spaces,_,pubs,old,new,_=seed(tmp_path);space=spaces[0]['id']
    current=impact(pubs,space,'candidate:'+new['candidate_id'])
    assert plans(current)['archive_candidate']['blockers']==['candidate_is_current_selection']
    report=impact(pubs,space,'candidate:'+old['candidate_id'])
    assert plans(report)['archive_candidate']['decision']=='eligible_by_saved_records'
    assert report['reference_counts']['candidate']==2 and report['reference_counts']['publication']==2
    assert 'candidate:'+new['candidate_id'] in {r['key'] for r in report['references']}
    assert plans(report)['archive_candidate']['retained']

def test_publication_preview_does_not_claim_offline_revoke(tmp_path):
    _,_,_,spaces,_,pubs,_,new,_=seed(tmp_path)
    report=impact(pubs,spaces[0]['id'],'publication:'+new['id']);plan=plans(report)['pause_distribution']
    assert plan['decision']=='eligible_by_saved_records' and plan['executable'] is False
    assert report['reference_counts']=={'batch':0,'job':0,'candidate':0,'publication':0,'offline_package':1}
    assert '已安装' in ''.join(plan['retained'])
    schema=json.loads(Path('contracts/schemas/preview-artifact-impact-v0.1.schema.json').read_bytes())
    validator=Draft202012Validator(schema,format_checker=FormatChecker());validator.validate(report)
    current=impact(pubs,spaces[0]['id'],'candidate:'+new['candidate_id']);validator.validate(current)

def test_batch_membership_and_saved_active_job_block_archive_and_digest_changes(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];first=impact(pubs,space,'input:'+input_id)
    batch=jobs.batches.create(BatchDraft(space_id=space,name='sample',origin='imported_sample',note='流程样本'))
    request={'space_id':space,'expected_revision':0,'operation':'replace_members','reason':'资料分组','input_ids':[input_id]}
    batch=jobs.batches.change(batch['id'],BatchChange(**request))
    p=jobs.root/'build-running';p.mkdir();(p/'job.json').write_text(json.dumps({'id':p.name,'state':'running','input_id':input_id,'space_id':space,'project_id':spaces[0]['project_id']}))
    report=impact(pubs,space,'input:'+input_id)
    assert report['reference_counts']['batch']==1 and report['reference_counts']['job']==5
    assert 'active_batch_membership' in plans(report)['archive_input']['blockers'] and 'saved_active_build_attempt' in plans(report)['archive_input']['blockers']
    assert first['snapshot_sha256']!=report['snapshot_sha256']
    off=jobs.batches.change(batch['id'],BatchChange(space_id=space,expected_revision=1,operation='disable',reason='停用样本分组'))
    restored=impact(pubs,space,'input:'+input_id)
    assert 'active_batch_membership' not in plans(restored)['archive_input']['blockers']
    assert next(r for r in restored['references'] if r['kind']=='batch')['state']=='disabled'

@pytest.mark.parametrize('kind',['candidate','publication','selection','missing_source'])
def test_incomplete_dependency_graph_never_optimistically_allows(tmp_path,kind):
    _,jobs,_,spaces,_,pubs,old,new,input_id=seed(tmp_path);space=spaces[0]['id']
    if kind=='candidate':(jobs.root/old['candidate_id']/'output/agent.npz').write_bytes(b'bad')
    elif kind=='publication':(pubs.root/old['id']/'agent.npz').write_bytes(b'bad')
    elif kind=='selection':
        p=jobs.root/'space-selections'/(space+'.json');value=json.loads(p.read_bytes());value['model_manifest_sha256']='0'*64;p.write_text(json.dumps(value))
    else:(jobs.inputs.root/(input_id+'.json')).unlink()
    report=impact(pubs,space,'publication:'+new['id'])
    assert report['issues'] and all(p['decision']=='blocked' for p in report['plans'])
    assert all('dependency_records_incomplete' in p['blockers'] for p in report['plans'])

def test_digest_stable_excludes_checked_at_and_changes_with_selection(tmp_path):
    _,jobs,_,spaces,_,pubs,old,new,input_id=seed(tmp_path);space=spaces[0]['id']
    one=impact(pubs,space,'input:'+input_id);two=impact(pubs,space,'input:'+input_id)
    assert one['snapshot_sha256']==two['snapshot_sha256'] and one['checked_at']!=two['checked_at']
    jobs.select(old['candidate_id'],2,space)
    assert impact(pubs,space,'input:'+input_id)['snapshot_sha256']!=one['snapshot_sha256']

def test_unknown_active_task_source_is_explicit_uncertainty(tmp_path):
    _,jobs,_,spaces,_,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];p=jobs.root/'build-unresolved';p.mkdir()
    (p/'job.json').write_text(json.dumps({'id':p.name,'state':'queued','input_id':'unknown','space_id':space,'project_id':spaces[0]['project_id']}))
    report=impact(pubs,space,'publication:'+new['id'])
    assert any(i['code']=='active_job_source_unresolved' for i in report['issues'])
    assert plans(report)['pause_distribution']['decision']=='blocked'

def test_api_scope_invalid_target_and_no_mutation_route(tmp_path):
    initial,jobs,directory,spaces,store,_,_,new,input_id=seed(tmp_path)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=store)) as client:
        assert client.get('/api/artifact-impact').status_code==422
        assert client.get('/api/artifact-impact',params={'space_id':'unknown','artifact':'input:'+input_id}).status_code==404
        assert client.get('/api/artifact-impact',params={'space_id':spaces[1]['id'],'artifact':'publication:'+new['id']}).status_code==404
        for artifact in ('../escape','offline_package:'+new['id']):
            assert client.get('/api/artifact-impact',params={'space_id':spaces[0]['id'],'artifact':artifact}).status_code==422
        result=client.get('/api/artifact-impact',params={'space_id':spaces[0]['id'],'artifact':'input:'+input_id})
        assert result.status_code==200 and result.json()['mutation_supported'] is False
        assert client.post('/api/artifact-impact',json={'artifact':'input:'+input_id}).status_code==405
        foreign=client.get('/api/artifact-impact',params={'space_id':spaces[1]['id'],'artifact':'candidate:build-two'}).json()
        assert new['id'] not in json.dumps(foreign) and input_id not in json.dumps(foreign)

def test_changed_source_files_not_rechecked_and_no_paths_returned(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path)
    registration=jobs.inputs.read(input_id);Path(registration['snapshot']).joinpath('raw/d.pgm').write_bytes(b'changed')
    before=inventory(tmp_path);report=impact(pubs,spaces[0]['id'],'input:'+input_id)
    assert not report['source_files_rechecked'] and report['issues']==[]
    assert registration['snapshot'] not in json.dumps(report) and inventory(tmp_path)==before

def test_unreferenced_registration_can_be_archived_by_rules(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id'];record=jobs.inputs.read(input_id)
    spare=jobs.inputs.register('unused sample',record['snapshot'],record['tracking'],space)
    report=impact(pubs,space,'input:'+spare['id'])
    assert report['references']==[] and report['issues']==[]
    assert all(p['decision']=='eligible_by_saved_records' and not p['executable'] for p in report['plans'])

def test_selection_race_discards_report(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,pubs,_,_,input_id=seed(tmp_path);space=spaces[0]['id']
    def changed(_):
        p=jobs.root/'space-selections'/(space+'.json');r=json.loads(p.read_bytes());r['revision']+=1;p.write_text(json.dumps(r));return []
    monkeypatch.setattr(jobs.batches,'list',changed)
    with pytest.raises(ValueError,match='impact_selection_changed'):impact(pubs,space,'input:'+input_id)

def test_unreadable_saved_record_fails_whole_check(tmp_path):
    initial,jobs,directory,spaces,store,_,_,new,_=seed(tmp_path)
    (jobs.root/'build-one/job.json').write_bytes(b'{')
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=store)) as client:
        response=client.get('/api/artifact-impact',params={'space_id':spaces[0]['id'],'artifact':'publication:'+new['id']})
        assert response.status_code==409 and response.json()['detail']=='impact_records_unavailable'
