"""F03 experimental metadata and conservative state semantics, not a runtime gate."""
import json
import math
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/quality-profile-v0.1.schema.json'
PARTS = ('observed_free', 'occupied', 'unobserved', 'degraded', 'conflict')


def utc(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value):
        raise ValueError('invalid_utc')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def validate_quality_document(document):
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('non_finite_number')
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)
    finite(document)
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    errors = list(Draft202012Validator(schema).iter_errors(document))
    if errors:
        raise ValueError(f'structure:{errors[0].message}')
    kind = document['kind']
    if kind == 'observation':
        if any(type(i) is not int for i in document['cell_index']):
            raise ValueError('cell_index_requires_literal_integer')
        reasons = document['reasons']
        if document['state'] == 'unknown' and not reasons:
            raise ValueError('unknown_requires_reason')
        if (document['state'] != 'unknown' or set(reasons) & {'degraded', 'conflict'}) and not document['evidence']:
            raise ValueError('observation_requires_evidence')
        refs = [(r['id'], r['sha256']) for r in document['evidence']]
        if len(set(refs)) != len(refs) or len({r[0] for r in refs}) != len(refs):
            raise ValueError('duplicate_or_conflicting_evidence')
        if document['state'] != 'unknown' and 'unobserved' in reasons:
            raise ValueError('known_state_cannot_be_unobserved')
        return {'metadata_valid': True, 'evidence_verified': False}

    scope = document['scope']
    cells = []
    for lower, upper in zip(*scope['bounds']):
        extent = upper - lower
        if extent <= 0 or not math.isfinite(extent):
            raise ValueError('invalid_scope_bounds')
        count = extent / scope['cell_size_m']
        if not math.isfinite(count) or count < 1 or count > 10000000 or abs(count-round(count)) > 1e-7:
            raise ValueError('scope_not_grid_aligned')
        cells.append(round(count))
    total = math.prod(cells)
    if total > 10000000:
        raise ValueError('scope_cell_budget_exceeded')
    if kind == 'profile':
        if type(document['rule']['expected_object_count']) is not int:
            raise ValueError('count_requires_literal_integer')
        age = document['freshness']['max_age_s']
        if document['mode'] == 'operational' and age is None:
            raise ValueError('operational_requires_max_age')
        if age is not None and type(age) is not int:
            raise ValueError('max_age_requires_literal_integer')
    else:
        coverage = document['coverage']
        semantics = document['semantics']
        for value in [coverage[k] for k in ('total_cells', *PARTS)] + [semantics[k] for k in ('required_count', 'confirmed_count')]:
            if type(value) is not int:
                raise ValueError('count_requires_literal_integer')
        if coverage['total_cells'] != total or sum(coverage[k] for k in PARTS) != total:
            raise ValueError('coverage_denominator_mismatch')
        if semantics['confirmed_count'] > semantics['required_count']:
            raise ValueError('semantic_count_mismatch')
        if utc(document['observed_until']) < utc(document['observed_from']):
            raise ValueError('reversed_observation_interval')
        geometry = document['geometry']
        if (geometry['basis'] == 'not_assessed') != (geometry['value_m'] is None):
            raise ValueError('geometry_basis_value_mismatch')
    return {'metadata_valid': True, 'evidence_verified': False, 'real_release_ready': False}


def normalize_observation(document):
    """Keep evidence diagnostics; never convert degradation/conflict to free space."""
    validate_quality_document(document)
    if document['kind'] != 'observation':
        raise ValueError('expected_observation')
    state = 'unknown' if set(document['reasons']) & {'degraded', 'conflict'} else document['state']
    return {**document, 'state': state}


def evaluate_quality(profile, assessment, *, now):
    """Evaluate declared aggregate metrics only; never grant robot capability."""
    validate_quality_document(profile)
    validate_quality_document(assessment)
    if profile['kind'] != 'profile' or assessment['kind'] != 'assessment':
        raise ValueError('expected_profile_and_assessment')
    if profile['scene_id'] != assessment['scene_id'] or profile['scope'] != assessment['scope']:
        raise ValueError('scene_scope_frame_mismatch')
    if profile['rule']['procedure_ref'] != assessment['procedure_ref']:
        raise ValueError('procedure_mismatch')
    current, start, end = utc(now), utc(assessment['observed_from']), utc(assessment['observed_until'])
    if end > current:
        raise ValueError('future_observation')
    c, s, rule = assessment['coverage'], assessment['semantics'], profile['rule']
    if s['target_objects_ref'] != rule['target_objects_ref'] or s['required_count'] != rule['expected_object_count']:
        raise ValueError('semantic_denominator_mismatch')
    observed = (c['observed_free'] + c['occupied']) / c['total_cells']
    semantic = s['confirmed_count'] / s['required_count'] if s['required_count'] else None
    failures = []
    if observed < rule['min_observed_ratio']:
        failures.append('insufficient_observed_coverage')
    if rule['min_confirmed_semantic_ratio'] > 0 and (semantic is None or semantic < rule['min_confirmed_semantic_ratio']):
        failures.append('insufficient_confirmed_semantics')
    limit, measured = rule['max_error_m'], assessment['geometry']['value_m']
    if limit is None or measured is None:
        failures.append('geometry_not_assessed')
    elif measured > limit:
        failures.append('geometry_limit_exceeded')
    max_age = profile['freshness']['max_age_s']
    # Conservative whole-scope age uses oldest evidence, not the newest frame.
    age = (current-start).total_seconds()
    if max_age is not None and age > max_age:
        failures.append('stale_observation')
    return {'observed_ratio': observed, 'confirmed_semantic_ratio': semantic,
            'oldest_observation_age_s': age, 'declared_limits_met': not failures,
            'reasons': failures, 'evidence_verified': False, 'authorized': False,
            'robot_ready': False, 'real_release_ready': False}
