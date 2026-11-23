"""B08a consumer acceptance through real authoring and fixed delivery services."""
from itertools import count
import json
from pathlib import Path

import pytest

from packages.ontology.kernel import Catalog, builtin_catalog
from packages.service.object_semantic_artifact import MANIFEST, PROFILE, freeze, preflight, verify_publication
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.service.scene_ontology_links import SceneOntologyLinks


FIXTURE = Path('examples/ontology/parks/manufacturing-electrical-b08a.json')
LEGACY = Path('tests/fixtures/ontology-instances/electrical-v0.1.0.json')
SCOPE = 'fixture-park'


def test_electrical_review_association_delivery_and_historical_closure(tmp_path):
    sample = json.loads(FIXTURE.read_bytes())
    catalog = builtin_catalog()
    editor = DefinitionWorkbench(tmp_path, SCOPE, 'editor', True)
    reviewer = DefinitionWorkbench(tmp_path, SCOPE, 'reviewer', True)
    ids = (f'{n:032x}' for n in count(1))

    def publish(module, bundle, revision=0, base=None):
        editor.service.save(SCOPE, 'editor', next(ids), module_id=module,
                            expected_revision=revision, bundle=bundle, base_reference=base)
        review = editor.service.submit(SCOPE, 'editor', next(ids), module_id=module,
                                       expected_revision=revision + 1)
        reviewer.service.decide(SCOPE, 'reviewer', next(ids), review_id=review['review_id'],
                                decision='approved', reason='合成测试审批，仅校验流程')
        return editor.service.publish(SCOPE, 'editor', next(ids), review_id=review['review_id'],
                                      expected_revision=revision + 1)['reference']

    core = catalog.export('core')
    old_module = json.loads(LEGACY.read_bytes())
    old_bundle = Catalog(core['modules'] + [old_module]).export()
    publish('core', core)
    old_ref = publish('electrical', old_bundle)
    assert old_ref['version'] == '0.1.0'

    def source(candidate):
        return {'space_id': 'synthetic-manufacturing', 'candidate_id': candidate,
                'source_sha256': 'a' * 64, 'source_model_sha256': 'b' * 64,
                'frame_id': sample['frame_id'], 'unit': 'm', 'axes': None,
                'objects': [
                    {'object_id': obj['id'], 'properties': {'name': obj['name']}} |
                    ({'anchor_m': obj['anchor_m']} if 'anchor_m' in obj else {})
                    for obj in sample['objects']],
                'relations': [
                    {'relation_id': rel['id'], 'source_id': rel['source'], 'target_id': rel['target'],
                     'type_id': 'source-assertion', 'note': rel.get('evidence_note', '仅空间邻近')}
                    for rel in sample['relations']]}

    service = SceneOntologyLinks(tmp_path, SCOPE, 'engineer', None)
    old_source, new_source = source('build-legacy-electrical'), source('build-b08a-electrical')

    def change(src, revision, action, **fields):
        identity = {k: src[k] for k in ('space_id', 'candidate_id', 'source_sha256')}
        return service.change(src, dict(identity, action=action, expected_revision=revision,
                                        request_id=next(ids), **fields))['revision']

    def link(src, revision, definition_ref, obj):
        revision = change(src, revision, 'set', object_id=obj['id'], reference=definition_ref,
                          concept_id=obj['type'])
        props = {'name': {'value': obj['name']}, **obj['properties']}
        if definition_ref == old_ref:
            del props['rated_current']
        return change(src, revision, 'properties', object_id=obj['id'], properties=props,
                      valid_time=None, evidence_note='合成设备铭牌 DEMO-LABEL-R01')

    def selection(src, revision):
        return {'consumer_revision': revision, 'source_manifest_sha256': src['source_sha256']}

    stamp = '2026-11-24T10:00:00Z'
    cabinet = sample['objects'][1]
    old_selection, _ = preflight(service, old_source, selection(old_source, link(old_source, 0, old_ref, cabinet)))
    _, old_files = freeze(service, old_source, old_selection, stamp)

    bundle = catalog.export('electrical')
    new_ref = publish('electrical', bundle, revision=1, base=old_ref)
    assert new_ref['version'] == '0.2.0'
    assert editor.service.read_release(SCOPE, 'editor', old_ref)['bundle'] == old_bundle
    _, old_after = freeze(service, old_source, old_selection, stamp)
    assert old_after['definitions.json'] == old_files['definitions.json']
    assert json.loads(old_after['claims.json'])['links'][0]['reference'] == old_ref
    new_module = next(m for m in bundle['modules'] if m['module_id'] == 'electrical')
    assert new_module['relations']['supplies'] == old_module['relations']['supplies']

    revision = 0
    for obj in sample['objects']:
        if 'type' in obj:
            revision = link(new_source, revision, new_ref, obj)

    def map_relation(rel, *, direction='forward'):
        nonlocal revision
        revision = change(new_source, revision, 'relation_set', relation_id=rel['id'],
                          reference=new_ref, definition_id=rel['type'], direction=direction,
                          valid_time=sample['valid_time'], evidence_note=rel['evidence_note'])

    for rel in sample['relations']:
        if 'type' in rel:
            map_relation(rel)
    selection_fixed, report = preflight(service, new_source, selection(new_source, revision))
    assert report['coverage']['unmapped_relations'] == 1
    assert report['coverage']['unlinked_objects'] == 1
    manifest, payload = freeze(service, new_source, selection_fixed, stamp)
    assert manifest['assessment']['mapped_relation_validation'] == 'passed'
    assert manifest['assessment']['professional_review'] == 'not_performed'
    fixed_root = tmp_path / 'fixed-artifact'
    fixed_root.mkdir()
    for name, raw in payload.items():
        (fixed_root / name).write_bytes(raw)
    record = {'space_id': new_source['space_id'], 'candidate_id': new_source['candidate_id'],
              'model_manifest_sha256': new_source['source_sha256'],
              'source_model_sha256': new_source['source_model_sha256'], 'files': payload,
              'semantic_workspace_scope': manifest['workspace_scope'], 'semantic_selection': selection_fixed,
              'semantic_artifact': {'path': MANIFEST, 'profile': PROFILE, 'artifact_id': manifest['artifact_id']}}
    assert verify_publication(record, fixed_root) == manifest
    assert Catalog.from_bytes(payload['definitions.json']).export() == bundle
    claims = json.loads(payload['claims.json'])
    assert {(r['source_id'], r['target_id']) for r in claims['relation_links']
            if r['definition_id'] == 'documented_feed'} == {('transformer', 'cabinet'), ('cabinet', 'load')}

    # The same physical connection is valid in either direction, but a load
    # cannot become a declared feeding device by reversing its source row.
    map_relation(sample['relations'][4], direction='reverse')
    assert service.read(new_source)['relation_report']['valid']
    map_relation(sample['relations'][1], direction='reverse')
    assert any(i['code'] == 'endpoint_type_mismatch' for i in service.read(new_source)['relation_report']['diagnostics'])
    with pytest.raises(ValueError, match='semantic_relations_invalid'):
        preflight(service, new_source, selection(new_source, revision))
    map_relation(sample['relations'][1])
    change(new_source, revision, 'properties', object_id='cabinet', valid_time=None,
           evidence_note='合成反例：错误标成 kV',
           properties={'name': {'value': cabinet['name']}, 'rated_voltage':
                       {'value': 0.4, 'unit': 'kV', 'quantity': 'electric_potential'}})
    with pytest.raises(ValueError, match='semantic_attributes_invalid'):
        preflight(service, new_source, selection(new_source, revision + 1))
    assert preflight(service, new_source, selection(new_source, selection_fixed['consumer_revision']))[0] == selection_fixed
    assert verify_publication(record, fixed_root) == manifest
