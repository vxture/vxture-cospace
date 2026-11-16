import json

import numpy as np
import pytest

from experiments.scripts import ifc_annotation_geometry as geometry
from experiments.scripts.ifc_spatial_annotation import seed
from experiments.scripts.ifc_structure_review import structure_review
from packages.data.ifc_inspection import digest
from test_ifc_sections import editor_source
from test_ifc_structure_review import structure_source


@pytest.mark.parametrize('point,closest,distance', [
    ([.5, .5, 2], [.5, .5, 0], 2),
    ([1, 1, 0], [1, 1, 0], 0),
    ([2, 2, 0], [1, 1, 0], np.sqrt(2)),
    ([-1, -1, 0], [0, 0, 0], np.sqrt(2)),
    ([1, -2, 0], [1, 0, 0], 2),
])
@pytest.mark.parametrize('winding', [[0, 1, 2], [2, 1, 0]])
def test_surface_interior_edge_vertex_and_winding(point, closest, distance, winding):
    result = geometry.nearest_surface(point, np.array([[0., 0, 0], [2, 0, 0], [0, 2, 0]]), np.array([winding]))
    assert result['distance_m'] == pytest.approx(distance)
    assert result['closest_point_xyz_m'] == pytest.approx(closest)
    assert result['triangle_index'] == 0


@pytest.mark.parametrize('vertices,closest', [
    ([[0., 0, 0], [1, 0, 0], [2, 0, 0]], [1, 0, 0]),
    ([[0., 0, 0]] * 3, [0, 0, 0]),
])
def test_degenerate_triangles_use_segments_or_vertices(vertices, closest):
    result = geometry.nearest_surface([1, 1, 0], np.array(vertices), np.array([[0, 1, 2]]))
    assert result['closest_point_xyz_m'] == closest
    assert np.isfinite(result['distance_m'])


def test_chunk_index_and_ties_are_stable(monkeypatch):
    monkeypatch.setattr(geometry, 'CHUNK_SIZE', 1)
    vertices = np.array([[0., 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 5], [2, 0, 5], [0, 2, 5]])
    faces = np.array([[3, 4, 5], [0, 1, 2], [0, 1, 2]])
    assert geometry.nearest_surface([.5, .5, 1], vertices, faces)['triangle_index'] == 1
    with pytest.raises(ValueError, match='empty_mesh'):
        geometry.nearest_surface([0, 0, 0], vertices, np.empty((0, 3), dtype=int))


def test_distance_is_invariant_under_rigid_frame_change():
    vertices = np.array([[0., 0, 0], [2, 0, 0], [0, 2, 0]])
    rotation = np.array([[1., 0, 0], [0, .6, -.8], [0, .8, .6]])
    translation = np.array([100., -200, 300])
    transformed = vertices @ rotation.T + translation
    point = np.array([.5, .5, 2]) @ rotation.T + translation
    result = geometry.nearest_surface(point, transformed, np.array([[0, 1, 2]]))
    assert result['distance_m'] == pytest.approx(2)
    assert result['closest_point_xyz_m'] == pytest.approx(np.array([.5, .5, 0]) @ rotation.T + translation)


@pytest.fixture
def endpoint_source(editor_source):
    root = editor_source
    catalog = json.loads((root / 'ifc.json').read_bytes())
    wall = next(row for row in catalog['products'] if row['global_id'] == 'wall')
    # Synthetic fixture only: use the known tetrahedron for door/opening/flight distance tests.
    for index, product in enumerate(catalog['products']):
        if product['global_id'] in ('door', 'opening', 'flight'):
            member = dict(wall['mesh'], path=f'e{index:05}.npz')
            (root / member['path']).write_bytes((root / wall['mesh']['path']).read_bytes())
            catalog['products'][index] = dict(wall, global_id=product['global_id'],
                                               ifc_type=product['ifc_type'], name=product['name'], mesh=member)
    catalog['vertices'] = sum(p.get('mesh', {}).get('vertices', 0) for p in catalog['products'])
    catalog['triangles'] = sum(p.get('mesh', {}).get('triangles', 0) for p in catalog['products'])
    (root / 'ifc.json').write_text(json.dumps(catalog), encoding='utf-8')
    checksum = digest(root / 'ifc.json')
    review = structure_review(root, expected_catalog_sha256=checksum)
    sheet = seed(review)
    sheet['evidence'] = [dict(id='test-only', sha256='a' * 64)]
    sheet['areas'] = [dict(id='area-1', name='synthetic', level_id='level',
                          footprint_xy_m=[[-1, -1], [5, -1], [5, 5], [-1, 5]],
                          z_range_m=[-1, 5], evidence_ids=['test-only'])]
    for connection, role in zip(sheet['connections'], ['side_a', 'lower']):
        connection.update(evidence_ids=['test-only'], endpoints=[
            dict(role=role, area_id='area-1', point_xyz_m=[.5, .5, 1])])
    return root, checksum, sheet


def test_pinned_endpoint_targets_and_triangle_provenance(endpoint_source):
    root, checksum, sheet = endpoint_source
    report = geometry.endpoint_geometry(root, expected_catalog_sha256=checksum, document=sheet)
    assert len(report['endpoints']) == 2
    door, stair = report['endpoints']
    assert {row['source_entity_id'] for row in door['targets']} == {'door', 'opening', 'wall'}
    assert {row['source_entity_id'] for row in stair['targets']} == {'flight'}
    assert stair['unavailable_geometry_ids'] == ['stair']
    assert report['triangle_evaluations'] == 16
    assert report['confirmed_connections'] == []
    assert report['alignment_verified'] is report['real_release_ready'] is False
    vertices = np.array([[0., 0, 0], [2, 0, 0], [0, 3, 0], [0, 0, 4]])
    faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
    for endpoint in report['endpoints']:
        for target in endpoint['targets']:
            index = target['triangle_index']
            assert target['mesh_sha256']
            closest = np.array(target['closest_point_xyz_m'])
            assert np.linalg.norm(closest - endpoint['point_xyz_m']) == pytest.approx(target['distance_m'])
            assert geometry.nearest_surface(closest, vertices, faces[index:index + 1])['distance_m'] < 1e-12


def test_empty_sheet_has_no_invented_endpoint(editor_source):
    root = editor_source
    checksum = digest(root / 'ifc.json')
    sheet = seed(structure_review(root, expected_catalog_sha256=checksum))
    report = geometry.endpoint_geometry(root, expected_catalog_sha256=checksum, document=sheet)
    assert report['endpoints'] == []
    assert report['triangle_evaluations'] == 0


def test_catalog_change_between_review_and_distance_is_rejected(endpoint_source, monkeypatch):
    root, checksum, sheet = endpoint_source
    original = geometry.structure_review

    def changed(*args, **kwargs):
        review = original(*args, **kwargs)
        catalog_path = root / 'ifc.json'
        catalog_path.write_bytes(catalog_path.read_bytes() + b'\n')
        return review

    monkeypatch.setattr(geometry, 'structure_review', changed)
    with pytest.raises(ValueError, match='catalog_changed'):
        geometry.endpoint_geometry(root, expected_catalog_sha256=checksum, document=sheet)


@pytest.mark.parametrize('problem,error', [
    ('source', 'source_binding'), ('catalog', 'catalog_digest'), ('mesh', 'ifc_mesh_changed'),
    ('endpoints', 'endpoint_budget'), ('triangles', 'triangle_budget'),
])
def test_invalid_sources_and_budgets_rejected(endpoint_source, monkeypatch, problem, error):
    root, checksum, sheet = endpoint_source
    if problem == 'source':
        sheet['frame_id'] = 'wrong'
    elif problem == 'catalog':
        checksum = '0' * 64
    elif problem == 'mesh':
        (root / 'e00001.npz').write_bytes(b'changed')
    elif problem == 'endpoints':
        monkeypatch.setattr(geometry, 'MAX_ENDPOINTS', 1)
    elif problem == 'triangles':
        monkeypatch.setattr(geometry, 'MAX_TRIANGLE_EVALUATIONS', 15)
    with pytest.raises(ValueError, match=error):
        geometry.endpoint_geometry(root, expected_catalog_sha256=checksum, document=sheet)
