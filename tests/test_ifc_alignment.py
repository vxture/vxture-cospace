import numpy as np
import pytest

from packages.construction.ifc_alignment import fit_ifc_alignment


@pytest.fixture
def controls():
    points = [[0, 0, 0], [2, 0, 1], [0, 2, 0], [3, 0, 1], [3, 2, 1], [5, 0, 0]]
    return {
        'profile': 'cospace.ifc-alignment-input/0.1',
        'ifc': {'frame_id': 'bim', 'artifact_sha256': 'a'*64, 'unit': 'm'},
        'cloud': {'frame_id': 'cloud', 'artifact_sha256': 'b'*64, 'unit': 'm'},
        'max_check_error_m': .02,
        'pairs': [{'id': f'p{i}', 'evidence_ref': f'e{i}', 'purpose': 'fit' if i < 3 else 'check',
                   'ifc_m': [x, y, z], 'cloud_m': [10-y, 20+x, z-1]}
                  for i, (x, y, z) in enumerate(points)],
    }


def run(controls, expected_ifc=None):
    return fit_ifc_alignment(controls, expected_ifc=expected_ifc or controls['ifc'],
                             expected_cloud=controls['cloud'])


def test_known_rigid_transform_and_held_out_controls(controls):
    result = run(controls)
    assert np.allclose(result['matrix_ifc_to_cloud'],
                       [[0, -1, 0, 10], [1, 0, 0, 20], [0, 0, 1, -1], [0, 0, 0, 1]])
    assert result['check']['max_m'] < 1e-10
    assert result['status'] == 'review_required'
    assert not result['alignment_verified']
    assert not result['control_evidence_verified']
    assert not result['real_release_ready']


def test_bad_check_does_not_change_fit(controls):
    first = run(controls)
    controls['pairs'][3]['cloud_m'][2] += .1
    result = run(controls)
    assert result['matrix_ifc_to_cloud'] == first['matrix_ifc_to_cloud']
    assert result['status'] == 'check_limit_exceeded'
    assert result['check']['max_m'] == pytest.approx(.1)


def test_source_digest_and_direction_binding(controls):
    with pytest.raises(ValueError, match='alignment_source_binding'):
        run(controls, expected_ifc=controls['cloud'])


@pytest.mark.parametrize('key', ['id', 'evidence_ref', 'ifc_m', 'cloud_m'])
def test_duplicate_fit_and_check_controls_rejected(controls, key):
    controls['pairs'][3][key] = controls['pairs'][0][key]
    with pytest.raises(ValueError, match='alignment_duplicate_control'):
        run(controls)


def test_reject_collinear_check_controls(controls):
    for i, p in enumerate(controls['pairs'][3:], start=3):
        p['ifc_m'] = [i, 0, 0]
    with pytest.raises(ValueError, match='alignment_degenerate_control_geometry'):
        run(controls)


def test_require_separate_check_group(controls):
    controls['pairs'][3]['purpose'] = 'fit'
    with pytest.raises(ValueError, match='alignment_requires_three_points_per_group'):
        run(controls)
