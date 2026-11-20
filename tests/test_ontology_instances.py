"""B03 production validator: negative matrix, time-aware graphs and boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from packages.ontology.kernel import builtin_catalog, canonical_bytes, validate_instances
from packages.ontology.kernel.instances import MAX_INSTANCE_BYTES

ROOT = Path('examples/ontology/parks')
CASES = json.loads(Path('tests/fixtures/ontology-instances/negative-matrix.json').read_text(encoding='utf-8'))['cases']


def sample(kind='manufacturing'):
    return json.loads((ROOT / f'{kind}.json').read_text(encoding='utf-8'))


def validate(document, **kwargs):
    return validate_instances(canonical_bytes(document), builtin_catalog(), rule_set='park-baseline', **kwargs)


def codes(report):
    return {d['code'] for d in report['diagnostics']}


@pytest.mark.parametrize('kind', ['research-office', 'manufacturing', 'logistics'])
def test_three_complete_synthetic_packages_pass_without_claiming_completeness(kind):
    document = sample(kind)
    before = deepcopy(document)
    report = validate(document)
    assert report['valid'], report
    assert codes(report) == {'incomplete_coverage', 'geometry_not_recorded'}
    assert report['rule_set']['version'] == '0.1.0'
    assert document == before
    assert report == validate(document)


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_all_negative_matrix_cases_are_now_rejected_with_locatable_diagnostics(case):
    document = sample(case['base'])
    for patch in case['patches']:
        keys = patch['path'].strip('/').split('/')
        target = document
        for key in keys[:-1]:
            target = target[int(key)] if isinstance(target, list) else target[key]
        key = int(keys[-1]) if isinstance(target, list) else keys[-1]
        if patch['op'] == 'remove':
            del target[key]
        else:
            target[key] = deepcopy(patch['value'])
    report = validate(document)
    assert not report['valid'], case['id']
    assert any(d['code'] == case['expected']['code'] and
               case['expected']['path'] in [d['path'], *d.get('related_paths', [])]
               for d in report['diagnostics']), report


def test_boolean_never_satisfies_numeric_property_or_unit():
    document = sample()
    document['entities'][11]['properties']['rated_voltage']['value'] = True
    assert not validate(document)['valid']
    document['entities'][11]['properties']['rated_voltage']['value'] = -1
    assert 'property_below_minimum' in codes(validate(document))


def test_duplicate_support_does_not_count_as_two_targets():
    document = sample()
    edge = deepcopy(document['assertions'][5])
    edge['id'] = 'duplicate-support'
    document['assertions'].append(edge)
    assert validate(document)['valid']
    edge['object_id'] = 'operator'
    assert 'cardinality_violation' in codes(validate(document))


def test_role_requires_continuous_time_coverage_and_accepts_touching_half_open_intervals():
    document = sample()
    second = deepcopy(document['assertions'][5])
    second['id'] = 'second-half'
    second['valid_time']['start'] = '2026-06-01T00:00:00Z'
    document['assertions'][5]['valid_time']['end'] = second['valid_time']['start']
    document['assertions'].append(second)
    assert validate(document)['valid']
    second['valid_time']['start'] = '2026-06-02T00:00:00Z'
    assert 'role_interval_uncovered' in codes(validate(document))


def test_open_ended_role_cannot_be_supported_by_finite_relationships():
    document = sample()
    document['entities'][8]['valid_time']['end'] = None
    assert 'role_interval_uncovered' in codes(validate(document))
    for edge in document['assertions'][5:7]:
        edge['valid_time']['end'] = None
    assert validate(document)['valid']


def test_nonoverlapping_spatial_reparenting_is_legal_but_overlap_and_cycle_fail():
    document = sample()
    previous = document['assertions'][3]
    previous['valid_time']['end'] = '2026-06-01T00:00:00Z'
    new = deepcopy(previous)
    new.update(id='reparent', object_id='site')
    new['valid_time'] = {'start': previous['valid_time']['end'], 'end': '2027-01-01T00:00:00Z'}
    document['assertions'].append(new)
    assert validate(document)['valid']
    new['valid_time']['start'] = '2026-05-01T00:00:00Z'
    assert 'multiple_spatial_parents' in codes(validate(document))


def test_union_graph_cycle_is_not_a_cycle_when_edges_never_overlap():
    document = sample()
    first = document['assertions'][3]
    first['valid_time']['end'] = '2026-06-01T00:00:00Z'
    reverse = deepcopy(first)
    reverse.update(id='reverse-later', subject_id='level', object_id='work-space')
    reverse['valid_time']['start'] = first['valid_time']['end']
    reverse['valid_time']['end'] = '2027-01-01T00:00:00Z'
    # Remove level's earlier parent when the new edge becomes active.
    document['assertions'][2]['valid_time']['end'] = first['valid_time']['end']
    document['assertions'].append(reverse)
    assert validate(document)['valid']
    reverse['valid_time']['start'] = '2026-05-01T00:00:00Z'
    assert 'hierarchy_cycle' in codes(validate(document))


def test_disputed_evidence_does_not_satisfy_required_role_relationship():
    document = sample()
    document['assertions'][5]['epistemic_status'] = 'disputed'
    report = validate(document)
    assert {'disputed_assertion', 'cardinality_violation'} <= codes(report)
    assert not report['valid']
    assert {d['state'] for d in report['diagnostics']} == {'conflict', 'unsatisfied', 'not_recorded', 'unknown'}


def test_missing_geometry_is_allowed_but_information_records_cannot_bind_geometry():
    document = sample()
    document['frames'] = []
    document['geometries'] = []
    document['geometry_bindings'] = []
    assert validate(document)['valid']
    document = sample()
    document['geometry_bindings'][0]['entity_id'] = 'asset'
    assert 'geometry_binding_type_mismatch' in codes(validate(document))


@pytest.mark.parametrize('raw,code', [
    (b'{"profile":1,"profile":2}', 'duplicate_key'),
    (b' ' * (MAX_INSTANCE_BYTES + 1), 'size_budget'),
    (b'\xff', 'invalid_json'),
    (b'{', 'invalid_json'),
    (b'{"value":NaN}', 'non_finite_number'),
    (b'{"value":1e999}', 'non_finite_number'),
    (b'[' * 40 + b'0' + b']' * 40, 'depth_budget'),
    ('not-bytes', 'invalid_input'),
])
def test_bounded_parser_fails_closed(raw, code):
    report = validate_instances(raw, builtin_catalog())
    assert not report['valid'] and code in codes(report)


def test_rules_are_explicit_and_unsupported_rules_fail_closed():
    document = sample()
    del document['assertions'][5]
    assert validate_instances(canonical_bytes(document), builtin_catalog())['valid']
    assert not validate(document)['valid']
    assert 'unsupported_rule_set' in codes(validate_instances(canonical_bytes(document), builtin_catalog(), rule_set='unknown'))


def test_work_and_diagnostic_budgets_fail_closed(monkeypatch):
    import packages.ontology.kernel.instances as engine
    monkeypatch.setattr(engine, 'MAX_WORK', 10)
    assert 'work_budget' in codes(validate(sample()))
    monkeypatch.setattr(engine, 'MAX_WORK', 250000)
    monkeypatch.setattr(engine, 'MAX_DIAGNOSTICS', 1)
    assert 'diagnostic_budget' in codes(validate(sample()))


def test_new_schema_vocabulary_is_not_silently_ignored(monkeypatch):
    import packages.ontology.kernel.instances as engine
    original = engine.instance_schema()
    original['unevaluatedProperties'] = False
    monkeypatch.setattr(engine, 'instance_schema', lambda: original)
    assert 'unsupported_schema' in codes(validate(sample()))


def test_missing_dependency_and_unlocked_types_are_not_satisfied_by_extra_catalog_modules():
    document = sample()
    document['definition_refs'] = [r for r in document['definition_refs'] if r['module_id'] != 'core']
    assert 'dependency_mismatch' in codes(validate(document))
    document = sample()
    document['entities'][11]['type'] = 'water:pump'
    assert 'unresolved_concept' in codes(validate(document))


def test_timestamps_are_calendar_checked_and_geometry_coordinates_are_finite():
    document = sample()
    document['generated_at'] = '2026-02-30T00:00:00Z'
    assert 'schema_invalid' in codes(validate(document))
    document = sample()
    document['geometries'][0]['shape']['min'] = [float('inf'), 0, 0]
    raw = json.dumps(document).encode('utf-8')
    assert 'non_finite_number' in codes(validate_instances(raw, builtin_catalog()))


def test_geometry_and_source_references_do_not_depend_on_geometric_nearness():
    document = sample()
    document['geometries'][3]['shape']['coordinates'] = [1000000, 1000000, 1000000]
    # This profile validates bindings, not geometric containment or inferred facts.
    assert validate(document)['valid']
    document['geometry_bindings'][0]['geometry_id'] = 'not-in-package'
    assert 'unresolved_geometry' in codes(validate(document))


def test_cli_reports_validation_without_exporting_definitions():
    result = subprocess.run([sys.executable, '-m', 'packages.ontology.kernel', '--instances',
                             str(ROOT / 'manufacturing.json'), '--rules', 'park-baseline'],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['valid']
