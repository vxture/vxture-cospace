"""Cross-park semantic boundaries and consumer upgrade compatibility."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from packages.ontology.kernel import Catalog, builtin_catalog, canonical_bytes
from packages.ontology.resource_directory import ResourceDirectory, ResourceDirectoryError


def definitions():
    return {m['module_id']: m for m in builtin_catalog().export()['modules']}


def test_competency_plan_references_resolve_without_scene_owned_definitions():
    plan = json.loads(Path('examples/ontology/park-competency-questions.json').read_text(encoding='utf-8'))
    modules = definitions()
    assert len(plan['questions']) == 12
    assert len({q['id'] for q in plan['questions']}) == 12
    for question in plan['questions']:
        assert set(question['park_types']) == set(plan['park_types'])
        assert question['required_inputs'] and question['forbidden_inferences']
        assert question['acceptance_batch'] in {'B03', 'B05', 'extension'}
        for field in ('concepts', 'relations'):
            for reference in question[field]:
                module_id, term_id = reference.split(':')
                assert term_id in modules[module_id][field], question['id']
    # Shared definitions remain independent of the three consuming park identities.
    assert all(m['layer'] in {'core', 'domain'} for m in modules.values())
    assert not any('scene_id' in m or 'park_id' in m or 'instances' in m for m in modules.values())


def test_building_space_and_operational_roles_preserve_identity_boundaries():
    modules = definitions()
    concepts = {f'{m}:{key}': term for m, value in modules.items() for key, term in value['concepts'].items()}

    def ancestors(identity):
        result = set()
        while identity:
            result.add(identity)
            identity = concepts[identity].get('parent')
        return result

    assert 'core:physical_object' in ancestors('built_environment:building')
    assert 'core:spatial_region' in ancestors('built_environment:building_region')
    assert 'core:physical_object' not in ancestors('built_environment:building_region')
    for name in ('space_use', 'occupancy_assignment', 'responsibility_assignment'):
        assert 'core:role_assignment' in ancestors('operations:' + name)
        assert 'core:spatial_region' not in ancestors('operations:' + name)
    assert 'core:information_record' in ancestors('operations:asset_record')
    assert 'core:physical_object' not in ancestors('operations:asset_record')
    assert modules['operations']['concepts']['space_use']['properties']['use_label']['required']


def test_responsibility_record_and_occupancy_have_separate_typed_endpoints():
    relations = definitions()['operations']['relations']
    assert relations['occupancy_organization']['source_types'] == ['operations:occupancy_assignment']
    assert relations['occupancy_organization']['target_types'] == ['core:organization']
    assert relations['occupancy_space']['target_types'] == ['core:spatial_region']
    assert relations['responsible_organization']['source_types'] == ['operations:responsibility_assignment']
    assert set(relations['responsibility_target']['target_types']) == {
        'core:physical_object', 'core:spatial_region', 'core:system'}
    assert relations['asset_object']['source_types'] == ['operations:asset_record']
    assert relations['asset_object']['target_types'] == ['core:physical_object']
    assert relations['asset_custodian']['source_types'] != relations['responsible_organization']['source_types']
    assert all(not r['symmetric'] for r in relations.values())


def test_domain_revision_does_not_rewrite_shared_core_or_export_unrelated_modules():
    catalog = builtin_catalog()
    modules = definitions()
    assert sha256(canonical_bytes(modules['core'])).hexdigest() == 'd12aec3d679d5c06779e91faf44b4064dfee2a7cbdee2330b20e253b511f169f'
    upgraded = {'built_environment', 'operations', 'electrical'}
    for identity in sorted(upgraded):
        assert modules[identity]['version'] == '0.2.0'
        exported = catalog.export(identity)
        assert {m['module_id'] for m in exported['modules']} == {'core', identity}
        assert Catalog.from_bytes(canonical_bytes(exported)).export() == exported
    assert all(m['version'] == '0.1.0' for key, m in modules.items()
               if key not in upgraded)


def test_definition_upgrade_invalidates_snapshot_but_preserves_explicit_membership(tmp_path):
    # Emulate a consumer holding a previous version; do not require a history service.
    previous = deepcopy(builtin_catalog().export()['modules'])
    next(m for m in previous if m['module_id'] == 'operations')['version'] = '0.1.0'
    old_store = ResourceDirectory(tmp_path, Catalog(previous).describe())
    old_page = old_store.read('park-a', {})
    old_reference = next(i['reference'] for i in old_page['items'] if i['reference']['module_id'] == 'operations')
    old_store.change('park-a', 'manager', {
        'request_id': 'a' * 32, 'module_id': 'operations', 'expected_revision': 0, 'group_ids': []})
    before_upgrade = old_store.read('park-a', {})
    upgraded = ResourceDirectory(tmp_path, builtin_catalog().describe())
    with pytest.raises(ResourceDirectoryError):
        upgraded.definition(old_reference)
    with pytest.raises(ResourceDirectoryError, match='directory_changed'):
        upgraded.read('park-a', {'snapshot': before_upgrade['snapshot']})
    item = next(i for i in upgraded.read('park-a', {})['items'] if i['reference']['module_id'] == 'operations')
    assert item['reference']['version'] == '0.2.0'
    assert item['revision'] == 1 and item['group_ids'] == []
    assert upgraded.read('park-b', {'group': 'preset-operations'})['total'] == 1
