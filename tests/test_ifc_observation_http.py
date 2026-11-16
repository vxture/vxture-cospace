import json
import sqlite3

import pytest

from packages.service.ifc_opening_observations import observation_scope
from test_ifc_structure_http import declare
from test_ifc_workspace import ifc_secured
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_observation_journal import report

ROUTE = '/api/scene-ifc/opening-observation'


def door_source(root, config):
    path = root / 'ifc.json'
    catalog = json.loads(path.read_bytes())
    catalog['products'][1]['ifc_type'] = 'IfcDoor'
    path.write_text(json.dumps(catalog), encoding='utf-8')
    declare(root, config)
    catalog = json.loads(path.read_bytes())
    catalog['structure']['entities'][1]['role'] = 'door'
    return declare(root, config, catalog['structure'])


def test_authorized_read_does_not_create_registration_and_rejects_stale_catalog(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    sha = door_source(root, config)
    params = {'space_id': spaces[0]['id'], 'element_id': 'e00001', 'catalog_sha256': sha}
    assert client.get(ROUTE, params=params).status_code == 401
    original = access.ifc_observations.read
    def denied(*args):
        pytest.fail('authorization did not precede observation read')
    monkeypatch.setattr(access.ifc_observations, 'read', denied)
    sign_in(env, 'usr_local_test')
    assert client.get(ROUTE, params=params).status_code == 403
    sign_in(env, 'usr_engineer')
    monkeypatch.setattr(access.ifc_observations, 'read', original)
    result = client.get(ROUTE, params=params)
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    assert result.json()['configured'] is False
    assert result.json()['status'] == 'unavailable'
    assert not access.ifc_observations.journal.path.exists()
    for change, status in [({'space_id': spaces[1]['id']}, 403), ({'catalog_sha256': '0' * 64}, 409),
                           ({'element_id': 'e00000'}, 409), ({'as_of': 'client-time'}, 422)]:
        assert client.get(ROUTE, params=params | change).status_code == status
    assert client.post(ROUTE, json={}).status_code == 403
    (root / 'source.ifc').write_bytes(b'changed')
    assert client.get(ROUTE, params=params).status_code == 409


@pytest.fixture
def registered_door(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    rp, client, _, _, _, _, spaces, *_ = env
    sha = door_source(root, config)
    sign_in(env, 'usr_engineer')
    original = rp.verifier.verify
    captured = []
    def capture(token):
        value = original(token)
        captured.append(value)
        return value
    monkeypatch.setattr(rp.verifier, 'verify', capture)
    params = {'space_id': spaces[0]['id'], 'element_id': 'e00001', 'catalog_sha256': sha}
    assert client.get(ROUTE, params=params).status_code == 200
    scope = observation_scope(captured[-1], spaces[0]['id'], sha)
    journal = access.ifc_observations.journal
    doc = {'profile': 'cospace.opening-observation-registration/0.1', 'scope': scope,
           'data_kind': 'ifc_design_candidate', 'subjects': [{'entity_id': 'wall', 'role': 'door'}], 'producers': ['sensor-a']}
    journal.register(doc)
    access.ifc_observations.clock = lambda: '2026-11-17T00:05:00Z'
    journal.clock = lambda: '2026-11-17T00:01:00Z'
    journal.append(scope, report(entity_id='wall'), authenticated_producer='sensor-a')
    return client, journal, root, params, scope, doc


def test_registered_reports_are_scoped_to_authenticated_tenant_and_not_geometry(registered_door, monkeypatch):
    client, journal, root, params, scope, _ = registered_door
    def no_mesh(*args):
        pytest.fail('observation read loaded geometry')
    monkeypatch.setattr('packages.data.ifc_workspace.load_mesh', no_mesh)
    value = client.get(ROUTE, params=params).json()
    assert value['configured'] is True
    assert value['status'] == 'reported'
    assert value['value'] == 'closed'
    assert value['source_content_verified'] is value['real_release_ready'] is False
    assert value['catalog_content_verified'] is True
    assert value['reported_at'] == '2026-11-17T00:01:00Z'
    assert value['active_count'] == 1
    assert 'report' not in value
    assert str(root) not in json.dumps(value)
    assert journal.registered(scope | {'workspace': 'other-workspace'}) is False
    assert journal.registered(scope, 'wall') is True
    assert journal.registered(scope, 'not-registered-door') is False
    journal.clock = lambda: '2026-11-17T00:02:00Z'
    journal.append(scope, report('late-old', entity_id='wall', observed_at='2026-11-16T23:59:00Z', value='open'),
                   authenticated_producer='sensor-a')
    value = client.get(ROUTE, params=params).json()
    assert value['value'] == 'closed'
    assert value['reported_at'] == '2026-11-17T00:02:00Z'


def test_storage_failure_is_unavailable_not_normal(ifc_secured):
    env, access, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    sha = door_source(root, config)
    sign_in(env, 'usr_engineer')
    path = access.ifc_observations.journal.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'broken database')
    response = client.get(ROUTE, params={'space_id': spaces[0]['id'], 'element_id': 'e00001', 'catalog_sha256': sha})
    assert response.status_code == 503
    assert response.json()['detail'] == 'observation_storage_unavailable'


@pytest.mark.parametrize('corruption', ['registration', 'record', 'received_time', 'scope_binding'])
def test_corrupted_persisted_data_is_not_a_client_parameter_error(registered_door, corruption):
    client, journal, _, params, _, doc = registered_door
    with sqlite3.connect(journal.path) as db:
        if corruption == 'registration':
            db.execute('UPDATE registrations SET document=?', (b'{}',))
        elif corruption == 'record':
            db.execute('UPDATE reports SET document=?', (b'{}',))
        elif corruption == 'received_time':
            db.execute('UPDATE reports SET received_at=?', ('bad-time',))
        else:
            doc['scope']['workspace'] = 'wrong-workspace'
            db.execute('UPDATE registrations SET document=?', (json.dumps(doc).encode(),))
    response = client.get(ROUTE, params=params)
    assert response.status_code == 503
    assert response.json()['detail'] == 'observation_storage_unavailable'
