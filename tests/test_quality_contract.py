import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.spatial.quality_contract import SCHEMA, evaluate_quality, normalize_observation, validate_quality_document

NOW = '2026-10-28T00:30:00Z'


@pytest.fixture
def sample():
    return json.loads((Path(__file__).resolve().parents[1] / 'examples/quality-profile/equipment-synthetic.json').read_text(encoding='utf-8'))


def evaluate(sample, now=NOW):
    return evaluate_quality(sample['profile'], sample['assessment'], now=now)


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text(encoding='utf-8')))


def test_declared_limits_do_not_grant_authorization(sample):
    result = evaluate(sample)
    assert result['declared_limits_met'] and result['observed_ratio'] == .8
    assert not any(result[k] for k in ('authorized', 'robot_ready', 'real_release_ready', 'evidence_verified'))


@pytest.mark.parametrize('state', ['occupied', 'observed_free', 'unknown'])
@pytest.mark.parametrize('reason', ['degraded', 'conflict'])
def test_diagnostics_force_unknown(sample, state, reason):
    observation = sample['observation']
    observation.update(state=state, reasons=[reason])
    assert normalize_observation(observation)['state'] == 'unknown'
    assert observation['state'] == state


def test_unobserved_is_unknown_without_fake_evidence(sample):
    sample['observation'].update(state='unknown', reasons=['unobserved'], evidence=[])
    assert normalize_observation(sample['observation'])['state'] == 'unknown'


@pytest.mark.parametrize('change,message', [
    ({'state':'observed_free','evidence':[]}, 'requires_evidence'),
    ({'state':'unknown','reasons':[]}, 'requires_reason'),
    ({'state':'occupied','reasons':['unobserved']}, 'cannot_be_unobserved'),
    ({'state':'unknown','reasons':['conflict'],'evidence':[]}, 'requires_evidence'),
    ({'state':'free'}, 'structure'),
])
def test_invalid_observation(sample, change, message):
    sample['observation'].update(change)
    with pytest.raises(ValueError, match=message):
        normalize_observation(sample['observation'])


@pytest.mark.parametrize('field,value', [('total_cells',80),('unobserved',0),('occupied',40)])
def test_coverage_cannot_shrink_or_double_count_denominator(sample, field, value):
    sample['assessment']['coverage'][field] = value
    with pytest.raises(ValueError, match='denominator_mismatch'):
        evaluate(sample)


def test_semantics_cannot_change_target_set(sample):
    sample['assessment']['semantics']['target_objects_ref']['sha256'] = '1'*64
    with pytest.raises(ValueError, match='semantic_denominator_mismatch'):
        evaluate(sample)


def test_semantics_cannot_shrink_denominator(sample):
    sample['assessment']['semantics'].update(required_count=9, confirmed_count=9)
    with pytest.raises(ValueError, match='semantic_denominator_mismatch'):
        evaluate(sample)


def test_semantic_zero_denominator_is_not_one_hundred_percent(sample):
    sample['profile']['rule']['expected_object_count'] = 0
    sample['assessment']['semantics'].update(required_count=0, confirmed_count=0)
    result = evaluate(sample)
    assert result['confirmed_semantic_ratio'] is None
    assert 'insufficient_confirmed_semantics' in result['reasons']


@pytest.mark.parametrize('key', ['frame_id','scope_ref','bounds'])
def test_scope_mismatch(sample, key):
    scope = sample['assessment']['scope']
    if key == 'frame_id':
        scope[key] = 'different-frame'
    elif key == 'scope_ref':
        scope[key]['sha256'] = '1'*64
    else:
        scope[key] = [[1,0,0],[11,10,1]]
    with pytest.raises(ValueError, match='scope_frame_mismatch'):
        evaluate(sample)


def test_procedure_identity_mismatch(sample):
    sample['assessment']['procedure_ref']['sha256'] = '1'*64
    with pytest.raises(ValueError, match='procedure_mismatch'):
        evaluate(sample)


def test_oldest_evidence_drives_age(sample):
    result = evaluate(sample, '2026-10-28T01:05:00Z')
    assert 'stale_observation' in result['reasons']


def test_age_boundary_is_inclusive(sample):
    assert 'stale_observation' not in evaluate(sample, '2026-10-28T01:00:00Z')['reasons']


def test_operational_freshness_is_required(sample):
    sample['profile']['freshness']['max_age_s'] = None
    with pytest.raises(ValueError, match='requires_max_age'):
        evaluate(sample)


def test_history_can_explicitly_omit_age_limit(sample):
    sample['profile'].update(mode='historical')
    sample['profile']['freshness']['max_age_s'] = None
    assert 'stale_observation' not in evaluate(sample, '2026-11-01T00:00:00Z')['reasons']


@pytest.mark.parametrize('field', ['max_error_m','value_m'])
def test_missing_geometry_is_not_pass(sample, field):
    if field == 'max_error_m':
        sample['profile']['rule'][field] = None
    else:
        sample['assessment']['geometry'].update(value_m=None, basis='not_assessed')
    assert 'geometry_not_assessed' in evaluate(sample)['reasons']


def test_error_limit_exceeded(sample):
    sample['assessment']['geometry']['value_m'] = .11
    assert 'geometry_limit_exceeded' in evaluate(sample)['reasons']


@pytest.mark.parametrize('value', [float('nan'), float('inf')])
def test_nonfinite(sample, value):
    sample['assessment']['geometry']['value_m'] = value
    with pytest.raises(ValueError, match='non_finite'):
        evaluate(sample)


@pytest.mark.parametrize('value', ['2026-02-30T00:00:00Z','2026-10-28T00:30Z'])
def test_invalid_clock(sample, value):
    with pytest.raises(ValueError):
        evaluate(sample, value)


def test_future_observation(sample):
    with pytest.raises(ValueError, match='future_observation'):
        evaluate(sample, '2026-10-28T00:05:00Z')


def test_unaligned_grid(sample):
    sample['profile']['scope']['cell_size_m'] = .3
    with pytest.raises(ValueError, match='grid_aligned'):
        evaluate(sample)


def test_literal_count(sample):
    sample['assessment']['coverage']['total_cells'] = 100.0
    with pytest.raises(ValueError, match='literal_integer'):
        evaluate(sample)


def test_undeclared_fields_and_versions(sample):
    sample['profile']['schema_version'] = 'cospace.quality-profile/9'
    with pytest.raises(ValueError, match='structure'):
        validate_quality_document(sample['profile'])


def test_coverage_threshold_is_not_rounded_up(sample):
    sample['profile']['rule']['min_observed_ratio'] = .80001
    assert 'insufficient_observed_coverage' in evaluate(sample)['reasons']


def test_semantic_threshold_is_not_rounded_up(sample):
    sample['profile']['rule']['min_confirmed_semantic_ratio'] = .90001
    assert 'insufficient_confirmed_semantics' in evaluate(sample)['reasons']


def test_geometry_missing_value_cannot_claim_assessment(sample):
    sample['assessment']['geometry']['value_m'] = None
    with pytest.raises(ValueError, match='geometry_basis_value_mismatch'):
        evaluate(sample)


def test_scope_budget(sample):
    sample['profile']['scope']['cell_size_m'] = .001
    with pytest.raises(ValueError, match='scope_cell_budget_exceeded'):
        evaluate(sample)
