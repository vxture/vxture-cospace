import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.spatial.changes import digest
from packages.views.agent.voxel import VoxelSession
from packages.views.agent.voxel_changes import SCHEMA, VoxelCandidatePreview, build_voxel_candidate
from packages.views.agent.voxel_change_sample import build_voxel_change_sample


@pytest.fixture
def sample():
    return build_voxel_change_sample()


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))


def test_add_replace_remove_and_unchanged_bytes(sample):
    before=copy.deepcopy(sample)
    result=build_voxel_candidate(*sample)
    assert sample==before
    assert result['files']['chunks/0-1-0.u8']==sample[0]['chunks/0-1-0.u8']
    assert result['unchanged_chunks']==1 and result['changed_chunk_count']==3
    preview=VoxelCandidatePreview(*sample,result)
    assert preview.query([5.5,5.5,.5])['state']=='occupied'
    assert preview.query([.5,.5,.5])['state']=='observed_free'
    assert preview.query([5.5,.5,.5])['reason']=='missing_chunk'
    assert preview.query([.5,5.5,.5])['reason']=='unobserved'
    assert VoxelSession(sample[0],sample[1]).query([.5,.5,.5])['state']=='unknown'


def test_candidate_rejected_by_regular_runtime(sample):
    result=build_voxel_candidate(*sample)
    with pytest.raises(ValueError,match='package_budget_or_manifest'):
        VoxelSession(result['files'],sample[1])


def test_impacts_are_chunk_bounds_not_whole_scene(sample):
    result=build_voxel_candidate(*sample)
    assert result['impacts'][0]['bounds']==[[5,5,0],[10,10,1]]
    assert result['impacts'][2]['after_missing']
    assert result['impacts'][2]['after_sha256'] is None
    assert not result['authorized'] and not result['robot_ready']


@pytest.mark.parametrize('key', ['base_package_id','base_package_sha256'])
def test_base_preconditions(sample,key):
    sample[2][key]='1'*64 if key.endswith('sha256') else 'other'
    with pytest.raises(ValueError,match='base_package_conflict'):
        build_voxel_candidate(*sample)


def test_add_to_present_chunk_conflicts(sample):
    sample[2]['operations'][0]['index']=[0,1,0]
    with pytest.raises(ValueError,match='expected_absent_conflict'):
        build_voxel_candidate(*sample)


def test_replace_absent_chunk_conflicts(sample):
    sample[2]['operations']=sample[2]['operations'][1:]
    sample[2]['operations'][0]['index']=[1,1,0]
    with pytest.raises(ValueError,match='old_digest_conflict'):
        build_voxel_candidate(*sample)


@pytest.mark.parametrize('i',[1,2])
def test_wrong_old_digest(sample,i):
    sample[2]['operations'][i]['expected_sha256']='1'*64
    with pytest.raises(ValueError,match='old_digest_conflict'):
        build_voxel_candidate(*sample)


def test_duplicate_logical_index(sample):
    sample[2]['operations'][1]['index']=[1,1,0]
    with pytest.raises(ValueError,match='duplicate_chunk_operation'):
        build_voxel_candidate(*sample)


@pytest.mark.parametrize('index,message',[([2,0,0],'out_of_scope'),([1.0,1,0],'literal_index'),([-1,0,0],'structure')])
def test_invalid_index(sample,index,message):
    sample[2]['operations'][0]['index']=index
    with pytest.raises(ValueError,match=message):
        build_voxel_candidate(*sample)


def test_payload_digest_failure(sample):
    sample[3]['input/add.u8']=bytes([1]*25)
    with pytest.raises(ValueError,match='integrity_mismatch'):
        build_voxel_candidate(*sample)


@pytest.mark.parametrize('raw',[bytes([255]*25),bytes([1]*24)])
def test_bad_payload_with_valid_digest(sample,raw):
    sample[3]['input/add.u8']=raw
    sample[2]['operations'][0]['replacement'].update(bytes=len(raw),sha256=digest(raw))
    with pytest.raises(ValueError,match='invalid_occupancy_payload'):
        build_voxel_candidate(*sample)


def test_evidence_missing(sample):
    del sample[3]['evidence/change.txt']
    with pytest.raises(ValueError,match='resource_missing'):
        build_voxel_candidate(*sample)


def test_extra_resource(sample):
    sample[3]['extra']=b'x'
    with pytest.raises(ValueError,match='unreferenced_resources'):
        build_voxel_candidate(*sample)


def test_original_corrupt_before_change(sample):
    sample[0]['chunks/0-0-0.u8']+=b' '
    with pytest.raises(ValueError,match='integrity_mismatch'):
        build_voxel_candidate(*sample)


@pytest.mark.parametrize('field,value',[('schema_version','cospace.voxel-change/99'),('data_kind','real'),('operations',[]),('evidence',[])])
def test_unsupported_envelope(sample,field,value):
    sample[2][field]=value
    with pytest.raises(ValueError,match='structure'):
        build_voxel_candidate(*sample)


def test_candidate_identity_must_be_new(sample):
    sample[2]['candidate_package_id']=sample[2]['base_package_id']
    with pytest.raises(ValueError,match='candidate_identity_reuse'):
        build_voxel_candidate(*sample)


def test_candidate_tampering_detected_by_rebuild(sample):
    result=build_voxel_candidate(*sample)
    result['files']['chunks/1-1-0.u8']=bytes([1]*25)
    with pytest.raises(ValueError,match='candidate_rebuild_mismatch'):
        VoxelCandidatePreview(*sample,result)


def test_impact_tampering_detected(sample):
    result=build_voxel_candidate(*sample)
    result['impacts'][0]['bounds']=[[0,0,0],[1,1,1]]
    with pytest.raises(ValueError,match='candidate_rebuild_mismatch'):
        VoxelCandidatePreview(*sample,result)


def test_preview_returns_candidate_not_fake_release(sample):
    result=build_voxel_candidate(*sample)
    response=VoxelCandidatePreview(*sample,result).query([.5,.5,.5])
    assert 'source' not in response and 'package_sha256' not in response
    assert response['publication_status']=='candidate_only'
    assert response['candidate_manifest_sha256']==result['candidate_manifest_sha256']


def test_candidate_example_reproducible(sample):
    root=Path(__file__).resolve().parents[1]/'examples/voxel-change'
    result=build_voxel_candidate(*sample)
    files={p.relative_to(root/'candidate').as_posix():p.read_bytes() for p in (root/'candidate').rglob('*') if p.is_file()}
    assert files==result['files']
    assert json.loads((root/'change.json').read_text())==sample[2]
    report=json.loads((root/'inspection.json').read_text())
    assert report['candidate_manifest_sha256']==result['candidate_manifest_sha256']


def test_no_op_replace_rejected(sample):
    raw=sample[0]['chunks/0-0-0.u8']
    sample[3]['input/replace.u8']=raw
    sample[2]['operations'][1]['replacement'].update(bytes=len(raw),sha256=digest(raw))
    with pytest.raises(ValueError,match='no_op_chunk_replace'):
        build_voxel_candidate(*sample)


def test_remove_all_blocks_keeps_unknown(sample):
    manifest=json.loads(sample[0]['agent-voxel.json'])
    sample[2]['operations']=[{'op':'chunk.remove','index':c['index'],'expected_sha256':c['member']['sha256']} for c in manifest['chunks']]
    del sample[3]['input/add.u8']
    del sample[3]['input/replace.u8']
    result=build_voxel_candidate(*sample)
    assert VoxelCandidatePreview(*sample,result).query([1,1,0])['reason']=='missing_chunk'


def test_input_order_cannot_change_target_bytes(sample):
    result=build_voxel_candidate(*sample)
    sample[2]['operations'].reverse()
    other=build_voxel_candidate(*sample)
    assert other['candidate_manifest_sha256']==result['candidate_manifest_sha256']
    assert other['change_sha256']!=result['change_sha256']


@pytest.mark.parametrize('path',['../escape','C:/absolute','/rooted','input\\bad'])
def test_unsafe_resource_paths(sample,path):
    sample[3][path]=b'bad'
    with pytest.raises(ValueError,match='unsafe_resource_path'):
        build_voxel_candidate(*sample)


def test_preview_session_isolated_from_later_candidate_mutation(sample):
    result=build_voxel_candidate(*sample)
    preview=VoxelCandidatePreview(*sample,result)
    result['files']['chunks/1-1-0.u8']=bytes([1]*25)
    assert preview.query([5.5,5.5,.5])['state']=='occupied'
