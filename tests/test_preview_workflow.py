import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_preview_objects import fixture
from test_preview_inputs import source
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_ledger import PreviewLedger
from packages.spatial.preview_objects import SemanticRequest
from packages.spatial.preview_business import LedgerDraft,BusinessRequest
from packages.spatial.preview_relations import RelationRequest
from packages.construction.preview_semantics import annotate
from packages.construction.preview_business import associate
from packages.construction.preview_relations import relate
from packages.construction.preview_model import digest
from packages.construction.preview_changes import CompareRequest,ReviewRequest,compare,confirm
from packages.service.preview_publications import PreviewPublications
from packages.service.preview_workflow import workflow
from packages.service.preview_checklist import checklist
from experiments.scripts.serve_nyu_flow_preview import create_app

def prepared(tmp_path,publish=True):
    initial,jobs,directory,spaces,store,body=fixture(tmp_path)
    snapshot,tracking=source(tmp_path);inputs=PreviewInputs(tmp_path/'inputs',directory);jobs.inputs=inputs
    registered=inputs.register('workflow source',snapshot,tracking,spaces[0]['id']);binding={k:v for k,v in registered.items() if k not in ('snapshot','tracking')}
    root=jobs.root/'build-one';manifest=json.loads((root/'output/model.json').read_bytes());manifest['source']=binding|{'input_binding':binding}
    human=root/'output/human.ply';human.write_text('ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 2\n')
    manifest['members']['human.ply']={'sha256':digest(human),'bytes':human.stat().st_size};manifest['human_view']['path']='human.ply'
    (root/'output/model.json').write_text(json.dumps(manifest));job=json.loads((root/'job.json').read_bytes());job.update(input_id=registered['id'],input_binding=binding);(root/'job.json').write_text(json.dumps(job))
    body['base_manifest_sha256']=digest(root/'output/model.json')
    body['objects']=[{'object_id':i,'type_id':t,'properties':{'name':i+' 待核实'},'point_index':0} for i,t in [('room-a','room'),('cabinet-a','cabinet'),('corridor-a','corridor')]]
    base=annotate(jobs,store,SemanticRequest(**body));selected=jobs.select(base['id'],0,body['space_id']);pubs=PreviewPublications(jobs);old=pubs.publish(base['id'],selected['revision'],body['space_id'])
    ledger=PreviewLedger(tmp_path/'ledger',directory);entry=ledger.register(LedgerDraft(space_id=body['space_id'],source_system='test',external_id='test-1',version='1',title='待核实台账'))
    model=jobs.model(base['id']);business=associate(jobs,store,ledger,BusinessRequest(space_id=body['space_id'],base_candidate_id=base['id'],base_manifest_sha256=digest(model.root/'model.json'),bindings=[{'object_id':'cabinet-a','ledger_ref':entry['ref']}]))
    model=jobs.model(business['id']);rule=store.register('configs/ontology/indoor-equipment-v0.2.json')
    linked=relate(jobs,store,RelationRequest(space_id=body['space_id'],base_candidate_id=business['id'],base_manifest_sha256=digest(model.root/'model.json'),ontology_ref={k:rule[k] for k in ('ontology_id','version','sha256')},relations=[{'relation_id':'rel-1','type_id':'contains','source_id':'room-a','target_id':'cabinet-a','note':'测试归属，待核实'}]))
    compare_request={'space_id':body['space_id'],'candidate_id':linked['id'],'expected_revision':1};report=compare(jobs,CompareRequest(**compare_request))
    selected=confirm(jobs,ReviewRequest(**compare_request,comparison_sha256=report['comparison_sha256'],acknowledge_unverified=True,note='流程核对'))
    new=pubs.publish(linked['id'],selected['revision'],body['space_id']) if publish else None
    return initial,jobs,directory,spaces,store,pubs,old,new

def stages(report):return {s['id']:s for s in report['stages']}
def inventory(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

def test_complete_saved_flow_readonly_without_consumer_claim(tmp_path,monkeypatch):
    _,jobs,_,spaces,_,pubs,_,new=prepared(tmp_path)
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('must not poll'))
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *a:pytest.fail('must not preflight source'))
    monkeypatch.setattr('packages.views.agent.preview_offline.export_bundle',lambda *a:pytest.fail('must not export'))
    before=inventory(tmp_path);report=workflow(pubs,spaces[0]['id']);s=stages(report)
    assert {s[k]['status'] for k in ('data','build','ontology','association','delivery')}<={'ready','recorded'}
    assert report['publication_ref']['publication_id']==new['id']
    assert report['counts']['objects']==3 and report['counts']['business_bindings']==report['counts']['object_relations']==1
    assert s['consumer']['status']=='unobserved' and report['next_stage']=='space'
    assert report['summary']['service_status']=='complete'
    assert not report['consumer_state_checked'] and not report['source_files_rechecked'] and not report['jobs_polled']
    assert not report['robot_ready'] and not report['production_ready'] and inventory(tmp_path)==before

def test_unpublished_current_does_not_borrow_old_publication(tmp_path):
    _,_,_,spaces,_,pubs,old,_=prepared(tmp_path,publish=False)
    report=workflow(pubs,spaces[0]['id']);s=stages(report)
    assert report['counts']['publication']==1 and report['publication_ref'] is None
    assert s['delivery']['status']==s['space']['status']=='pending' and report['next_stage']=='delivery'
    assert old['id'] not in json.dumps(report['next_action'])
    assert report['next_action']['values']['job']==report['candidate_ref']['candidate_id']
    assert s['build']['action']['values']['tab']=='flow'

def test_saved_batch_source_links_to_batch_without_reading_live_store(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_=prepared(tmp_path)
    path=jobs.root/'space-selections'/(spaces[0]['id']+'.json');selection=json.loads(path.read_bytes());root=jobs.root/selection['candidate_id']
    manifest=json.loads((root/'output/model.json').read_bytes());ref={'batch_id':'batch-'+'a'*16,'admitted_revision':2}
    manifest['source']['batch_ref']=ref;(root/'output/model.json').write_text(json.dumps(manifest))
    job=json.loads((root/'job.json').read_bytes());job['batch_ref']=ref;(root/'job.json').write_text(json.dumps(job))
    selection['model_manifest_sha256']=digest(root/'output/model.json');path.write_text(json.dumps(selection))
    report=workflow(pubs,spaces[0]['id']);data=stages(report)['data']
    assert data['action']['values']['batch']==ref['batch_id'] and '提交修订 2' in data['detail']
    assert not jobs.inputs.root.joinpath('acquisition-batches.sqlite3').exists()

def test_empty_space_no_selection_directory_side_effect(tmp_path):
    initial,jobs,directory,spaces,_,_=fixture(tmp_path);pubs=PreviewPublications(jobs)
    empty=directory.create('space','empty',spaces[0]['project_id']);path=jobs.root/'space-selections';assert not path.exists()
    before=inventory(tmp_path);report=workflow(pubs,empty['id'])
    assert report['next_stage']=='data' and report['candidate_ref'] is None
    assert all(s['status'] in ('pending','unobserved') for s in report['stages'])
    assert not path.exists() and inventory(tmp_path)==before

@pytest.mark.parametrize('kind',['selection','review'])
def test_invalid_selected_binding_never_ready(tmp_path,kind):
    _,jobs,_,spaces,_,pubs,_,_=prepared(tmp_path);path=jobs.root/'space-selections'/(spaces[0]['id']+'.json');doc=json.loads(path.read_bytes())
    if kind=='selection':doc['model_manifest_sha256']='0'*64
    else:doc['selection_review']['comparison']['comparison_sha256']='0'*64
    path.write_text(json.dumps(doc));report=workflow(pubs,spaces[0]['id'])
    assert stages(report)['build']['status']=='blocked'
    if kind=='selection':assert report['publication_ref'] is None and report['candidate_ref'] is None
    assert report['next_stage'] in ('data','build')

def test_missing_associations_and_legacy_review_are_explicit(tmp_path):
    _,jobs,_,spaces,_,pubs,old,_=prepared(tmp_path)
    jobs.select(old['candidate_id'],2,spaces[0]['id']);report=workflow(pubs,spaces[0]['id']);s=stages(report)
    assert s['build']['status']=='pending' and s['association']['status']=='pending'
    assert report['counts']['business_bindings']==report['counts']['object_relations']==0
    assert report['next_stage']=='build'

def test_scope_api_and_no_foreign_record_leak(tmp_path):
    initial,jobs,directory,spaces,store,pubs,_,new=prepared(tmp_path)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=store)) as client:
        assert client.get('/api/workflow').status_code==422
        assert client.get('/api/workflow?space_id=unknown').status_code==404
        report=client.get('/api/workflow',params={'space_id':spaces[1]['id']}).json()
        assert report['space_id']==spaces[1]['id'] and new['id'] not in json.dumps(report)
        assert new['candidate_id'] not in json.dumps(report)
        assert client.get('/api/workflow',params={'space_id':spaces[0]['id']}).status_code==200

def test_checklist_covers_frozen_business_relations_without_stale_capability_gap(tmp_path):
    _,_,_,_,_,pubs,_,new=prepared(tmp_path);report=checklist(pubs,new['id']);s=stages(report)
    assert s['business']['status']==s['relations']['status']=='recorded' and s['query']['status']=='passed'
    assert not any('尚未持久化' in gap for gap in report['gaps'])
    assert any('不读取消费端' in gap for gap in report['gaps'])

def test_geometry_only_flow_skips_optional_enrichment_but_requires_publication(tmp_path):
    _,jobs,_,spaces,_,pubs,_,_=prepared(tmp_path)
    space=spaces[0]['id']
    request={'space_id':space,'candidate_id':'build-one','expected_revision':2}
    comparison=compare(jobs,CompareRequest(**request))
    selection=confirm(jobs,ReviewRequest(**request,comparison_sha256=comparison['comparison_sha256'],acknowledge_unverified=True,note='几何流程验收'))
    report=workflow(pubs,space)
    assert report['next_stage']=='delivery' and report['publication_ref'] is None
    for name in ('ontology','association'):
        assert stages(report)[name]['optional'] and stages(report)[name]['status']=='pending'
    publication=pubs.publish('build-one',selection['revision'],space)
    report=workflow(pubs,space)
    assert report['publication_ref']['publication_id']==publication['id']
    assert report['next_stage']=='space' and not report['consumer_state_checked']
    assert report['summary']['service_status']=='complete'
    assert report['next_action']['values']=={'space':space,'job':'build-one','publication':publication['id']}
    assert stages(report)['delivery']['action']['values']=={'space':space,'job':'build-one','publication':publication['id']}
