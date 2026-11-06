from copy import deepcopy
import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_preview_changes import setup, reviewed
from test_preview_publications import fixture as legacy_fixture
from packages.construction.preview_changes import CompareRequest, compare, confirm, checksum
from packages.service.preview_publications import PreviewPublications
from packages.service.preview_publication_changes import PublicationCompareRequest, compare_publications
from experiments.scripts.serve_nyu_flow_preview import create_app


def published(tmp_path):
    initial,jobs,directory,spaces,ontologies,base,target,request=setup(tmp_path)
    pubs=PreviewPublications(jobs)
    old=pubs.publish(base['id'],1,request['space_id'])
    report=compare(jobs,CompareRequest(**request))
    confirm(jobs,reviewed(request,report))
    new=pubs.publish(target['id'],2,request['space_id'])
    body={'space_id':request['space_id'],'base_publication_id':old['id'],'target_publication_id':new['id']}
    return initial,jobs,directory,spaces,ontologies,pubs,old,new,body


def test_readonly_fixed_comparison_and_saved_review(tmp_path):
    _,jobs,_,_,_,pubs,old,new,body=published(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report=compare_publications(pubs,PublicationCompareRequest(**body))
    assert report==compare_publications(pubs,PublicationCompareRequest(**body))
    assert report['base_publication']['publication_id']==old['id']
    assert report['target_publication']['candidate_id']==new['candidate_id']
    assert report['provenance']['base']['status']=='not_recorded'
    review=report['provenance']['target']
    assert review['status']=='internally_consistent' and review['matches_requested_base_model'] is True
    assert review['saved_review']==new['selection_review']
    assert review['trust']=='saved_local_record_not_authenticated_approval'
    assert len(report['changes']['objects']['added'])==len(report['changes']['objects']['removed'])==len(report['changes']['objects']['modified'])==1
    assert report['geometry_comparable'] and not report['robot_ready']
    assert checksum({k:v for k,v in report.items() if k!='comparison_sha256'})==report['comparison_sha256']
    assert {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before


def test_comparison_does_not_follow_selection_or_require_candidates(tmp_path):
    _,jobs,_,_,_,pubs,old,_,body=published(tmp_path)
    request=PublicationCompareRequest(**body);expected=compare_publications(pubs,request)
    jobs.select(old['candidate_id'],2,body['space_id'])
    for path in jobs.root.glob('build-*'):
        shutil.rmtree(path)  # Only this test's private tmp_path candidates.
    jobs.selection_path(body['space_id']).unlink()
    assert compare_publications(PreviewPublications(jobs),request)==expected


def test_explicit_reverse_self_and_review_base_model_semantics(tmp_path):
    _,jobs,_,_,_,pubs,old,new,body=published(tmp_path)
    reverse=compare_publications(pubs,PublicationCompareRequest(**(body|{'base_publication_id':new['id'],'target_publication_id':old['id']})))
    assert reverse['provenance']['target']['status']=='not_recorded'
    assert reverse['changes']['objects']['modified'][0]['after']['properties']['name']!='revised'
    same=compare_publications(pubs,PublicationCompareRequest(**(body|{'base_publication_id':new['id']})))
    assert same['changes']['objects']['modified']==[]
    assert same['provenance']['target']['status']=='internally_consistent'
    assert same['provenance']['target']['matches_requested_base_model'] is False
    # A second publication of the same model is a base-model match, not a signed publication-parent link.
    jobs.select(old['candidate_id'],2,body['space_id'])
    other=pubs.publish(old['candidate_id'],3,body['space_id'])
    report=compare_publications(pubs,PublicationCompareRequest(**(body|{'base_publication_id':other['id']})))
    assert report['provenance']['target']['matches_requested_base_model'] is True


@pytest.mark.parametrize('kind',['checksum','target','revision','ack','note','malformed','note_object','base_ref'])
def test_review_binding_mismatch_is_reported_not_promoted(tmp_path,kind):
    _,_,_,_,_,pubs,_,new,body=published(tmp_path)
    path=pubs.root/new['id']/'publication.json';record=deepcopy(new)
    review=record['selection_review']
    if kind=='checksum':review['comparison']['comparison_sha256']='0'*64
    elif kind=='target':review['comparison']['target_ref']['candidate_id']='different'
    elif kind=='revision':record['selection_revision']+=1
    elif kind=='ack':review['acknowledge_unverified']=False
    elif kind=='malformed':record['selection_review']='invalid saved record'
    elif kind=='note_object':review['note']={'unexpected':'object'}
    elif kind=='base_ref':
        review['comparison']['base_ref']['candidate_id']={'bad':'type'}
        review['comparison']['comparison_sha256']=checksum({k:v for k,v in review['comparison'].items() if k!='comparison_sha256'})
    else:review['note']=' '
    path.write_text(json.dumps(record),encoding='utf-8')
    result=compare_publications(pubs,PublicationCompareRequest(**body))['provenance']['target']
    assert result['status']=='binding_mismatch' and result['matches_requested_base_model'] is None


@pytest.mark.parametrize('kind',['candidate_id','model_manifest_sha256','source_model_sha256','member'])
def test_corrupt_publication_binding_or_member_refused(tmp_path,kind):
    _,_,_,_,_,pubs,_,new,body=published(tmp_path)
    path=pubs.root/new['id']/'publication.json';record=deepcopy(new)
    if kind=='member':(path.parent/'agent.npz').write_bytes(b'corrupt')
    else:
        record[kind]='wrong';path.write_text(json.dumps(record),encoding='utf-8')
    with pytest.raises(ValueError):compare_publications(pubs,PublicationCompareRequest(**body))


def test_scope_restrictions_and_api_contract(tmp_path):
    initial,jobs,directory,spaces,ontologies,_,_,_,body=published(tmp_path)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        assert client.post('/api/publication-comparisons',json=body).status_code==200
        assert client.post('/api/publication-comparisons',json=body,headers={'Origin':'https://example.com'}).status_code==403
        for invalid in [body|{'extra':True},body|{'base_publication_id':'../outside'},body|{'target_publication_id':3}]:
            assert client.post('/api/publication-comparisons',json=invalid).status_code==422
        assert client.post('/api/publication-comparisons',json=body|{'space_id':None}).status_code==409
        assert client.post('/api/publication-comparisons',json=body|{'space_id':spaces[1]['id']}).status_code==409
        assert client.post('/api/publication-comparisons',json=body|{'target_publication_id':'preview-'+'0'*16}).status_code==409


@pytest.mark.parametrize('kind',['frame_id','resolution'])
def test_legacy_and_incompatible_geometry_keep_provenance(tmp_path,kind):
    _,jobs=legacy_fixture(tmp_path);pubs=PreviewPublications(jobs)
    jobs.select('build-one',0);old=pubs.publish('build-one',1)
    path=jobs.root/'build-two/output/model.json';model=json.loads(path.read_bytes())
    if kind=='frame_id':model['frame_id']='different'
    else:model['agent_view']['resolution_m']=.2
    path.write_text(json.dumps(model),encoding='utf-8')
    jobs.select('build-two',1);new=pubs.publish('build-two',2)
    report=compare_publications(pubs,PublicationCompareRequest(base_publication_id=old['id'],target_publication_id=new['id']))
    assert not report['geometry_comparable'] and report['changes']['geometry']['added_surface'] is None
    assert report['provenance']['base']['status']==report['provenance']['target']['status']=='not_recorded'


def test_record_changed_during_comparison_refused(tmp_path,monkeypatch):
    _,_,_,_,_,pubs,old,_,body=published(tmp_path)
    from packages.service import preview_publication_changes as module
    original=module.compare_models
    def race(*args,**kwargs):
        result=original(*args,**kwargs)
        path=pubs.root/old['id']/'publication.json';path.write_bytes(path.read_bytes()+b' ')
        return result
    monkeypatch.setattr(module,'compare_models',race)
    with pytest.raises(ValueError,match='publication_record_changed'):
        compare_publications(pubs,PublicationCompareRequest(**body))


def test_schema_matches_request_and_response(tmp_path):
    _,_,_,_,_,pubs,_,_,body=published(tmp_path)
    schema=json.loads(Path('contracts/schemas/preview-publication-changes-v0.1.schema.json').read_bytes())
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema)
    validator.validate(body)
    validator.validate(compare_publications(pubs,PublicationCompareRequest(**body)))
    assert schema['$defs']['Request']==PublicationCompareRequest.model_json_schema()
    for invalid in [body|{'space_id':False},body|{'unexpected':1},body|{'base_publication_id':'invalid'}]:
        assert not validator.is_valid(invalid)
