"""F01/F02 contract boundaries, with no claim of measured data readiness."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.data.observation_contract import SCHEMA, validate_observation_input


@pytest.fixture
def sample():
    path = Path(__file__).resolve().parents[1] / 'examples/observation-input/equipment-synthetic.json'
    return json.loads(path.read_text(encoding='utf-8'))


def test_schema_is_valid():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text(encoding='utf-8')))


def test_unverified_metadata_does_not_become_ready(sample):
    result = validate_observation_input(sample)
    assert result['metadata_valid']
    assert not any(result[k] for k in ('payload_verified', 'evidence_verified', 'algorithm_ready', 'real_release_ready'))


@pytest.mark.parametrize('role', ['construction', 'independent_check', 'independent_consumption', 'change'])
def test_declared_roles_are_metadata_only(sample, role):
    sample['streams'][0]['role'] = role
    sample['data_kind'] = 'real'
    assert not validate_observation_input(sample)['algorithm_ready']


@pytest.mark.parametrize('field,value,diagnostic', [
    ('frame_id', 'missing', 'unknown_frame'),
    ('member_id', 'missing', 'unknown_member'),
    ('extra', True, 'structure'),
])
def test_bad_stream(sample, field, value, diagnostic):
    sample['streams'][0][field] = value
    with pytest.raises(ValueError, match=diagnostic):
        validate_observation_input(sample)


@pytest.mark.parametrize('path', ['../escape', '/absolute', 'C:/absolute', 'raw\\escape', 'raw//file', 'raw/./file', 'raw/file.'])
def test_unsafe_member_path(sample, path):
    sample['members'][0]['path'] = path
    with pytest.raises(ValueError, match='unsafe_member_path'):
        validate_observation_input(sample)


@pytest.mark.parametrize('field', ['used_for_fit', 'used_for_tuning'])
def test_independent_point_cannot_be_used_for_development(sample, field):
    sample['reference_points'][0][field] = True
    with pytest.raises(ValueError, match='structure'):
        validate_observation_input(sample)


@pytest.mark.parametrize('collection', ['frames', 'members', 'streams', 'reference_points'])
def test_duplicate_identity(sample, collection):
    sample[collection].append(copy.deepcopy(sample[collection][0]))
    with pytest.raises(ValueError, match='duplicate'):
        validate_observation_input(sample)


@pytest.mark.parametrize('matrix,diagnostic', [
    ([[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,1,1]], 'invalid_homogeneous_row'),
    ([[2,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]], 'non_rigid_rotation'),
    ([[-1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]], 'reflection_not_allowed'),
])
def test_invalid_rigid_transform(sample, matrix, diagnostic):
    sample['transforms'][0]['matrix'] = matrix
    with pytest.raises(ValueError, match=diagnostic):
        validate_observation_input(sample)


def test_transform_cycle(sample):
    reverse = copy.deepcopy(sample['transforms'][0])
    reverse.update(source_frame_id='scene', target_frame_id='lidar')
    sample['transforms'].append(reverse)
    with pytest.raises(ValueError, match='transform_cycle'):
        validate_observation_input(sample)


def test_verified_clock_requires_measurement_metadata(sample):
    sample['streams'][0]['clock']['sync_status'] = 'verified'
    with pytest.raises(ValueError, match='structure'):
        validate_observation_input(sample)


def test_reversed_time_range(sample):
    sample['streams'][0]['clock'].update(utc_start='2026-10-28T02:00:00Z', utc_end='2026-10-28T01:00:00Z')
    with pytest.raises(ValueError, match='reversed_observation_interval'):
        validate_observation_input(sample)


def test_invalid_calendar_date(sample):
    sample['reference_points'][0]['measured_at'] = '2026-02-30T00:00:00Z'
    with pytest.raises(ValueError, match='structure'):
        validate_observation_input(sample)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_number(sample, value):
    sample['reference_points'][0]['position'][0] = value
    with pytest.raises(ValueError, match='non_finite_number'):
        validate_observation_input(sample)


def test_float_bytes_rejected(sample):
    sample['members'][0]['bytes'] = 1.0
    with pytest.raises(ValueError, match='literal_integer'):
        validate_observation_input(sample)


def test_verified_declaration_does_not_verify_evidence(sample):
    sample['streams'][0]['clock'].update(
        sync_status='verified', utc_start='2026-10-28T00:00:00Z',
        utc_end='2026-10-28T00:01:00Z', uncertainty_ms=0.2,
        mapping_ref={'id': 'clock-mapping', 'sha256': '0' * 64})
    assert not validate_observation_input(sample)['evidence_verified']


def test_valid_rotation_and_translation(sample):
    sample['transforms'][0]['matrix'] = [[0,-1,0,4],[1,0,0,2],[0,0,1,1],[0,0,0,1]]
    assert validate_observation_input(sample)['metadata_valid']


def test_unknown_contract_version(sample):
    sample['schema_version'] = 'cospace.observation-input/99'
    with pytest.raises(ValueError, match='structure'):
        validate_observation_input(sample)


def test_incomplete_utc_interval(sample):
    sample['streams'][0]['clock']['utc_start'] = '2026-10-28T00:00:00Z'
    with pytest.raises(ValueError, match='structure'):
        validate_observation_input(sample)


@pytest.mark.parametrize('value', ['20261028T000000Z', '2026-10-28T00:00Z', '2026-10-28T08:00:00+08:00'])
def test_utc_canonical_representation(sample, value):
    sample['reference_points'][0]['measured_at'] = value
    with pytest.raises(ValueError, match='structure'):
        validate_observation_input(sample)
