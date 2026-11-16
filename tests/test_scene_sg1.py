"""SG1 proposals and subsets preserve facts without upgrading their authority."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from experiments.scripts.scene_graph_sample import sample
from experiments.scripts.scene_sg1_samples import identity_samples, legacy_sample, merged_sample
from packages.spatial.scene_identity import (IdentityChanges, canonical, content_digest,
                                             snapshot_ref, validate_identity_changes)
from packages.spatial.scene_legacy import AnchorMapping, project_legacy_anchors
from packages.views.agent.scene_subset import (DEPENDENCIES, SubsetManifest, build_scene_subset,
                                               validate_scene_subset, verify_subset_against_source)


def refresh_bindings(draft, base, target):
    draft.update(base=snapshot_ref(base), target=snapshot_ref(target))


def replace_legacy(raw, mapping, change):
    document = json.loads(raw)
    change(document)
    raw = json.dumps(document, allow_nan=True).encode()
    mapping['source_document_sha256'] = hashlib.sha256(raw).hexdigest()
    return raw


def resign_component(package, role):
    component = next(c for c in package['manifest']['components'] if c['role'] == role)
    raw = canonical(package['payloads'][role])
    component.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


@pytest.mark.parametrize('kind', ['split', 'merge', 'unresolved'])
def test_identity_alternatives_are_unverified_proposals(kind):
    base, target, drafts = identity_samples()
    before, after = (target, merged_sample(base)) if kind == 'merge' else (base, target)
    originals = deepcopy((before, after, drafts[kind]))
    report = validate_identity_changes(drafts[kind], before, after)
    assert report['metadata_valid']
    assert not report['identity_verified']
    assert not report['mutation_supported']
    assert not report['real_release_ready']
    assert (before, after, drafts[kind]) == originals
    if kind == 'unresolved':
        assert report['unresolved_event_ids'] == ['proposal-unresolved']
    assert not report['added_ids']
    assert not report['removed_ids']


@pytest.mark.parametrize('field', ['base', 'target'])
def test_changes_pinned_to_exact_content(field):
    base, target, drafts = identity_samples()
    drafts['split'][field]['sha256'] = '0'*64
    with pytest.raises(ValueError, match='identity_snapshot_binding'):
        validate_identity_changes(drafts['split'], base, target)


@pytest.mark.parametrize('change,error', [
    (lambda d: d['events'][0].update(before_ids=['missing']), 'identity_endpoint_missing'),
    (lambda d: d['events'][0].update(before_ids=['room-l1', 'room-l1']), 'duplicate_identity_reference'),
    (lambda d: d['events'][0].update(after_ids=['room-l1-a']), 'split_cardinality'),
    (lambda d: d['events'][0].update(kind='merge'), 'merge_cardinality'),
    (lambda d: d['events'][0].update(after_ids=['cabinet', 'room-l1-a']), 'identity_kind_mismatch'),
    (lambda d: d['events'][0].update(assessment='verified'), 'identity_structure'),
    (lambda d: d.update(data_kind='real'), 'identity_structure'),
    (lambda d: d['events'].append(deepcopy(d['events'][0])), 'duplicate_identity_event'),
])
def test_bad_identity_events(change, error):
    base, target, drafts = identity_samples()
    change(drafts['split'])
    with pytest.raises(ValueError, match=error):
        validate_identity_changes(drafts['split'], base, target)


def test_overlapping_and_continuing_ids_cannot_be_split():
    base, target, drafts = identity_samples()
    draft = drafts['split']
    other = deepcopy(draft['events'][0])
    other['id'] = 'other'
    draft['events'].append(other)
    with pytest.raises(ValueError, match='overlapping_identity_events'):
        validate_identity_changes(draft, base, target)
    draft['events'].pop()
    # cabinet continues in both snapshots, so it cannot become a new split endpoint.
    draft['events'][0].update(before_ids=['cabinet'], after_ids=['room-l1-a', 'room-l1-b'])
    with pytest.raises(ValueError, match='identity_kind_mismatch'):
        validate_identity_changes(draft, base, target)
    draft['events'][0].update(before_ids=['room-l1'], after_ids=['corridor-l1', 'room-l1-a'])
    with pytest.raises(ValueError, match='identity_endpoint_still_continues'):
        validate_identity_changes(draft, base, target)


def test_revisions_cover_geometry_but_not_observation_updates():
    base, target, drafts = identity_samples()
    next(g for g in target['geometry'] if g['entity_id'] == 'cabinet')['value']['bounds'][1][0] += .1
    refresh_bindings(drafts['split'], base, target)
    with pytest.raises(ValueError, match='changed_entity_requires_revision'):
        validate_identity_changes(drafts['split'], base, target)
    next(e for e in target['entities'] if e['id'] == 'cabinet')['revision'] = 2
    target['observations'][0]['value'] = 'open'
    refresh_bindings(drafts['split'], base, target)
    assert validate_identity_changes(drafts['split'], base, target)['metadata_valid']


def test_revision_regression_and_context_migration_rejected():
    base, target, drafts = identity_samples()
    next(e for e in base['entities'] if e['id'] == 'cabinet')['revision'] = 2
    refresh_bindings(drafts['split'], base, target)
    with pytest.raises(ValueError, match='identity_revision_regression'):
        validate_identity_changes(drafts['split'], base, target)
    next(e for e in target['entities'] if e['id'] == 'cabinet')['revision'] = 2
    target['ontology']['id'] = 'new-ontology'
    refresh_bindings(drafts['split'], base, target)
    with pytest.raises(ValueError, match='identity_context_migration_unsupported'):
        validate_identity_changes(drafts['split'], base, target)


def test_unclassified_addition_and_removal_are_explicit():
    base, target, drafts = identity_samples()
    drafts['split']['events'] = []
    report = validate_identity_changes(drafts['split'], base, target)
    assert report['removed_ids'] == ['room-l1']
    assert report['added_ids'] == ['room-l1-a', 'room-l1-b']


def test_legacy_projection_preserves_identity_and_only_point_geometry():
    raw, mapping = legacy_sample()
    before = deepcopy(mapping)
    projection = project_legacy_anchors(raw, mapping)
    assert mapping == before
    assert projection['data_kind'] == 'source_unverified'
    assert projection['geometry_role'] == 'reference_point'
    assert projection['anchors'][0]['entity_id'] == 'cabinet'
    assert projection['anchors'][0]['position'] == [1., 6., 0.]
    assert not projection['evidence_verified']
    assert not projection['real_release_ready']
    assert 'bounds' not in projection['anchors'][0]
    assert 'connections' not in projection


@pytest.mark.parametrize('change,error', [
    (lambda d: d['objects'][0]['anchor_m'].__setitem__(0, float('nan')), 'legacy_anchor_structure'),
    (lambda d: d['objects'][0]['anchor_m'].__setitem__(0, True), 'legacy_document_structure'),
    (lambda d: d['objects'][0]['anchor_m'].__setitem__(0, 1e20), 'legacy_anchor_structure'),
    (lambda d: d['objects'][0]['evidence'].update(sha256='d'*64), 'legacy_point_source_binding'),
    (lambda d: d.update(frame_id='other'), 'legacy_source_binding'),
    (lambda d: d.update(source_model_sha256='d'*64), 'legacy_source_binding'),
    (lambda d: d['objects'][0].update(type_id='other'), 'legacy_type_mapping_missing'),
    (lambda d: d['objects'].append(deepcopy(d['objects'][0])), 'duplicate_legacy_object'),
    (lambda d: d['objects'][0].update(confirmation='verified'), 'legacy_document_structure'),
])
def test_legacy_bad_inputs(change, error):
    raw, mapping = legacy_sample()
    raw = replace_legacy(raw, mapping, change)
    with pytest.raises(ValueError, match=error):
        project_legacy_anchors(raw, mapping)


def test_legacy_digest_mapping_and_duplicate_keys():
    raw, mapping = legacy_sample()
    with pytest.raises(ValueError, match='legacy_document_digest'):
        project_legacy_anchors(raw+b' ', mapping)
    mapping['mappings'].append(deepcopy(mapping['mappings'][0]))
    with pytest.raises(ValueError, match='duplicate_legacy_type_mapping'):
        project_legacy_anchors(raw, mapping)
    raw = b'{"profile":1,"profile":2}'
    mapping['source_document_sha256'] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match='duplicate_legacy_json_key'):
        project_legacy_anchors(raw, mapping)


def test_subset_is_local_with_full_dependencies_and_closed_references():
    source = sample()
    before = deepcopy(source)
    package = build_scene_subset(source, ['corridor-l1'])
    assert source == before
    manifest = package['manifest']
    assert manifest['requested_ids'] == ['corridor-l1']
    assert set(manifest['dependency_ids']) == {'door-l1', 'room-l1', 'stair', 'corridor-l2'}
    assert 'building' not in {e['id'] for e in package['payloads']['entities']['entities']}
    assert len(package['payloads']['structure']['connections']) == 2
    # corridor-l2 is a dependency, not a recursively expanded request; door-l2 is omitted.
    assert 'door-l2' not in manifest['dependency_ids']
    report = validate_scene_subset(package, snapshot_ref(source))
    assert not report['source_content_verified']
    assert not report['selection_boundary_complete']
    verified = verify_subset_against_source(package, source)
    assert verified['source_content_verified']
    assert verified['selection_boundary_complete']
    assert not verified['full_scene_coverage']
    assert not verified['robot_ready']


def test_isolated_asset_package_does_not_invent_connections():
    source = sample()
    package = build_scene_subset(source, ['cabinet'])
    assert not package['manifest']['dependency_ids']
    assert package['payloads']['structure'] == {'relations': [], 'connections': []}
    assert verify_subset_against_source(package, source)['source_content_verified']


@pytest.mark.parametrize('ids', [[], ['missing'], ['cabinet', 'cabinet'], [True], 'cabinet', ['cabinet']*129])
def test_subset_invalid_selections(ids):
    with pytest.raises(ValueError, match='subset_'):
        build_scene_subset(sample(), ids)


@pytest.mark.parametrize('role', ['entities', 'geometry', 'structure', 'observations'])
def test_subset_component_dependencies_are_mandatory(role):
    source = sample()
    package = build_scene_subset(source, ['corridor-l1'])
    component = next(c for c in package['manifest']['components'] if c['role'] == role)
    component['depends_on'] = ['geometry'] if role == 'entities' else []
    assert component['depends_on'] != DEPENDENCIES[role]
    with pytest.raises(ValueError, match='subset_component_dependencies'):
        validate_scene_subset(package, snapshot_ref(source))


def test_subset_integrity_and_external_source_binding():
    source = sample()
    package = build_scene_subset(source, ['cabinet'])
    package['payloads']['entities']['entities'][0]['name'] = 'tampered'
    with pytest.raises(ValueError, match='subset_component_integrity'):
        validate_scene_subset(package, snapshot_ref(source))
    resign_component(package, 'entities')
    # A newly self-consistent hash still does not prove the source content was preserved.
    assert not validate_scene_subset(package, snapshot_ref(source))['source_content_verified']
    with pytest.raises(ValueError, match='subset_differs_from_source_selection'):
        verify_subset_against_source(package, source)
    expected = snapshot_ref(source) | {'sha256': '0'*64}
    with pytest.raises(ValueError, match='subset_source_binding'):
        validate_scene_subset(package, expected)


def test_resigned_subset_cannot_hide_broken_connections():
    source = sample()
    package = build_scene_subset(source, ['corridor-l1'])
    package['payloads']['geometry'].pop()
    resign_component(package, 'geometry')
    with pytest.raises(ValueError, match='entity_geometry_binding'):
        validate_scene_subset(package, snapshot_ref(source))


def test_subset_component_role_and_catalog_checks():
    source = sample()
    package = build_scene_subset(source, ['cabinet'])
    package['manifest']['dependency_ids'] = ['cabinet']
    with pytest.raises(ValueError, match='subset_dependency_overlap'):
        validate_scene_subset(package, snapshot_ref(source))
    package['manifest']['dependency_ids'] = []
    package['manifest']['components'][-1] = deepcopy(package['manifest']['components'][0])
    with pytest.raises(ValueError, match='subset_component_roles'):
        validate_scene_subset(package, snapshot_ref(source))


@pytest.mark.parametrize('name,model', [
    ('synthetic-identity-changes-v0.1', IdentityChanges),
    ('legacy-anchor-mapping-v0.1', AnchorMapping),
    ('synthetic-scene-subset-v0.1', SubsetManifest),
])
def test_checked_in_schema_matches_binding(name, model):
    schema = json.loads(Path('contracts/schemas', name+'.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    assert {k: v for k, v in schema.items() if k not in {'$schema', '$id'}} == model.model_json_schema()


def test_checked_in_examples_reproduce_and_validate():
    folder = Path('examples/scene-graph/sg1')
    base, target, drafts = identity_samples()
    assert json.loads((folder/'target.synthetic.json').read_bytes()) == target
    for kind, document in drafts.items():
        assert json.loads((folder/(kind+'.synthetic.json')).read_bytes()) == document
    raw, mapping = legacy_sample()
    assert (folder/'legacy-objects.synthetic.json').read_bytes() == raw
    assert json.loads((folder/'legacy-mapping.synthetic.json').read_bytes()) == mapping
    assert json.loads((folder/'legacy-projection.synthetic.json').read_bytes()) == project_legacy_anchors(raw, mapping)
    assert json.loads((folder/'merged.synthetic.json').read_bytes()) == merged_sample(base)
    assert json.loads((folder/'corridor-subset.synthetic.json').read_bytes()) == build_scene_subset(base, ['corridor-l1'])
