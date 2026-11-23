"""Accept specialized park claims through authoring, scene linkage and fixed delivery."""
from itertools import count
import json
from pathlib import Path

import pytest

from packages.ontology.kernel import Catalog, builtin_catalog
from packages.service.object_semantic_artifact import MANIFEST, PROFILE, freeze, preflight, verify_publication
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.service.scene_ontology_links import SceneOntologyLinks


EXAMPLES = Path('examples/ontology/parks')
LEGACY = Path('tests/fixtures/ontology-instances')
SCOPE = 'synthetic-park'
STAMP = '2026-11-24T10:00:00Z'


class Delivery:
    def __init__(self, root):
        self.catalog = builtin_catalog()
        self.ids = (f'{n:032x}' for n in count(1))
        self.author = DefinitionWorkbench(root, SCOPE, 'author', True).service
        self.reviewer = DefinitionWorkbench(root, SCOPE, 'reviewer', True).service
        self.links = SceneOntologyLinks(root, SCOPE, 'engineer', None)
        self.references = {'core': self.publish('core', self.catalog.export('core'))}

    def publish(self, module, bundle, base=None):
        revision = int(base is not None)
        self.author.save(SCOPE, 'author', next(self.ids), module_id=module,
                         expected_revision=revision, bundle=bundle, base_reference=base)
        review = self.author.submit(SCOPE, 'author', next(self.ids), module_id=module,
                                    expected_revision=revision + 1)
        self.reviewer.decide(SCOPE, 'reviewer', next(self.ids), review_id=review['review_id'],
                             decision='approved', reason='合成审批，仅校验流程')
        ref = self.author.publish(SCOPE, 'author', next(self.ids), review_id=review['review_id'],
                                  expected_revision=revision + 1)['reference']
        return ref

    def change(self, source, revision, action, **fields):
        identity = {k: source[k] for k in ('space_id', 'candidate_id', 'source_sha256')}
        return self.links.change(source, dict(identity, action=action, expected_revision=revision,
                                             request_id=next(self.ids), **fields))['revision']

    @staticmethod
    def plan(sample, candidate):
        return {
            'space_id': SCOPE, 'candidate_id': candidate, 'source_sha256': 'a' * 64,
            'source_model_sha256': 'b' * 64, 'frame_id': sample['frame_id'], 'unit': 'm', 'axes': None,
            'objects': [{'object_id': o['id'], 'properties': {'name': o['name']}} |
                        ({'anchor_m': o['anchor_m']} if 'anchor_m' in o else {}) for o in sample['objects']],
            'relations': [{'relation_id': r['id'], 'source_id': r['source'], 'target_id': r['target'],
                           'type_id': 'source-assertion', 'note': r.get('evidence_note', '仅空间邻近')}
                          for r in sample['relations']],
        }

    def link(self, source, revision, obj, reference=None):
        module, concept = obj['type'].split(':')
        revision = self.change(source, revision, 'set', object_id=obj['id'], concept_id=concept,
                               reference=reference or self.references[module])
        return self.change(source, revision, 'properties', object_id=obj['id'], valid_time=None,
                           properties={'name': {'value': obj['name']}, **obj.get('properties', {})},
                           evidence_note=obj.get('evidence_note', '合成对象台账'))

    def map(self, source, revision, row, valid_time, *, direction='forward', relation=None):
        module, term = (relation or row['type']).split(':')
        return self.change(source, revision, 'relation_set', relation_id=row['id'], reference=self.references[module],
                           definition_id=term, direction=direction, valid_time=valid_time,
                           evidence_note=row.get('evidence_note', '合成负例资料'))

    def selection(self, source, revision):
        return preflight(self.links, source, {'consumer_revision': revision,
                                               'source_manifest_sha256': source['source_sha256']})


def verify_fixed(root, source, selection, manifest, payload):
    root.mkdir()
    for name, raw in payload.items():
        (root / name).write_bytes(raw)
    record = {'space_id': source['space_id'], 'candidate_id': source['candidate_id'],
              'model_manifest_sha256': source['source_sha256'], 'source_model_sha256': source['source_model_sha256'],
              'files': payload, 'semantic_workspace_scope': manifest['workspace_scope'],
              'semantic_selection': selection,
              'semantic_artifact': {'path': MANIFEST, 'profile': PROFILE, 'artifact_id': manifest['artifact_id']}}
    assert verify_publication(record, root) == manifest


def upgrade_and_verify_previous(root, delivery, sample, module, legacy_filename, legacy_object):
    old = json.loads((LEGACY / legacy_filename).read_bytes())
    previous = Catalog(delivery.catalog.export('core')['modules'] + [old]).export()
    old_ref = delivery.publish(module, previous)
    old_source = delivery.plan(sample, 'build-legacy-' + module.replace('_', '-'))
    old_revision = delivery.link(old_source, 0, legacy_object, reference=old_ref)
    old_fixed, _ = delivery.selection(old_source, old_revision)
    old_manifest, old_files = freeze(delivery.links, old_source, old_fixed, STAMP)

    bundle = delivery.catalog.export(module)
    delivery.references[module] = delivery.publish(module, bundle, base=old_ref)
    assert delivery.references[module]['version'] != old_ref['version']
    assert delivery.author.read_release(SCOPE, 'author', old_ref)['bundle'] == previous
    assert delivery.selection(old_source, old_revision)[0] == old_fixed
    verify_fixed(root / ('old-artifact-' + module), old_source, old_fixed, old_manifest, old_files)
    return bundle


def test_fire_safety_distinguishes_placement_configuration_and_alarm_source(tmp_path):
    sample = json.loads((EXAMPLES / 'logistics-fire-safety-b08b.json').read_bytes())
    delivery = Delivery(tmp_path)
    bundle = upgrade_and_verify_previous(
        tmp_path, delivery, sample, 'fire_safety', 'fire-safety-v0.1.0.json', sample['objects'][2])
    source = delivery.plan(sample, 'build-fire-safety')
    revision = 0
    for obj in sample['objects']:
        revision = delivery.link(source, revision, obj)
    for row in sample['relations'][:3]:
        revision = delivery.map(source, revision, row, sample['valid_time'])
    selected, report = delivery.selection(source, revision)
    assert report['coverage']['unmapped_relations'] == 1
    manifest, payload = freeze(delivery.links, source, selected, STAMP)
    assert manifest['assessment']['professional_review'] == 'not_performed'
    assert Catalog.from_bytes(payload['definitions.json']).export() == bundle
    verify_fixed(tmp_path / 'fire-artifact', source, selected, manifest, payload)
    claims = json.loads(payload['claims.json'])
    assert {(r['definition_id'], r['source_id'], r['target_id'], r['epistemic_status'])
            for r in claims['relation_links']} == {
                ('located_in', 'detector', 'compartment', 'reported'),
                ('assigned_alarm_zone', 'detector', 'alarm-zone', 'reported'),
                ('reported_source_device', 'reported-alarm', 'detector', 'reported')}
    assert {link['concept_id'] for link in claims['links']} == {
        'fire_alarm_device', 'fire_alarm_zone', 'fire_compartment', 'alarm_report'}

    revision = delivery.map(source, revision, sample['relations'][2], sample['valid_time'], direction='reverse')
    with pytest.raises(ValueError, match='semantic_relations_invalid'):
        delivery.selection(source, revision)
    revision = delivery.map(source, revision, sample['relations'][2], sample['valid_time'])
    revision = delivery.map(source, revision, sample['relations'][3], sample['valid_time'],
                            relation='fire_safety:assigned_alarm_zone')
    assert any(issue['code'] == 'endpoint_type_mismatch'
               for issue in delivery.links.read(source)['relation_report']['diagnostics'])
    with pytest.raises(ValueError, match='semantic_relations_invalid'):
        delivery.selection(source, revision)
    assert delivery.selection(source, selected['consumer_revision'])[0] == selected


def test_water_documents_connections_without_direction_or_spatial_inference(tmp_path):
    sample = json.loads((EXAMPLES / 'research-office-water-b08c.json').read_bytes())
    delivery = Delivery(tmp_path)
    bundle = upgrade_and_verify_previous(
        tmp_path, delivery, sample, 'water', 'water-v0.1.0.json', sample['objects'][0])
    source = delivery.plan(sample, 'build-water')
    revision = 0
    for obj in sample['objects']:
        revision = delivery.link(source, revision, obj)
    period = sample['valid_time']
    for row in sample['relations'][:4]:
        revision = delivery.map(source, revision, row, period)
    selected, report = delivery.selection(source, revision)
    assert report['coverage']['unmapped_relations'] == 1
    manifest, payload = freeze(delivery.links, source, selected, STAMP)
    verify_fixed(tmp_path / 'water-artifact', source, selected, manifest, payload)
    assert Catalog.from_bytes(payload['definitions.json']).export() == bundle
    claims = json.loads(payload['claims.json'])
    assert {(r['relation_id'], r['definition_id']) for r in claims['relation_links']} == {
        ('pump-connection-point', 'has_water_port'), ('pipe-connection-point', 'has_water_port'),
        ('physical-connection', 'water_connected_to'), ('system-membership', 'member_of')}
    assert next(r for r in claims['links'] if r['object_id'] == 'pipe')['instance_properties'][
        'design_inner_diameter'] == {'value': 52, 'unit': 'mm', 'quantity': 'length'}

    revision = delivery.map(source, revision, sample['relations'][2], period, direction='reverse')
    assert delivery.selection(source, revision)[1]['mapped_relation_validation'] == 'passed'
    invalid_port = delivery.map(source, revision, sample['relations'][4], period,
                                relation='water:water_connected_to')
    with pytest.raises(ValueError, match='semantic_relations_invalid'):
        delivery.selection(source, invalid_port)
    revision = delivery.change(source, invalid_port, 'relation_remove', relation_id='nearby')
    revision = delivery.change(source, revision, 'properties', object_id='pipe', valid_time=None,
                               evidence_note='合成反例：把设计内径登记成 m',
                               properties={'name': {'value': '给水管段 WP-07'}, 'design_inner_diameter':
                                           {'value': 0.052, 'unit': 'm', 'quantity': 'length'}})
    with pytest.raises(ValueError, match='semantic_attributes_invalid'):
        delivery.selection(source, revision)
    assert delivery.selection(source, selected['consumer_revision'])[0] == selected
