from copy import deepcopy
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient

from test_preview_objects import fixture
from test_preview_publications import fixture as legacy_fixture
from packages.construction.preview_semantics import annotate
from packages.spatial.preview_objects import SemanticRequest
from packages.construction.preview_changes import CompareRequest,ReviewRequest,compare,confirm
from packages.construction.preview_model import digest
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from experiments.scripts.serve_nyu_flow_preview import create_app
from jsonschema import Draft202012Validator
from pathlib import Path


def setup(tmp_path):
    initial,jobs,directory,spaces,ontologies,body=fixture(tmp_path)
    body['objects'].append({'object_id':'remove-001','type_id':'room','properties':{'name':'removed'},'point_index':0})
    base=annotate(jobs,ontologies,SemanticRequest.model_validate(body))
    jobs.select(base['id'],0,body['space_id'])
    revised=deepcopy(body)
    revised.update(base_candidate_id=base['id'],base_manifest_sha256=digest(jobs.root/base['id']/'output/model.json'))
    revised['objects'][0]['properties']['name']='revised'
    revised['objects'][1]['object_id']='added-001'
    target=annotate(jobs,ontologies,SemanticRequest.model_validate(revised))
    request={'candidate_id':target['id'],'space_id':body['space_id'],'expected_revision':1}
    return initial,jobs,directory,spaces,ontologies,base,target,request


def reviewed(request,report):
    return ReviewRequest(**request,comparison_sha256=report['comparison_sha256'],acknowledge_unverified=True,note='人工核对测试，非现场确认')


def test_readonly_comparison_classifies_changes_and_is_deterministic(tmp_path):
    _,jobs,_,_,_,base,target,request=setup(tmp_path)
    before={p:p.read_bytes() for p in jobs.root.rglob('*') if p.is_file()}
    report=compare(jobs,CompareRequest(**request))
    assert report==compare(jobs,CompareRequest(**request))
    assert report['base_ref']['candidate_id']==base['id'] and report['target_ref']['candidate_id']==target['id']
    assert report['geometry']['same_source_model'] and report['geometry']['added_surface']['count']==report['geometry']['removed_surface']['count']==0
    assert [o['object_id'] for o in report['objects']['added']]==['added-001']
    assert [o['object_id'] for o in report['objects']['removed']]==['remove-001']
    assert report['objects']['modified'][0]['fields']==['properties']
    assert report['objects']['modified'][0]['before']['properties']['name']!='revised'
    assert report['objects']['modified'][0]['after']['properties']['name']=='revised'
    assert {p:p.read_bytes() for p in jobs.root.rglob('*') if p.is_file()}==before


def test_review_selects_only_then_publication_and_offline_keep_review(tmp_path):
    _,jobs,_,_,_,base,target,request=setup(tmp_path)
    pubs=PreviewPublications(jobs);old=pubs.publish(base['id'],1,request['space_id'])
    old_objects=pubs.read(old['id'])[1].objects()
    report=compare(jobs,CompareRequest(**request))
    selected=confirm(jobs,reviewed(request,report))
    assert selected['revision']==2 and selected['candidate_id']==target['id']
    assert selected['selection_review']['comparison']==report
    assert pubs.list()==[old]  # Choosing never publishes.
    new=pubs.publish(target['id'],2,request['space_id'])
    data=export_bundle(*pubs.read(new['id']))
    offline=OfflinePreview(data,new['id'],sha(data))
    assert any(o['properties']['name']=='revised' for o in offline.objects()['objects'])
    assert new['selection_review']==selected['selection_review']
    assert pubs.read(old['id'])[1].objects()==old_objects
    assert json.loads((jobs.root/'space-selections'/(request['space_id']+'.json')).read_text())==selected


@pytest.mark.parametrize('kind',['hash','note','ack','selection','target'])
def test_stale_or_missing_acknowledgement_rejected_without_selection(tmp_path,kind):
    _,jobs,_,_,_,base,target,request=setup(tmp_path)
    report=compare(jobs,CompareRequest(**request));body=reviewed(request,report).model_dump()
    if kind=='hash':body['comparison_sha256']='0'*64
    elif kind=='note':body['note']='   '
    elif kind=='ack':body['acknowledge_unverified']=False
    elif kind=='selection':jobs.select(base['id'],1,request['space_id'])
    else:
        path=jobs.root/target['id']/'output/model.json';m=json.loads(path.read_bytes());m['label']='changed since report';path.write_text(json.dumps(m))
    before=jobs.selection(request['space_id'])
    with pytest.raises(ValueError):confirm(jobs,ReviewRequest(**body))
    assert jobs.selection(request['space_id'])==before


def test_revalidation_inside_selection_lock_rejects_racing_changes(tmp_path,monkeypatch):
    _,jobs,_,_,_,_,target,request=setup(tmp_path)
    report=compare(jobs,CompareRequest(**request));select=jobs.select
    def racing(*args,**kwargs):
        path=jobs.root/target['id']/'output/model.json';m=json.loads(path.read_bytes());m['label']='race';path.write_text(json.dumps(m))
        return select(*args,**kwargs)
    monkeypatch.setattr(jobs,'select',racing)
    with pytest.raises(ValueError,match='comparison_changed'):confirm(jobs,reviewed(request,report))
    assert jobs.selection(request['space_id'])['revision']==1


@pytest.mark.parametrize('kind',['frame_id','resolution'])
def test_incompatible_coordinate_or_grid_has_no_surface_diff_and_blocks_review(tmp_path,kind):
    _,jobs=legacy_fixture(tmp_path);jobs.select('build-one',0)
    path=jobs.root/'build-two/output/model.json';m=json.loads(path.read_bytes())
    if kind=='frame_id':m['frame_id']='different'
    else:m['agent_view']['resolution_m']=.2
    path.write_text(json.dumps(m))
    request={'candidate_id':'build-two','expected_revision':1}
    report=compare(jobs,CompareRequest(**request))
    assert not report['review_allowed'] and report['geometry']['added_surface'] is None
    with pytest.raises(ValueError,match='blocked'):confirm(jobs,reviewed(request,report))


def test_surface_removed_is_not_free_and_samples_are_bounded(tmp_path):
    _,jobs=legacy_fixture(tmp_path);jobs.select('build-one',0)
    root=jobs.root/'build-two/output'
    np.savez_compressed(root/'agent.npz',cells=np.array([[i,9,9] for i in range(30)]))
    path=root/'model.json';m=json.loads(path.read_bytes());m['members']['agent.npz']['sha256']=digest(root/'agent.npz');path.write_text(json.dumps(m))
    report=compare(jobs,CompareRequest(candidate_id='build-two',expected_revision=1))
    assert report['geometry']['added_surface']['count']==30 and len(report['geometry']['added_surface']['sample_cell_indices'])==20
    assert report['geometry']['removed_surface']['count']==2
    assert report['geometry']['unlisted_state']=='unknown' and report['geometry']['removed_surface_meaning']=='evidence_removed_not_free_space'


def test_initial_selection_and_no_semantics_are_explicit(tmp_path):
    _,jobs=legacy_fixture(tmp_path)
    report=compare(jobs,CompareRequest(candidate_id='build-one',expected_revision=0))
    assert report['base_ref'] is None and not report['objects']['base_available'] and not report['objects']['target_available']
    assert confirm(jobs,reviewed({'candidate_id':'build-one','expected_revision':0},report))['revision']==1


def test_anchor_and_type_revision_are_reported_under_stable_object_id(tmp_path):
    _,jobs,_,_,ontologies,body=fixture(tmp_path)
    root=jobs.root/'build-one/output'
    np.savez_compressed(root/'spatial.npz',points=np.array([[0.,0.,2.],[1.,0.,2.]]),colors=np.array([[40,80,120],[40,80,120]],dtype='u1'))
    path=root/'model.json';model=json.loads(path.read_bytes())
    model['members']['spatial.npz']['sha256']=digest(root/'spatial.npz')
    for view in ('human_view','agent_view'):model[view]['source_model_sha256']=model['members']['spatial.npz']['sha256']
    path.write_text(json.dumps(model));body['base_manifest_sha256']=digest(path)
    base=annotate(jobs,ontologies,SemanticRequest.model_validate(body));jobs.select(base['id'],0,body['space_id'])
    body.update(base_candidate_id=base['id'],base_manifest_sha256=digest(jobs.root/base['id']/'output/model.json'))
    body['objects'][0].update(type_id='cabinet',point_index=1)
    target=annotate(jobs,ontologies,SemanticRequest.model_validate(body))
    report=compare(jobs,CompareRequest(candidate_id=target['id'],space_id=body['space_id'],expected_revision=1))
    assert report['objects']['modified'][0]['fields']==['anchor_m','evidence','type_id']
    assert report['objects']['modified'][0]['before']['anchor_m']==[0.,0.,2.]
    assert report['objects']['modified'][0]['after']['anchor_m']==[1.,0.,2.]


def test_api_origin_strict_requests_cross_space_and_restart(tmp_path):
    initial,jobs,directory,spaces,ontologies,_,_,request=setup(tmp_path)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        assert client.post('/api/candidate-comparisons',json=request,headers={'Origin':'https://example.com'}).status_code==403
        for change in [{'expected_revision':True},{'expected_revision':-1},{'extra':1}]:
            assert client.post('/api/candidate-comparisons',json=request|change).status_code==422
        assert client.post('/api/candidate-comparisons',json=request|{'space_id':spaces[1]['id'],'expected_revision':0}).status_code==409
        report=client.post('/api/candidate-comparisons',json=request).json()
        selected=client.post('/api/candidate-reviews',json=reviewed(request,report).model_dump())
        assert selected.status_code==200,selected.text
        assert client.get('/api/selection',params={'space_id':request['space_id']}).json()==selected.json()
    from packages.construction.preview_jobs import PreviewJobs
    restarted=PreviewJobs(jobs.root,tmp_path/'unused',tmp_path/'unused');restarted.directory=directory
    assert restarted.selection(request['space_id'])==selected.json()


def test_request_schema_accepts_both_operations_and_rejects_unbound_fields():
    schema=json.loads(Path('contracts/schemas/preview-changes-v0.1.schema.json').read_bytes())
    Draft202012Validator.check_schema(schema);validator=Draft202012Validator(schema)
    request={'candidate_id':'build-example','space_id':'space-example','expected_revision':1}
    validator.validate(request)
    validator.validate(request|{'comparison_sha256':'a'*64,'acknowledge_unverified':True,'note':'review'})
    for change in [{'expected_revision':True},{'extra':1},{'comparison_sha256':'a'*64}]:
        assert list(validator.iter_errors(request|change))
