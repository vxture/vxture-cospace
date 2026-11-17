import json
from pathlib import Path

import pytest

from packages.service.ifc_surface_query import SurfaceQuery, query_surface
from test_ifc_workspace import ifc_secured
from test_ifc_structure_http import declare
from test_platform_business import secured, sign_in
from test_platform_login import runtime

ROUTE = '/api/scene-ifc/nearest-surface'


def test_schema_matches_request_contract():
    path = Path('contracts/schemas/ifc-nearest-surface-request-v0.1.schema.json')
    assert json.loads(path.read_bytes()) == SurfaceQuery.model_json_schema()


@pytest.fixture
def surface_env(ifc_secured):
    env, access, root, config = ifc_secured
    pin = declare(root, config)
    catalog = json.loads((root / 'ifc.json').read_bytes())
    body = {'space_id': env[6][0]['id'], 'catalog_sha256': pin, 'frame_id': catalog['frame_id'],
            'point_xyz_m': [.5, .5, -2.], 'max_distance_m': 3.}
    return env, access, root, config, body


def test_exact_surface_not_vertex_or_bounds_and_inclusive_radius(surface_env):
    _, access, _, _, body = surface_env
    query = SurfaceQuery.model_validate(body)
    result = query_surface(access.scene_ifc, query)
    assert result['status'] == 'found'
    assert result['match']['closest_point_xyz_m'] == [.5, .5, 0.]
    assert result['match']['distance_m'] == 2.
    assert result['match']['entity_id'] == 'wall'
    assert result['match']['triangle_index'] == 0
    assert result['tested_triangles'] == 4
    assert result['without_geometry'] == 1
    assert result['alignment_verified'] is False
    assert result['ontology_bound'] is False
    assert result['real_release_ready'] is False
    assert query_surface(access.scene_ifc, query) == result
    query.max_distance_m = 2.
    assert query_surface(access.scene_ifc, query)['status'] == 'found'
    query.max_distance_m = 1.99
    outside = query_surface(access.scene_ifc, query)
    assert outside['status'] == 'no_match'
    assert outside['match'] is None


@pytest.mark.parametrize('budget', ['MAX_COMPONENTS', 'MAX_TRIANGLES', 'MAX_MESH_BYTES', 'MAX_ARRAY_BYTES'])
def test_budget_rejected_before_loading_geometry(surface_env, monkeypatch, budget):
    _, access, _, _, body = surface_env
    monkeypatch.setattr('packages.service.ifc_surface_query.' + budget, 0)
    def never(*args):
        pytest.fail('over-budget query read geometry')
    monkeypatch.setattr('packages.service.ifc_surface_query.load_mesh', never)
    query = SurfaceQuery.model_validate(body)
    with pytest.raises(ValueError, match='budget'):
        query_surface(access.scene_ifc, query)


def test_source_changed_during_query_rejected(surface_env, monkeypatch):
    _, access, root, _, body = surface_env
    from packages.service.ifc_surface_query import load_mesh
    def changed(*args):
        arrays = load_mesh(*args)
        (root / 'source.ifc').write_bytes(b'changed')
        return arrays
    monkeypatch.setattr('packages.service.ifc_surface_query.load_mesh', changed)
    query = SurfaceQuery.model_validate(body)
    with pytest.raises(ValueError, match='source_changed'):
        query_surface(access.scene_ifc, query)


def test_no_extracted_geometry_is_unavailable_not_no_match(surface_env):
    _, access, root, config, body = surface_env
    catalog = json.loads((root / 'ifc.json').read_bytes())
    for p in catalog['products']:
        p['geometry_status'] = 'no_representation'
    for key in ('vertices', 'triangles'):
        catalog[key] = 0
    (root / 'ifc.json').write_text(json.dumps(catalog), encoding='utf-8')
    pin = declare(root, config)
    query = SurfaceQuery.model_validate(body | {'catalog_sha256': pin})
    result = query_surface(access.scene_ifc, query)
    assert result['status'] == 'geometry_unavailable'
    assert result['match'] is None


def test_tied_components_and_damaged_other_mesh_cannot_be_skipped(surface_env):
    _, access, root, config, body = surface_env
    catalog = json.loads((root / 'ifc.json').read_bytes())
    product = catalog['products'][1]
    other = dict(product, global_id='wall-other', mesh=product['mesh'] | {'path': 'e00002.npz'})
    catalog['products'].append(other)
    catalog['product_count'] += 1
    catalog['vertices'] += product['mesh']['vertices']
    catalog['triangles'] += product['mesh']['triangles']
    catalog['structure']['entities'].append(catalog['structure']['entities'][1] |
                                          {'entity_id': 'wall-other', 'geometry_product_id': 'wall-other'})
    (root / 'e00002.npz').write_bytes((root / 'e00001.npz').read_bytes())
    (root / 'ifc.json').write_text(json.dumps(catalog), encoding='utf-8')
    pin = declare(root, config, catalog['structure'])
    query = SurfaceQuery.model_validate(body | {'catalog_sha256': pin})
    result = query_surface(access.scene_ifc, query)
    assert result['tested_components'] == 2
    assert result['match']['element_id'] == 'e00001'
    assert result['match']['triangle_index'] == 0
    (root / 'e00002.npz').write_bytes(b'changed')
    with pytest.raises(ValueError, match='mesh_changed'):
        query_surface(access.scene_ifc, query)


@pytest.mark.parametrize('change', [
    {'point_xyz_m': [0, 1]}, {'point_xyz_m': [True, 1, 2]}, {'point_xyz_m': [0, 0, float('inf')]},
    {'point_xyz_m': [1_000_001, 0, 0]}, {'max_distance_m': 0}, {'max_distance_m': 1001},
    {'catalog_sha256': 'bad'}, {'frame_id': 'cloud'}, {'path': '../private'},
])
def test_request_validation(surface_env, change):
    body = surface_env[-1] | change
    with pytest.raises(ValueError):
        SurfaceQuery.model_validate(body)


def test_http_authorization_csrf_and_complete_geometry(surface_env, monkeypatch):
    env, access, root, _, body = surface_env
    client = env[1]
    assert client.post(ROUTE, json=body).status_code == 401
    headers, _ = sign_in(env, 'usr_local_test')
    original = access.scene_ifc.catalog
    def never(*args):
        pytest.fail('unauthorized query read storage')
    monkeypatch.setattr(access.scene_ifc, 'catalog', never)
    assert client.post(ROUTE, json=body, headers=headers).status_code == 403
    monkeypatch.setattr(access.scene_ifc, 'catalog', original)
    headers, _ = sign_in(env, 'usr_engineer')
    assert client.post(ROUTE, json=body).status_code == 403
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    response = client.post(ROUTE, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['match']['entity_id'] == 'wall'
    assert str(root) not in response.text
    for change, status in [({'frame_id': 'ifc_world_' + '0' * 16}, 409),
                           ({'catalog_sha256': '0' * 64}, 409), ({'max_distance_m': 0}, 422),
                           ({'space_id': env[6][1]['id']}, 403)]:
        assert client.post(ROUTE, json=body | change, headers=headers).status_code == status
    assert client.post(ROUTE + '?root=private', json=body, headers=headers).status_code == 422
    assert client.get(ROUTE, params={'space_id': body['space_id']}).status_code == 403
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    (root / 'e00001.npz').write_bytes(b'changed')
    assert client.post(ROUTE, json=body, headers=headers).status_code == 409
