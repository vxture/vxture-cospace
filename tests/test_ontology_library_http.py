import pytest
from packages.ontology.kernel import CatalogError
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def test_library_requires_login_before_reading_definitions(secured, monkeypatch):
    _, client, *_ = secured
    def forbidden():
        pytest.fail('unauthenticated request read the library')
    monkeypatch.setattr('packages.service.platform_business_http.ontology_library', forbidden)
    assert client.get('/api/ontology-library').status_code == 401


@pytest.mark.parametrize('user', ['usr_local_test', 'usr_other', 'usr_engineer', 'usr_manager'])
def test_library_is_scene_independent_read_only_and_does_not_open_private_stores(secured, monkeypatch, user):
    _, client, _, _, _, directory, *_ = secured
    headers, _ = sign_in(secured, user)
    def forbidden(*args, **kwargs):
        pytest.fail('shared definition catalog accessed a scene or workspace rule store')
    monkeypatch.setattr(directory, 'list', forbidden)
    monkeypatch.setattr('packages.service.platform_business_http.WorkspaceOntologies', forbidden)
    response = client.get('/api/ontology-library')
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    assert data['profile'] == 'vxture.ontology-catalog/0.1'
    assert data['status'] == 'draft' and len(data['modules']) == 8
    assert 'workspace_id' not in data and 'space_id' not in data
    assert client.head('/api/ontology-library').status_code == 200
    assert client.get('/api/ontology-library?space_id=anything').status_code == 422
    for method in ('POST', 'PUT', 'DELETE'):
        assert client.request(method, '/api/ontology-library', headers=headers).status_code == 403


def test_library_corruption_is_unavailable_not_empty_or_passed(secured, monkeypatch):
    _, client, *_ = secured
    sign_in(secured)
    def broken():
        raise CatalogError('dependency_mismatch', '/private/location')
    monkeypatch.setattr('packages.service.platform_business_http.ontology_library', broken)
    response = client.get('/api/ontology-library')
    assert response.status_code == 503
    assert response.json()['detail'] == 'ontology_library_unavailable'
    assert '/private/' not in response.text
