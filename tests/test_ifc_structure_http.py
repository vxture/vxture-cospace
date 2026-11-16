import json

import pytest

from packages.data.ifc_inspection import digest
from test_ifc_workspace import ifc_secured
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def declare(root, config, structure=None):
    path = root / 'ifc.json'
    catalog = json.loads(path.read_bytes())
    catalog['structure'] = structure if structure is not None else {
        'profile': 'cospace.ifc-structure-candidate/0.1',
        'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
        'entities': [{'entity_id': row['global_id'], 'geometry_product_id': row['global_id'],
                      'ifc_type': row['ifc_type'], 'role': role}
                     for row, role in zip(catalog['products'], ['building', 'wall'])],
        'relations': [{'ifc_relation_id': 'relation-1', 'kind': 'contained_in',
                       'source_id': 'wall', 'target_id': 'building'}]}
    path.write_text(json.dumps(catalog), encoding='utf-8')
    bindings = json.loads(config.read_bytes())
    bindings['bindings'][0]['catalog_sha256'] = digest(path)
    config.write_text(json.dumps(bindings), encoding='utf-8')
    return digest(path)


def test_structure_is_scene_authorized_and_pin_bound(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    sha = declare(root, config)
    params = {'space_id': spaces[0]['id'], 'catalog_sha256': sha}
    assert client.get('/api/scene-ifc/structure', params=params).status_code == 401
    sign_in(env, 'usr_local_test')
    original = access.scene_ifc.structure_view
    def denied_read(*args):
        pytest.fail('unauthorized structure read reached storage')
    monkeypatch.setattr(access.scene_ifc, 'structure_view', denied_read)
    assert client.get('/api/scene-ifc/structure', params=params).status_code == 403
    monkeypatch.setattr(access.scene_ifc, 'structure_view', original)
    sign_in(env, 'usr_engineer')
    response = client.get('/api/scene-ifc/structure', params=params)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    value = response.json()
    assert value['profile'] == 'cospace.ifc-structure-view/0.1'
    assert value['declared_role_counts'] == {'building': 1, 'wall': 1}
    assert value['relations'][0]['kind'] == 'contained_in'
    assert value['structure_available'] is True
    assert value['geometry_integrity_checked'] is value['alignment_verified'] is value['ontology_bound'] is False
    assert value['confirmed_connections'] == []
    assert str(root) not in response.text
    assert all('mesh' not in row for row in value['entities'])
    assert client.get('/api/scene-ifc/structure', params=params | {'space_id': spaces[1]['id']}).status_code == 403
    assert client.get('/api/scene-ifc/structure', params=params | {'catalog_sha256': '0' * 64}).status_code == 409
    assert client.get('/api/scene-ifc/structure', params=params | {'catalog_sha256': 'bad'}).status_code == 422
    assert client.get('/api/scene-ifc/structure', params=params | {'root': 'private'}).status_code == 422
    repeated = list(params.items()) + [('space_id', spaces[0]['id'])]
    # The shared authorization boundary rejects ambiguous scopes before dispatch.
    assert client.get('/api/scene-ifc/structure', params=repeated).status_code == 403


def test_metadata_does_not_read_mesh_and_legacy_catalog_is_explicit(ifc_secured, monkeypatch):
    env, _, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    sign_in(env, 'usr_engineer')
    params = {'space_id': spaces[0]['id'], 'catalog_sha256': digest(root / 'ifc.json')}
    result = client.get('/api/scene-ifc/structure', params=params)
    assert result.status_code == 200
    assert result.json()['structure_available'] is False
    params['catalog_sha256'] = declare(root, config)
    def no_mesh(*args):
        pytest.fail('metadata query loaded mesh')
    monkeypatch.setattr('packages.data.ifc_workspace.load_mesh', no_mesh)
    assert client.get('/api/scene-ifc/structure', params=params).status_code == 200
    (root / 'source.ifc').write_bytes(b'changed')
    assert client.get('/api/scene-ifc/structure', params=params).status_code == 409


@pytest.mark.parametrize('structure', ['invalid', {'profile': 'wrong'},
                                     {'profile': 'cospace.ifc-structure-candidate/0.1',
                                      'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
                                      'entities': [{'bad': True}], 'relations': []}])
def test_bad_structure_is_evidence_unavailable(ifc_secured, structure):
    env, _, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    sign_in(env, 'usr_engineer')
    sha = declare(root, config, structure)
    response = client.get('/api/scene-ifc/structure', params={'space_id': spaces[0]['id'], 'catalog_sha256': sha})
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'ifc_evidence_unavailable'
