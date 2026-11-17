import base64
import json
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np
import pytest

from packages.views.agent.ifc_offline_surface import OfflineSurfaceQuery, query_package_surface
from packages.views.agent.ifc_offline_package import export_design_package
from packages.service.ifc_surface_query import SurfaceQuery, query_surface
from packages.spatial.scene_identity import canonical
from test_ifc_offline_package import package, sha, unpack, pack
from test_ifc_workspace import ifc_secured
from test_ifc_structure_http import declare
from test_platform_business import secured
from test_platform_login import runtime


def node_query(raw, source, query, expected_sha=None):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    uri = Path('examples/scene-graph/consumers/query-ifc-package.mjs').resolve().as_uri()
    script = ('import {queryPackageSurface} from ' + json.dumps(uri) + ';'
              "let text='';for await(const chunk of process.stdin){text+=chunk;}const p=JSON.parse(text);"
              "try{process.stdout.write(JSON.stringify(queryPackageSurface(Buffer.from(p.raw,'base64'),p.expected,p.query)));}"
              "catch(e){process.stderr.write(e.message);process.exitCode=1;}")
    payload = {'raw': base64.b64encode(raw).decode(), 'expected': {'sha256': expected_sha or sha(raw), 'source': source},
               'query': query}
    return subprocess.run([node, '--input-type=module', '-e', script], input=json.dumps(payload),
                          text=True, capture_output=True, timeout=60, check=False, shell=False)


def request(raw, **changes):
    _, payloads = unpack(raw)
    return {'frame_id': json.loads(payloads[0])['frame_id'], 'point_xyz_m': [.5, .5, -2.],
            'max_distance_m': 3.} | changes


def both(raw, source, query):
    result = query_package_surface(raw, expected_sha256=sha(raw), expected_source=source, query=query)
    node = node_query(raw, source, query)
    assert node.returncode == 0, node.stderr
    other = json.loads(node.stdout)
    if result['match'] is not None:
        for key in ('distance_m', 'closest_point_xyz_m'):
            assert other['match'][key] == pytest.approx(result['match'][key], abs=1e-9)
            other['match'][key] = result['match'][key]
    assert other == result
    return result


def test_offline_matches_service_without_original_files_or_service_calls(package, monkeypatch):
    raw, source, (_, access, root, _), space, pin = package
    query = request(raw)
    online = query_surface(access.scene_ifc, SurfaceQuery.model_validate(query | {
        'space_id': space, 'catalog_sha256': pin}))
    for path in root.iterdir():
        if path.is_file():
            path.unlink()
    def never(*args):
        pytest.fail('offline query accessed original data')
    monkeypatch.setattr(access.scene_ifc, 'catalog', never)
    result = both(raw, source, query)
    assert result['status'] == 'found'
    expected_match = result['match'].copy()
    assert len(expected_match.pop('geometry_component_sha256')) == 64
    assert expected_match == online['match']
    assert result['match']['closest_point_xyz_m'] == [.5, .5, 0.]
    assert result['match']['distance_m'] == 2.
    assert result['tested_triangles'] == 4
    assert result['without_geometry'] == 1
    for key in ('original_ifc_content_verified', 'original_mesh_content_verified', 'alignment_verified',
                'ontology_bound', 'real_release_ready'):
        assert result[key] is False
    assert both(raw, source, query) == result


@pytest.mark.parametrize('radius,status', [(2., 'found'), (1.99, 'no_match')])
def test_inclusive_radius_and_no_match(package, radius, status):
    raw, source, *_ = package
    result = both(raw, source, request(raw, max_distance_m=radius))
    assert result['status'] == status
    assert (result['match'] is None) == (status == 'no_match')


@pytest.mark.parametrize('point,expected', [([-2., 0., 0.], [0., 0., 0.]),
                                          ([.5, -2., 0.], [.5, 0., 0.]),
                                          ([0., 0., 0.], [0., 0., 0.])])
def test_edge_vertex_and_shared_face_ties(package, point, expected):
    raw, source, *_ = package
    result = both(raw, source, request(raw, point_xyz_m=point))
    assert result['match']['closest_point_xyz_m'] == expected
    assert result['match']['triangle_index'] == 0


@pytest.mark.parametrize('change', [
    {'point_xyz_m': [0, 1]}, {'point_xyz_m': [True, 1, 2]}, {'point_xyz_m': [0, 0, '0']},
    {'point_xyz_m': [1_000_001, 0, 0]}, {'max_distance_m': 0}, {'max_distance_m': 1001},
    {'max_distance_m': True}, {'frame_id': 'cloud'}, {'path': '../private'},
])
def test_invalid_query_rejected_by_both(package, change):
    raw, source, *_ = package
    query = request(raw, **change)
    expected = sha(raw)
    with pytest.raises(ValueError):
        query_package_surface(raw, expected_sha256=expected, expected_source=source, query=query)
    assert node_query(raw, source, query).returncode != 0


@pytest.mark.parametrize('value', [float('inf'), float('nan'), float('-inf')])
def test_nonfinite_query_is_rejected(package, value):
    raw, source, *_ = package
    expected = sha(raw)
    query = request(raw, point_xyz_m=[value, 0., 0.])
    with pytest.raises(ValueError):
        query_package_surface(raw, expected_sha256=expected, expected_source=source, query=query)


def test_node_api_rejects_nonfinite_and_sparse_coordinates_before_package_read():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    uri = Path('examples/scene-graph/consumers/query-ifc-package.mjs').resolve().as_uri()
    script = ('import {queryPackageSurface} from ' + json.dumps(uri) + ';'
              "for(const point of [[Infinity,0,0],[NaN,0,0],new Array(3)]){"
              "try{queryPackageSurface(Buffer.alloc(0),{}, {frame_id:'ifc_world_'+'a'.repeat(16),"
              "point_xyz_m:point,max_distance_m:1});throw new Error('accepted_invalid_point');}"
              "catch(e){if(e.message!=='offline_surface_point'){throw e;}}}")
    subprocess.run([node, '--input-type=module', '-e', script], check=True, timeout=30, shell=False)


@pytest.mark.parametrize('failure', ['frame', 'source', 'digest', 'damage'])
def test_pins_and_frame_must_match_before_any_result(package, failure):
    raw, source, *_ = package
    query = request(raw)
    expected = sha(raw)
    if failure == 'frame':
        query['frame_id'] = 'ifc_world_' + '0' * 16
    elif failure == 'source':
        source = source | {'catalog_sha256': '0' * 64}
    elif failure == 'digest':
        expected = '0' * 64
    else:
        raw = raw[:-1] + bytes([raw[-1] ^ 1])
        expected = sha(raw)  # Even repinning a damaged package cannot bypass member hashes.
    with pytest.raises(ValueError):
        query_package_surface(raw, expected_sha256=expected, expected_source=source, query=query)
    assert node_query(raw, source, query, expected).returncode != 0


@pytest.mark.parametrize('vertices,point,expected', [
    ([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], [.5, 2., 0.], [.5, 0., 0.]),
    ([[0, 0, 0]] * 4, [0., 2., 0.], [0., 0., 0.]),
])
def test_degenerate_triangles_use_segments_and_points(package, vertices, point, expected):
    raw, source, *_ = package
    manifest, payloads = unpack(raw)
    geometry = payloads[1]
    size = struct.unpack_from('<I', geometry, 8)[0]
    start = 12 + size
    replacement = np.asarray(vertices, dtype='<f8').tobytes()
    payloads[1] = geometry[:start] + replacement + geometry[start + len(replacement):]
    manifest['members'][1]['sha256'] = sha(payloads[1])
    raw = pack(manifest, payloads)
    result = both(raw, source, request(raw, point_xyz_m=point))
    assert result['match']['closest_point_xyz_m'] == expected
    assert result['match']['triangle_index'] == 0


def test_no_geometry_is_unavailable_not_no_match(package):
    _, _, (_, access, root, config), space, _ = package
    path = root / 'ifc.json'
    catalog = json.loads(path.read_bytes())
    for product in catalog['products']:
        product['geometry_status'] = 'no_representation'
    catalog['vertices'] = catalog['triangles'] = 0
    path.write_text(json.dumps(catalog), encoding='utf-8')
    pin = declare(root, config)
    raw = export_design_package(access.scene_ifc, space, pin)
    source = unpack(raw)[0]['source']
    result = both(raw, source, request(raw))
    assert result['status'] == 'geometry_unavailable'
    assert result['match'] is None


def two_components(package):
    _, _, (_, access, root, config), space, _ = package
    catalog = json.loads((root / 'ifc.json').read_bytes())
    product = catalog['products'][1]
    catalog['products'].append(product | {'global_id': 'other', 'mesh': product['mesh'] | {'path': 'e00002.npz'}})
    catalog['product_count'] += 1
    catalog['vertices'] += product['mesh']['vertices']
    catalog['triangles'] += product['mesh']['triangles']
    catalog['structure']['entities'].append(catalog['structure']['entities'][1] |
                                          {'entity_id': 'other', 'geometry_product_id': 'other'})
    (root / 'e00002.npz').write_bytes((root / 'e00001.npz').read_bytes())
    (root / 'ifc.json').write_text(json.dumps(catalog), encoding='utf-8')
    pin = declare(root, config, catalog['structure'])
    raw = export_design_package(access.scene_ifc, space, pin)
    source = unpack(raw)[0]['source']
    return raw, source


def test_tied_components_and_corrupt_nonwinning_member(package):
    raw, source = two_components(package)
    result = both(raw, source, request(raw))
    assert result['tested_components'] == 2
    assert result['match']['element_id'] == 'e00001'
    # The winning member is intact. Damage elsewhere must still reject the whole query.
    raw = raw[:-1] + bytes([raw[-1] ^ 1])
    expected, query = sha(raw), request(raw)
    with pytest.raises(ValueError, match='member_digest'):
        query_package_surface(raw, expected_sha256=expected, expected_source=source, query=query)
    assert node_query(raw, source, request(raw)).returncode != 0


def test_total_triangle_budget_is_enforced_by_both_consumers(package, monkeypatch):
    raw, source = two_components(package)
    manifest, payloads = unpack(raw)
    for i in (1, 2):
        size = struct.unpack_from('<I', payloads[i], 8)[0]
        header = json.loads(payloads[i][12:12 + size])
        points = payloads[i][12 + size:12 + size + header['vertices'] * 24]
        header['triangles'] = 200_001  # Each valid member is within its own 400,000 budget.
        metadata = canonical(header)
        faces = np.tile(np.array([0, 1, 2], dtype='<u4'), header['triangles']).tobytes()
        payloads[i] = b'CSIFCG01' + struct.pack('<I', len(metadata)) + metadata + points + faces
        manifest['members'][i] |= {'sha256': sha(payloads[i]), 'bytes': len(payloads[i])}
    raw = pack(manifest, payloads)
    def never(*args, **kwargs):
        pytest.fail('over-budget package started distance work')
    monkeypatch.setattr('packages.views.agent.ifc_offline_surface.nearest_surface', never)
    expected, query = sha(raw), request(raw)
    with pytest.raises(ValueError, match='triangle_budget'):
        query_package_surface(raw, expected_sha256=expected, expected_source=source, query=query)
    result = node_query(raw, source, request(raw))
    assert result.returncode != 0
    assert 'triangle_budget' in result.stderr


def test_query_budget_refuses_before_distance_work(package, monkeypatch):
    raw, source, *_ = package
    monkeypatch.setattr('packages.views.agent.ifc_offline_surface.MAX_TRIANGLES', 0)
    def never(*args, **kwargs):
        pytest.fail('over-budget query started surface work')
    monkeypatch.setattr('packages.views.agent.ifc_offline_surface.nearest_surface', never)
    expected, query = sha(raw), request(raw)
    with pytest.raises(ValueError, match='triangle_budget'):
        query_package_surface(raw, expected_sha256=expected, expected_source=source, query=query)


def test_request_schema():
    path = Path('contracts/schemas/ifc-offline-nearest-surface-request-v0.1.schema.json')
    assert json.loads(path.read_bytes()) == OfflineSurfaceQuery.model_json_schema()
