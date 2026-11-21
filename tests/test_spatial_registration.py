from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from packages.spatial.georeference import RegistrationInput, evaluate_registration


@pytest.fixture
def controls():
    return json.loads(Path('contracts/examples/spatial-registration-campus.json').read_text(encoding='utf-8'))


def run(document):
    return evaluate_registration(document, expected_source=document['source'])


def test_known_answer_and_no_implicit_geographic_approval(controls):
    report = run(controls)
    golden = json.loads(Path('contracts/examples/spatial-registration-campus-report.json').read_text())
    assert report['input_sha256'] == golden['input_sha256']
    for purpose in ('fit', 'check'):
        assert report['metrics'][purpose] == pytest.approx(golden['metrics'][purpose])
    assert report['calculation_status'] == 'checks_passed'
    assert report['metrics']['check']['max_horizontal_m'] == pytest.approx(np.hypot(.04, .02))
    assert report['metrics']['check']['max_vertical_m'] == pytest.approx(.04)
    k1 = report['controls'][3]
    assert k1['delta_m'] == pytest.approx([-.03, .02, -.04])
    assert report['review_status'] == 'not_reviewed'
    for field in ('control_evidence_verified', 'can_focus_geographic_map', 'robot_ready'):
        assert report[field] is False


def test_explicit_direction_with_a_quarter_turn_and_translation(controls):
    controls['matrix'] = [[0., -1., 0., 10.], [1., 0., 0., 20.], [0., 0., 1., -3.], [0., 0., 0., 1.]]
    for p in controls['controls']:
        x, y, z = p['source_m']
        p['target_m'] = [10-y, 20+x, z-3]
    report = run(controls)
    assert report['controls'][1]['predicted_m'] == [10., 120., -3.]
    assert report['metrics']['check']['max_horizontal_m'] == 0
    assert report['metrics']['check']['max_vertical_m'] == 0


@pytest.mark.parametrize('axis', [0, 2])
def test_each_check_dimension_can_block_a_candidate(controls, axis):
    first = run(controls)
    controls['controls'][5]['target_m'][axis] += .32
    report = run(controls)
    assert report['calculation_status'] == 'check_limits_exceeded'
    assert report['controls'][5]['within_limits'] is False
    assert report['metrics']['fit'] == first['metrics']['fit']
    assert report['input_sha256'] != first['input_sha256']
    assert not report['can_focus_geographic_map']


def test_source_is_compared_with_host_loaded_binding(controls):
    expected = deepcopy(controls['source'])
    controls['source']['model_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='registration_source_binding'):
        evaluate_registration(controls, expected_source=expected)


@pytest.mark.parametrize('change', ['scale', 'reflection', 'shear', 'last_row'])
def test_reject_non_rigid_or_wrong_homogeneous_matrix(controls, change):
    if change == 'scale':
        controls['matrix'][0][0] *= 1.01
    elif change == 'reflection':
        for row in controls['matrix'][:3]:
            row[0] *= -1
    elif change == 'shear':
        controls['matrix'][0][2] = .05
    else:
        controls['matrix'][3][0] = 1e-11
    with pytest.raises(ValueError, match='registration_proper_rigid_transform_required'):
        run(controls)


@pytest.mark.parametrize('field', ['id', 'source_m', 'target_m'])
def test_duplicate_checks_do_not_inflate_independence(controls, field):
    controls['controls'][3][field] = controls['controls'][0][field]
    with pytest.raises(ValueError, match='registration_duplicate_control'):
        run(controls)


@pytest.mark.parametrize('field', ['source_m', 'target_m'])
def test_collinear_check_groups_are_rejected(controls, field):
    for i, p in enumerate(controls['controls'][3:]):
        p[field] = [float(i+1), 1., 1.]
    with pytest.raises(ValueError, match='registration_degenerate_control_geometry'):
        run(controls)


def test_controls_inside_source_scope_and_separate_groups(controls):
    controls['controls'][3]['source_m'][0] = 500.
    with pytest.raises(ValueError, match='registration_control_outside_scope'):
        run(controls)
    controls['controls'][3]['source_m'][0] = 100.
    controls['controls'][3]['purpose'] = 'fit'
    with pytest.raises(ValueError, match='registration_three_controls_per_group_required'):
        run(controls)


@pytest.mark.parametrize('field,value', [('can_focus_geographic_map', True), ('review_status', 'approved'), ('workspace_scope', 'spoofed')])
def test_client_cannot_add_authority_fields(controls, field, value):
    controls[field] = value
    with pytest.raises(ValidationError):
        run(controls)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), True, '0.5'])
def test_nonfinite_or_coerced_values_are_rejected(controls, bad):
    controls['controls'][3]['source_m'][0] = bad
    with pytest.raises(ValidationError):
        run(controls)


def test_units_reference_and_target_geographic_adapter_are_explicit(controls):
    for field, value in [('unit', 'deg'), ('geographic_adapter', 'automatic'), ('vertical_reference', '')]:
        mutated = deepcopy(controls)
        mutated['target'][field] = value
        with pytest.raises(ValidationError):
            run(mutated)
    controls['target']['frame_id'] = controls['source']['frame_id']
    with pytest.raises(ValueError, match='registration_distinct_frames_required'):
        run(controls)


def test_parameter_budget_prevents_nonfinite_report_values(controls):
    controls['matrix'][0][3] = 1e308
    with pytest.raises(ValidationError):
        run(controls)


def test_published_schema_matches_runtime_contract():
    schema = json.loads(Path('contracts/schemas/spatial-registration-input-v0.1.schema.json').read_text())
    schema.pop('$schema')
    schema.pop('$id')
    assert schema == RegistrationInput.model_json_schema()
