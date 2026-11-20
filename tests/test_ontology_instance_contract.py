"""B02 contract and fixture QA, not the B03 production semantic validator."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from packages.ontology.kernel import (
    Catalog, builtin_catalog, canonical_bytes, instance_schema, park_baseline_rules,
)

PARKS = Path('examples/ontology/parks')
MATRIX = json.loads(Path('tests/fixtures/ontology-instances/negative-matrix.json').read_text(encoding='utf-8'))
FORMATS = FormatChecker()


@FORMATS.checks('date-time', raises=ValueError)
def valid_datetime(value):
    # jsonschema's RFC3339 checker is an optional dependency. Never let a missing
    # optional checker silently accept invalid calendar dates in contract QA.
    if isinstance(value, str):
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    return True


def load(kind):
    return json.loads((PARKS / f'{kind}.json').read_text(encoding='utf-8'))


def patched(case):
    value = load(case['base'])
    for patch in case['patches']:
        keys = patch['path'].strip('/').split('/')
        target = value
        for key in keys[:-1]:
            target = target[int(key)] if isinstance(target, list) else target[key]
        key = int(keys[-1]) if isinstance(target, list) else keys[-1]
        if patch['op'] == 'remove':
            del target[key]
        else:
            target[key] = deepcopy(patch['value'])
    return value


def test_schema_and_candidate_rules_are_detached_portable_resources():
    schema = instance_schema()
    Draft202012Validator.check_schema(schema)
    schema['properties'].clear()
    assert 'namespace' in instance_schema()['properties']
    rules = park_baseline_rules()
    rules['cardinalities'].clear()
    assert len(park_baseline_rules()['cardinalities']) == 9
    modules = {m['module_id']: m for m in builtin_catalog().export()['modules']}
    for rule in park_baseline_rules()['cardinalities']:
        module, key = rule['concept'].split(':')
        assert key in modules[module]['concepts']
        module, key = rule['relation'].split(':')
        assert key in modules[module]['relations']


@pytest.mark.parametrize('kind', ['research-office', 'manufacturing', 'logistics'])
def test_positive_park_package_schema_and_reference_integrity(kind):
    document = load(kind)
    Draft202012Validator(instance_schema(), format_checker=FORMATS).validate(document)
    assert document['synthetic'] and all(s['synthetic'] for s in document['sources'])
    modules = {m['module_id']: m for m in builtin_catalog().export()['modules']}
    locked = {ref['module_id']: ref for ref in document['definition_refs']}
    for identity, ref in locked.items():
        assert ref['version'] == modules[identity]['version']
        assert ref['sha256'] == sha256(canonical_bytes(modules[identity])).hexdigest()
        assert all(dependency == locked[dependency['module_id']] for dependency in modules[identity]['requires'])
    Catalog([modules[identity] for identity in locked])
    sources = {s['id'] for s in document['sources']}
    evidence = {e['id'] for e in document['evidence']}
    entities = {e['id']: e for e in document['entities']}
    for collection in ('sources', 'evidence', 'entities', 'assertions', 'frames', 'geometries', 'coverage'):
        assert len({e['id'] for e in document[collection]}) == len(document[collection])
    for entity in entities.values():
        module, key = entity['type'].split(':')
        assert module in locked and key in modules[module]['concepts']
        assert all(b['source_id'] in sources for b in entity['source_bindings'])
        assert set(entity['evidence_ids']) <= evidence
        for prop in entity['properties'].values():
            assert prop['source_id'] in sources and set(prop['evidence_ids']) <= evidence
    for assertion in document['assertions']:
        module, key = assertion['relation'].split(':')
        assert module in locked and key in modules[module]['relations']
        assert assertion['subject_id'] in entities and assertion['object_id'] in entities
        assert assertion['source_id'] in sources and set(assertion['evidence_ids']) <= evidence
    for rule in park_baseline_rules()['cardinalities']:
        for entity in entities.values():
            if entity['type'] == rule['concept']:
                edges = [a for a in document['assertions'] if a['subject_id'] == entity['id'] and a['relation'] == rule['relation']]
                assert len(edges) >= rule['minimum']
                assert rule['maximum'] is None or len(edges) <= rule['maximum']
                if 'valid_time' in entity:
                    assert all(a['valid_time'] == entity['valid_time'] for a in edges)
    frames = {f['id'] for f in document['frames']}
    geometries = {g['id'] for g in document['geometries']}
    assert all(g['frame_id'] in frames for g in document['geometries'])
    assert all(b['entity_id'] in entities and b['geometry_id'] in geometries for b in document['geometry_bindings'])


def test_three_parks_reuse_types_but_never_merge_local_ids_across_namespaces():
    parks = [load(kind) for kind in ('research-office', 'manufacturing', 'logistics')]
    assert len({p['namespace'] for p in parks}) == 3
    shared = set.intersection(*[{e['type'] for e in p['entities']} for p in parks])
    assert {'built_environment:building', 'operations:occupancy_assignment', 'electrical:distribution_cabinet'} <= shared
    assert len({(p['namespace'], e['id']) for p in parks for e in p['entities']}) == sum(len(p['entities']) for p in parks)
    assert all(p['coverage'][0]['status'] == 'partial' for p in parks)


@pytest.mark.parametrize('case', MATRIX['cases'], ids=lambda case: case['id'])
def test_negative_matrix_distinguishes_structural_rejection_from_future_semantic_rules(case):
    errors = list(Draft202012Validator(instance_schema(), format_checker=FORMATS).iter_errors(patched(case)))
    if case['stage'] == 'schema':
        assert errors
    else:
        # Semantic-invalid inputs deliberately pass structure validation.
        # B03 must execute the expected code/path; do not count these as rejected yet.
        assert errors == []
    assert case['expected']['path'].startswith('/')


def test_examples_are_reproducible_without_silent_repinning():
    result = subprocess.run([sys.executable, 'scripts/ontology/build_park_examples.py'],
                            capture_output=True, text=True, check=True)
    assert '3 synthetic park fixtures match' in result.stdout
