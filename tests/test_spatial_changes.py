import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.spatial.change_sample import build_change_sample
from packages.spatial.changes import SCHEMA, CandidateBranch, build_candidate, object_digest, validate_candidate

NOW='2026-10-28T00:30:00Z'


@pytest.fixture
def sample():
    return build_change_sample()


def build(sample):
    return build_candidate(*sample,now=NOW)


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))


def test_candidate_does_not_mutate_or_publish(sample):
    before=copy.deepcopy(sample)
    result=build(sample)
    assert sample==before
    c=result['candidate']
    assert c['publication_status']=='candidate_only' and not c['real_release_ready']
    assert set(c['impacted_views'])=={'human-v1','machine-v1'}
    assert validate_candidate(result)
    content=json.loads(result['blobs'][c['content']['path']])
    objects=json.loads(result['blobs'][content['objects']['path']])
    assert objects['instances'][0]['anchor']==[3,2,0]
    assert 'quality' not in content and 'provenance' not in content


@pytest.mark.parametrize('field',['release_id','release_sha256','truth_id','truth_sha256'])
def test_base_preconditions(sample,field):
    sample[1]['base'][field]='1'*64 if field.endswith('sha256') else 'other'
    with pytest.raises(ValueError,match='base_conflict'):
        build(sample)


def test_object_precondition(sample):
    sample[1]['operations'][0]['expected_object_sha256']='1'*64
    with pytest.raises(ValueError,match='object_precondition_conflict'):
        build(sample)


def test_resource_precondition(sample):
    sample[1]['operations'][1]['expected_sha256']='1'*64
    with pytest.raises(ValueError,match='resource_precondition_conflict'):
        build(sample)


@pytest.mark.parametrize('change,message',[
    (lambda d:d['operations'][0]['object'].update(type_id='Pump'),'unknown_object_type'),
    (lambda d:d['operations'][0]['object'].update(anchor=[10,0,0]),'out_of_scope'),
    (lambda d:d['operations'][0]['object'].update(anchor=[float('inf'),0,0]),'nonfinite_anchor'),
    (lambda d:d['operations'].append(copy.deepcopy(d['operations'][0])),'duplicate_object_operation'),
    (lambda d:d['operations'].append(copy.deepcopy(d['operations'][1])),'duplicate_resource_operation'),
    (lambda d:d.update(new_truth_id='truth-v1'),'new_identity_conflict'),
    (lambda d:d.update(schema_version='cospace.spatial-change/99'),'change_structure'),
    (lambda d:d.update(data_kind='real'),'change_structure'),
    (lambda d:d.update(evidence=[]),'change_structure'),
    (lambda d:d['operations'][1].update(role='frame'),'change_structure')])
def test_invalid_changes(sample,change,message):
    change(sample[1])
    with pytest.raises(ValueError,match=message):
        build(sample)


def test_add_object(sample):
    sample[1]['operations'][0]={'op':'object.add','object':{'object_id':'cabinet-c','type_id':'Cabinet','anchor':[1,1,0]}}
    assert validate_candidate(build(sample))


def test_remove_object(sample):
    operation=sample[1]['operations'][0]
    sample[1]['operations'][0]={'op':'object.remove','object_id':operation['object']['object_id'],'expected_object_sha256':operation['expected_object_sha256']}
    assert validate_candidate(build(sample))


def test_existing_object_cannot_be_added(sample):
    op=sample[1]['operations'][0]
    op['op']='object.add'
    del op['expected_object_sha256']
    with pytest.raises(ValueError,match='object_already_exists'):
        build(sample)


def test_no_op_object(sample):
    sample[1]['operations'][0]['object']['anchor']=[2,2,0]
    with pytest.raises(ValueError,match='no_op_object_change'):
        build(sample)


def test_evidence_tamper(sample):
    sample[2]['evidence/change.json']+=b' '
    with pytest.raises(ValueError,match='resource_integrity_mismatch'):
        build(sample)


def test_missing_evidence(sample):
    del sample[2]['evidence/change.json']
    with pytest.raises(ValueError,match='resource_missing'):
        build(sample)


def test_extra_resource(sample):
    sample[2]['extra']=b'{}'
    with pytest.raises(ValueError,match='unreferenced_resources'):
        build(sample)


def test_candidate_tamper_before_submit(sample):
    result=build(sample)
    result['blobs'][result['candidate']['content']['path']]+=b' '
    with pytest.raises(ValueError,match='candidate_integrity_mismatch'):
        CandidateBranch(sample[1]['base']['release_sha256']).submit(result,expected_revision=0)


def test_concurrent_submit_has_one_winner(sample):
    result=build(sample)
    branch=CandidateBranch(sample[1]['base']['release_sha256'])
    def submit():
        try:
            return branch.submit(result,expected_revision=0)['revision']
        except ValueError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:submit(),range(2)))
    assert sorted(map(str,outcomes))==['1','candidate_revision_conflict']
    assert branch.snapshot()['revision']==1


def test_wrong_branch_does_not_commit(sample):
    branch=CandidateBranch('1'*64)
    with pytest.raises(ValueError,match='candidate_base_conflict'):
        branch.submit(build(sample),expected_revision=0)
    assert branch.snapshot()=={'revision':0,'head':None}


def test_submit_holds_isolated_candidate(sample):
    result=build(sample)
    branch=CandidateBranch(sample[1]['base']['release_sha256'])
    branch.submit(result,expected_revision=0)
    result['candidate']['candidate_id']='mutated'
    snap=branch.snapshot()
    snap['head']['candidate']['candidate_id']='also-mutated'
    assert branch.snapshot()['head']['candidate']['candidate_id']=='candidate-truth-002'


@pytest.mark.parametrize('field,value',[('authorized',True),('real_release_ready',True),('publication_status','published'),('quality_status','passed')])
def test_candidate_flags_cannot_be_promoted(sample,field,value):
    result=build(sample)
    result['candidate'][field]=value
    with pytest.raises(ValueError,match='candidate_status_invalid'):
        CandidateBranch(sample[1]['base']['release_sha256']).submit(result,expected_revision=0)


def test_whole_geometry_resource_replace(sample):
    source,change,_=sample
    truth=json.loads(source['truth.json'])
    change['operations'][1].update(role='geometry',expected_sha256=truth['geometry']['sha256'])
    assert validate_candidate(build(sample))


def test_empty_object_set_rejected(sample):
    objects=json.loads(sample[0]['objects.json'])
    sample[1]['operations']=[{'op':'object.remove','object_id':o['object_id'],'expected_object_sha256':object_digest(o)} for o in objects['instances']]
    with pytest.raises(ValueError,match='empty_object_set_unsupported'):
        build(sample)


def test_generated_candidate_is_reproducible(sample):
    root=Path(__file__).resolve().parents[1]/'examples/spatial-change'
    result=build(sample)
    assert json.loads((root/'change.json').read_text())==sample[1]
    assert json.loads((root/'candidate.json').read_text())==result['candidate']
    blobs={p.relative_to(root/'candidate').as_posix():p.read_bytes() for p in (root/'candidate').rglob('*') if p.is_file()}
    assert blobs==result['blobs']
