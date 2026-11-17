from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.construction.ifc_review_snapshot import build_review_snapshot, inspect_review_snapshot, ReviewSnapshot
from packages.construction.ifc_structure_review import structure_review
from packages.data.ifc_inspection import digest
from packages.data.ifc_workspace import IfcWorkspace
from packages.service.ifc_review_changes import compare_review_snapshots
from packages.spatial.ifc_annotations import seed
from packages.spatial.scene_identity import canonical
from test_ifc_structure_review import structure_source
from test_ifc_type_proposals import ontology, mapping

SPACE = 'space-' + '1' * 16


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def review_env(structure_source, tmp_path):
    root, doc = structure_source
    # Add a source-declared level so candidate areas can be tested independently.
    doc['products'].append(dict(doc['products'][0], global_id='level', ifc_type='IfcBuildingStorey', name='level'))
    doc['product_count'] = len(doc['products'])
    doc['structure']['entities'].append(dict(entity_id='level', geometry_product_id='level',
                                            ifc_type='IfcBuildingStorey', role='level'))
    (root / 'ifc.json').write_text(json.dumps(doc), encoding='utf-8')
    pin = digest(root / 'ifc.json')
    config = tmp_path / 'bindings.json'
    config.write_text(json.dumps({'profile': 'cospace.scene-ifc-bindings/0.1', 'bindings': [
        {'space_id': SPACE, 'root': str(root), 'catalog_sha256': pin}]}), encoding='utf-8')
    workspace = IfcWorkspace(SimpleNamespace(read=lambda *args: None), None, config)
    review = structure_review(root, expected_catalog_sha256=pin)
    return workspace, pin, review, root, config


def build(env, **kwargs):
    return build_review_snapshot(env[0], SPACE, env[1], **kwargs)


def inspect(result, **kwargs):
    source = json.loads(result['snapshot'])['source']
    return inspect_review_snapshot(result['snapshot'], expected_sha256=sha(result['snapshot']),
                                   design_package=result['design_package'], expected_source=source, **kwargs)


def filled(review):
    sheet = seed(review)
    sheet['evidence'] = [{'id': 'drawing', 'sha256': 'a' * 64}]
    sheet['areas'] = [{'id': name, 'name': name, 'level_id': 'level',
                      'footprint_xy_m': [[x, 0], [x + 2, 0], [x + 2, 2], [x, 2]],
                      'z_range_m': [0, 3], 'evidence_ids': ['drawing']} for name, x in [('area-a', 0), ('area-b', 2)]]
    sheet['connections'][0].update(evidence_ids=['drawing'], endpoints=[
        {'role': 'side_a', 'area_id': 'area-a', 'point_xyz_m': [1, 1, 0]},
        {'role': 'side_b', 'area_id': 'area-b', 'point_xyz_m': [3, 1, 0]}])
    return sheet


def compare(a, b, **kwargs):
    return compare_review_snapshots(a['snapshot'], b['snapshot'], base_sha256=sha(a['snapshot']),
        target_sha256=sha(b['snapshot']), design_package=a['design_package'],
        expected_source=json.loads(a['snapshot'])['source'], **kwargs)


def test_fixed_composition_replays_after_original_files_are_unavailable(review_env):
    worksheet = filled(review_env[2])
    before = deepcopy(worksheet)
    result = build(review_env, worksheet=worksheet)
    assert build(review_env, worksheet=worksheet) == result
    assert worksheet == before
    summary = inspect(result)['summary']
    assert summary['areas'] == 2
    assert summary['complete_annotation_ids'] == ['door']
    assert summary['pending_annotation_ids'] == ['stair']
    assert summary['confirmed_connections'] == []
    for key in ('evidence_content_verified', 'alignment_verified', 'ontology_bound', 'real_release_ready'):
        assert summary[key] is False
    assert str(review_env[3]).encode() not in result['snapshot']
    (review_env[3] / 'source.ifc').unlink()
    assert inspect(result)['summary'] == summary


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(real_release_ready=True),
    lambda d: d.update(alignment_verified=True),
    lambda d: d.update(ontology_bound=True),
    lambda d: d.update(structure_sha256='e' * 64),
    lambda d: d['annotations']['connections'].pop(),
    lambda d: d['annotations']['areas'][0].update(level_id='wall'),
    lambda d: d['annotations']['connections'][0]['endpoints'][0].update(area_id='missing'),
    lambda d: d['annotations']['areas'][0].update(evidence_ids=['missing']),
])
def test_rehashed_but_invalid_snapshot_is_rejected(review_env, mutation):
    result = build(review_env, worksheet=filled(review_env[2]))
    doc = json.loads(result['snapshot'])
    mutation(doc)
    result['snapshot'] = canonical(doc)
    with pytest.raises(ValueError):
        inspect(result)


def test_pins_canonical_json_and_design_package_are_required(review_env):
    result = build(review_env)
    raw, source = result['snapshot'], json.loads(result['snapshot'])['source']
    pin = sha(raw)
    with pytest.raises(ValueError, match='snapshot_digest'):
        inspect_review_snapshot(raw + b' ', expected_sha256=pin, design_package=result['design_package'], expected_source=source)
    result['snapshot'] = b'{"assessment":"unverified",' + raw[1:]
    with pytest.raises(ValueError, match='duplicate_json_key'):
        inspect(result)
    result['snapshot'] = raw + b' '
    with pytest.raises(ValueError, match='canonical_required'):
        inspect(result)
    result['snapshot'] = raw
    result['design_package'] += b'bad'
    with pytest.raises(ValueError, match='byte_digest'):
        inspect(result)


def test_mapping_is_recomputed_from_fixed_ontology_and_source(review_env):
    vocabulary = ontology()
    result = build(review_env, mapping=mapping(vocabulary), ontology_raw=vocabulary)
    assert inspect(result, ontology_raw=vocabulary)['summary']['proposed_types'] == 1
    with pytest.raises(ValueError):
        inspect(result, ontology_raw=vocabulary + b' ')
    doc = json.loads(result['snapshot'])
    doc['type_proposals_sha256'] = 'a' * 64
    result['snapshot'] = canonical(doc)
    with pytest.raises(ValueError, match='proposals_changed'):
        inspect(result, ontology_raw=vocabulary)


def test_no_change_and_annotation_impact_remain_separate_from_geometry_and_observations(review_env):
    base = build(review_env)
    same = compare(base, base)
    assert same['review_required'] is False
    assert same['affected_source_entity_ids'] == []
    target = build(review_env, worksheet=filled(review_env[2]))
    change = compare(base, target)
    assert change['sections']['areas']['added'] == ['area-a', 'area-b']
    assert change['affected_source_entity_ids'] == ['door']
    assert change['review_components'] == ['spatial_regions', 'structural_connections', 'evidence_review']
    assert change['design_geometry_changed'] is False
    assert change['observation_changes_included'] is False
    assert change['real_release_ready'] is False


def test_evidence_change_propagates_to_areas_and_connectors(review_env):
    sheet = filled(review_env[2])
    base = build(review_env, worksheet=sheet)
    sheet['evidence'][0]['sha256'] = 'b' * 64
    target = build(review_env, worksheet=sheet)
    change = compare(base, target)
    assert change['sections']['areas']['revised'] == []
    assert change['sections']['connections']['revised'] == []
    assert change['sections']['evidence']['revised'] == ['drawing']
    assert change['affected_area_ids'] == ['area-a', 'area-b']
    assert change['affected_source_entity_ids'] == ['door']


def test_semantic_changes_do_not_rebuild_geometry_or_connections(review_env):
    vocabulary = ontology()
    base = build(review_env, mapping=mapping(vocabulary), ontology_raw=vocabulary)
    target = build(review_env, mapping=mapping(vocabulary, target='wall'), ontology_raw=vocabulary)
    change = compare(base, target, base_ontology=vocabulary, target_ontology=vocabulary)
    assert change['sections']['types']['revised'] == ['door']
    assert change['review_components'] == ['semantic_types']
    assert change['design_geometry_changed'] is False


def test_ontology_revision_and_removed_mapping_require_semantic_review(review_env):
    vocabulary = ontology()
    base = build(review_env, mapping=mapping(vocabulary), ontology_raw=vocabulary)
    value = json.loads(vocabulary)
    value['version'] = '1.0.1'
    revised = canonical(value)
    target = build(review_env, mapping=mapping(revised), ontology_raw=revised)
    change = compare(base, target, base_ontology=vocabulary, target_ontology=revised)
    assert change['ontology_context_changed'] is True
    assert change['sections']['types']['revised'] == []
    assert change['affected_source_entity_ids'] == ['door']
    assert change['review_components'] == ['semantic_types']
    removed = compare(base, build(review_env), base_ontology=vocabulary)
    assert removed['sections']['types']['removed'] == ['door']


def test_other_source_or_stale_worksheet_cannot_be_combined(review_env):
    worksheet = seed(review_env[2])
    worksheet['source_review_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='annotation_source_binding'):
        build(review_env, worksheet=worksheet)
    result = build(review_env)
    raw = result['snapshot']
    pin = sha(raw)
    source = json.loads(raw)['source'] | {'space_id': 'space-' + '2' * 16}
    with pytest.raises(ValueError, match='snapshot_source_binding'):
        inspect_review_snapshot(raw, expected_sha256=pin, design_package=result['design_package'], expected_source=source)


def test_source_change_during_composition_is_rejected(review_env, monkeypatch):
    from packages.construction import ifc_review_snapshot as module
    original = module.export_design_package
    calls = []

    def changing(*args):
        raw = original(*args)
        calls.append(True)
        return raw if len(calls) == 1 else raw + b'changed'

    monkeypatch.setattr(module, 'export_design_package', changing)
    with pytest.raises(ValueError, match='snapshot_source_changed'):
        build(review_env)


def test_unused_mapping_rule_still_requires_mapping_review(review_env):
    vocabulary = ontology()
    first = mapping(vocabulary)
    second = deepcopy(first)
    second['rules'].append({'ifc_type': 'IfcWindow', 'target_type_id': 'wall'})
    base = build(review_env, mapping=first, ontology_raw=vocabulary)
    target = build(review_env, mapping=second, ontology_raw=vocabulary)
    changes = compare(base, target, base_ontology=vocabulary, target_ontology=vocabulary)
    assert changes['sections']['types']['revised'] == []
    assert changes['review_components'] == ['semantic_mapping_review']


def test_compare_cli_refuses_overwrite(review_env, tmp_path, monkeypatch):
    from experiments.scripts.ifc_review_changes import main
    result = build(review_env)
    raw = result['snapshot']
    source = json.loads(raw)['source']
    for name, data in [('snapshot.json', raw), ('design.bin', result['design_package']), ('source.json', canonical(source))]:
        (tmp_path / name).write_bytes(data)
    monkeypatch.setattr('sys.argv', ['ifc_review_changes', '--base', str(tmp_path / 'snapshot.json'),
        '--target', str(tmp_path / 'snapshot.json'), '--design-package', str(tmp_path / 'design.bin'),
        '--source', str(tmp_path / 'source.json'), '--base-sha256', sha(raw), '--target-sha256', sha(raw),
        '--output', str(tmp_path / 'changes.json')])
    main()
    assert json.loads((tmp_path / 'changes.json').read_bytes())['review_required'] is False
    with pytest.raises(FileExistsError):
        main()


def test_export_cli_creates_new_directory_only(review_env, tmp_path, monkeypatch):
    from experiments.scripts.ifc_review_snapshot import main
    output = tmp_path / 'export'
    monkeypatch.setattr('sys.argv', ['ifc_review_snapshot', '--bindings', str(review_env[4]), '--space', SPACE,
        '--catalog-sha256', review_env[1], '--output-dir', str(output)])
    main()
    receipt = json.loads((output / 'receipt.json').read_bytes())
    assert len(receipt['members']) == 2
    with pytest.raises(FileExistsError):
        main()


def test_schema_keeps_snapshot_a_candidate():
    schema = json.loads(Path('contracts/schemas/ifc-review-snapshot-v0.1.schema.json').read_bytes())
    assert {k: v for k, v in schema.items() if k not in ('$schema', '$id')} == ReviewSnapshot.model_json_schema()
