import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.views.agent.voxel import SCHEMA, VoxelSession
from packages.views.agent.voxel_sample import build_voxel_sample


@pytest.fixture
def sample():
    return build_voxel_sample()


def edit(files,fn):
    manifest = json.loads(files['agent-voxel.json'])
    fn(manifest)
    files['agent-voxel.json'] = json.dumps(manifest).encode()


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))


@pytest.mark.parametrize('x,state,reason',[(.5,'unknown','unobserved'),(1.5,'observed_free','synthetic_observation'),
    (2.5,'occupied','synthetic_observation'),(3.5,'unknown','degraded'),(4.5,'unknown','conflict')])
def test_binary_codes(sample,x,state,reason):
    result = VoxelSession(*sample).query([x,.5,.5])
    assert (result['state'],result['reason']) == (state,reason)
    assert not result['robot_ready'] and not result['authorized']


def test_unlisted_chunk_is_unknown(sample):
    result = VoxelSession(*sample).query([5.5,5.5,.5])
    assert result['state']=='unknown' and result['reason']=='missing_chunk'


def test_missing_listed_chunk_is_error(sample):
    files,pin = sample
    del files['chunks/0-0-0.u8']
    with pytest.raises(ValueError,match='listed_chunk_missing'):
        VoxelSession(files,pin)


@pytest.mark.parametrize('point,state', [([0,0,0],'unknown'),([10,0,0],'out_of_scope'),([-0.001,0,0],'out_of_scope'),
    ([5,0,0],'unknown'),([1,0,0],'observed_free'),([0,1,0],'observed_free'),([0,0,1],'out_of_scope')])
def test_half_open_boundaries_and_x_fastest(sample,point,state):
    assert VoxelSession(*sample).query(point)['state']==state


@pytest.mark.parametrize('point', [[float('nan'),0,0],[float('inf'),0,0],[True,0,0],[1,2],[10**1000,0,0]])
def test_invalid_query(sample,point):
    with pytest.raises(ValueError,match='finite_numbers'):
        VoxelSession(*sample).query(point)


def test_payload_tampering(sample):
    files,pin=sample
    files['chunks/0-0-0.u8']=bytes([1]*25)
    with pytest.raises(ValueError,match='integrity_mismatch'):
        VoxelSession(files,pin)


def test_unknown_code_with_valid_digest(sample):
    files,pin=sample
    raw=bytes([255]*25)
    files['chunks/0-0-0.u8']=raw
    edit(files,lambda m:m['chunks'][0]['member'].update(sha256=hashlib.sha256(raw).hexdigest()))
    with pytest.raises(ValueError,match='unsupported_voxel_code'):
        VoxelSession(files,pin)


@pytest.mark.parametrize('field,value,message', [
    ('frame_id','other','source_binding_mismatch'),('origin_m',[1,0,0],'source_scope_mismatch'),
    ('dimensions',[9,10,1],'chunk_aligned'),('dimensions',[4096,4096,4096],'grid_budget'),
    ('resolution_m',.5,'source_scope_mismatch'),('index_order','z_fastest','manifest_structure'),
    ('data_kind','real','manifest_structure'),('schema_version','cospace.agent-voxel/9','manifest_structure')])
def test_manifest_semantics(sample,field,value,message):
    files,pin=sample
    edit(files,lambda m:m.update({field:value}))
    with pytest.raises(ValueError,match=message):
        VoxelSession(files,pin)


def test_pinned_version_mismatch(sample):
    files,pin=sample
    pin=copy.deepcopy(pin)
    pin['source']['release_sha256']='1'*64
    with pytest.raises(ValueError,match='source_binding_mismatch'):
        VoxelSession(files,pin)


@pytest.mark.parametrize('required',[True,False])
def test_unknown_component(sample,required):
    files,pin=sample
    edit(files,lambda m:m['components'].append({'id':'future','role':'esdf','encoding':'future/1','required':required,'depends_on':[]}))
    if required:
        with pytest.raises(ValueError,match='unsupported_required_component'):
            VoxelSession(files,pin)
    else:
        assert VoxelSession(files,pin).skipped_components == ('future',)


def test_required_component_cannot_depend_on_skipped(sample):
    files,pin=sample
    def change(m):
        m['components'].append({'id':'future','role':'esdf','encoding':'future/1','required':False,'depends_on':[]})
        m['components'][0]['depends_on']=['future']
    edit(files,change)
    with pytest.raises(ValueError,match='unsupported_component_dependency'):
        VoxelSession(files,pin)


def test_dependency_cycle(sample):
    files,pin=sample
    edit(files,lambda m:m['components'][0].update(depends_on=['occupancy']))
    with pytest.raises(ValueError,match='dependency_cycle'):
        VoxelSession(files,pin)


def test_missing_dependency(sample):
    files,pin=sample
    edit(files,lambda m:m['components'][0].update(depends_on=['missing']))
    with pytest.raises(ValueError,match='missing_component_dependency'):
        VoxelSession(files,pin)


@pytest.mark.parametrize('change,message', [
    (lambda m:m['chunks'].append(copy.deepcopy(m['chunks'][0])),'duplicate_or_outside_chunk'),
    (lambda m:m['chunks'][0].update(index=[2,0,0]),'outside_chunk'),
    (lambda m:m['chunks'][0].update(index=[0.0,0,0]),'literal_chunk_index'),
    (lambda m:m['components'][0].update(required=False),'occupancy_must_be_required'),
    (lambda m:m['chunks'][0]['member'].update(bytes=24),'chunk_integrity_mismatch')])
def test_structural_relationships(sample,change,message):
    files,pin=sample
    edit(files,change)
    with pytest.raises(ValueError,match=message):
        VoxelSession(files,pin)


def test_queries_hold_original_immutable_bytes(sample):
    files,pin=sample
    session=VoxelSession(files,pin)
    files['chunks/0-0-0.u8']=bytes([2]*25)
    first=session.query([1.5,.5,.5])
    first['source']['release_id']='changed'
    assert session.query([1.5,.5,.5])['state']=='observed_free'
    assert session.query([1.5,.5,.5])['source']['release_id']!='changed'


def test_extra_member_rejected(sample):
    files,pin=sample
    files['extra.bin']=b'\0'
    with pytest.raises(ValueError,match='unreferenced_members'):
        VoxelSession(files,pin)


def test_full_three_dimensional_indexing_and_negative_origin(sample):
    files,pin=sample
    m=json.loads(files['agent-voxel.json'])
    # Coordinate math fixture only: independently supplied scope pin is adjusted.
    pin['bounds']=[[-2,-2,-2],[0,0,0]]
    m.update(origin_m=[-2,-2,-2],dimensions=[2,2,2],chunk_shape=[2,2,2])
    raw=bytes([0,1,2,3,4,1,2,3])
    m['chunks']=[{'index':[0,0,0],'member':{'path':'chunks/only.u8','sha256':hashlib.sha256(raw).hexdigest(),'bytes':8}}]
    session=VoxelSession({'agent-voxel.json':json.dumps(m).encode(),'chunks/only.u8':raw},pin)
    assert session.query([-1.5,-1.5,-.5])['reason']=='conflict'  # offset 4
    assert session.query([-.5,-1.5,-1.5])['state']=='observed_free'  # offset 1
    assert session.query([-1.5,-.5,-1.5])['state']=='occupied'  # offset 2


def test_zero_listed_chunks_remains_all_unknown(sample):
    files,pin=sample
    m=json.loads(files['agent-voxel.json'])
    m['chunks']=[]
    session=VoxelSession({'agent-voxel.json':json.dumps(m).encode()},pin)
    assert session.query([1.5,.5,.5])['reason']=='missing_chunk'


@pytest.mark.parametrize('path',['../escape','/absolute','C:/absolute','chunks\\bad'])
def test_unsafe_paths(sample,path):
    files,pin=sample
    files[path]=b'\0'
    with pytest.raises(ValueError,match='unsafe_member_path'):
        VoxelSession(files,pin)


def test_example_bytes_match_builder():
    root=Path(__file__).resolve().parents[1]/'examples/agent-voxel'
    files={str(p.relative_to(root/'synthetic')).replace('\\','/'):p.read_bytes() for p in (root/'synthetic').rglob('*') if p.is_file()}
    generated,pin=build_voxel_sample()
    assert files==generated
    assert json.loads((root/'expected-source.json').read_text())==pin
    assert VoxelSession(files,pin).loaded_chunk_bytes==75
