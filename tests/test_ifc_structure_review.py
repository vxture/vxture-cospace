import json

import pytest

from experiments.scripts.ifc_structure_review import structure_review
from packages.data.ifc_inspection import digest
from test_ifc_inspection import assets_at


@pytest.fixture
def structure_source(tmp_path):
    _, doc, root = assets_at(tmp_path, 'space-' + '1' * 16)
    extra = [('door', 'IfcDoor'), ('opening', 'IfcOpeningElement'),
             ('stair', 'IfcStair'), ('flight', 'IfcStairFlight')]
    for identity, kind in extra:
        doc['products'].append(dict(doc['products'][0], global_id=identity, ifc_type=kind, name=identity))
    doc['product_count'] = len(doc['products'])
    roles = ['building', 'wall', 'door', 'opening', 'stair', 'stair_flight']
    doc['structure'] = dict(profile='cospace.ifc-structure-candidate/0.1', assessment='unverified',
        data_kind='ifc_design_candidate',
        entities=[dict(entity_id=p['global_id'], geometry_product_id=p['global_id'],
                       ifc_type=p['ifc_type'], role=role) for p, role in zip(doc['products'], roles)],
        relations=[dict(ifc_relation_id=f'rel-{i}', kind=kind, source_id=a, target_id=b)
                   for i, (kind, a, b) in enumerate([
                       ('fills', 'door', 'opening'), ('opening_in', 'opening', 'wall'),
                       ('aggregates', 'stair', 'flight')])])
    (root / 'ifc.json').write_text(json.dumps(doc), encoding='utf-8')
    return root, doc


def run(env):
    root, _ = env
    return structure_review(root, expected_catalog_sha256=digest(root / 'ifc.json'))


def test_explicit_paths_are_preserved_without_connections(structure_source):
    report = run(structure_source)
    assert len(report['tasks']) == 2
    door, stair = report['tasks']
    assert [r['kind'] for r in door['source_relations']] == ['fills', 'opening_in']
    assert {g['global_id'] for g in door['related_geometry']} == {'opening', 'wall'}
    assert door['review']['space_endpoints'] == []
    assert stair['related_geometry'][0]['global_id'] == 'flight'
    assert 'space' in report['missing_declared_roles']
    assert report['confirmed_connections'] == []
    assert report['alignment_verified'] is report['real_release_ready'] is False
    assert run(structure_source) == report


def test_mesh_and_source_are_rechecked(structure_source):
    root, _ = structure_source
    (root / 'e00001.npz').write_bytes(b'changed')
    with pytest.raises(ValueError, match='ifc_mesh_changed'):
        run(structure_source)


def test_digest_rejected(structure_source):
    with pytest.raises(ValueError, match='structure_review_catalog_digest'):
        structure_review(structure_source[0], expected_catalog_sha256='0' * 64)


@pytest.mark.parametrize('change,error', [
    (lambda d: d['structure']['relations'][0].update(target_id='missing'), 'relation_binding'),
    (lambda d: d['structure']['entities'][0].update(geometry_product_id='door'), 'entity_binding'),
    (lambda d: d['structure'].update(data_kind='real'), 'source_required'),
])
def test_invalid_structure_rejected(structure_source, change, error):
    root, doc = structure_source
    change(doc)
    (root / 'ifc.json').write_text(json.dumps(doc), encoding='utf-8')
    with pytest.raises(ValueError, match=error):
        run(structure_source)


def test_cli_export_does_not_overwrite(structure_source, tmp_path, monkeypatch):
    from experiments.scripts.ifc_structure_review import main
    root, _ = structure_source
    output = tmp_path / 'review.json'
    monkeypatch.setattr('sys.argv', [
        'ifc_structure_review', '--ifc-root', str(root),
        '--ifc-sha256', digest(root / 'ifc.json'), '--output', str(output)])
    main()
    original = output.read_bytes()
    assert len(json.loads(original)['tasks']) == 2
    with pytest.raises(FileExistsError):
        main()
    assert output.read_bytes() == original


def test_atlas_escapes_names_and_preserves_source_identity(structure_source):
    from experiments.scripts.ifc_structure_atlas import build_atlas
    root, doc = structure_source
    doc['products'][2]['name'] = '<script>alert(1)</script>'
    (root / 'ifc.json').write_text(json.dumps(doc), encoding='utf-8')
    html = build_atlas(root, expected_catalog_sha256=digest(root / 'ifc.json'))
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert html.count('<section id="task-') == 2
    assert html.count('<svg ') == 3  # Stair fixture has no child mesh.
    assert 'door · 待复核' in html
    assert 'opening_in' in html
