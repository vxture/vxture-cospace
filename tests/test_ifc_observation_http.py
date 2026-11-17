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
    history = {'as_of': '2026-11-16T00:00:00Z', 'known_at': '2026-11-16T00:00:00Z', 'through_sequence': '0'}
    assert client.get(ROUTE, params=params | history).status_code == 409
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


def replay_params(value):
    return {key: str(value[key]) for key in ('as_of', 'known_at', 'through_sequence')}


def test_http_replay_pins_same_time_corrections_and_retractions(registered_door):
    client, journal, _, params, scope, _ = registered_door
    first = client.get(ROUTE, params=params).json()
    # A correction received at exactly the same instant is excluded by sequence.
    journal.append(scope, report('corrected', entity_id='wall', value='open', supersedes='event-1'),
                   authenticated_producer='sensor-a')
    second = client.get(ROUTE, params=params).json()
    assert second['value'] == 'open'
    replay = client.get(ROUTE, params=params | replay_params(first))
    assert replay.status_code == 200
    assert replay.json() == first
    assert replay.headers['cache-control'] == 'no-store'
    journal.clock = lambda: '2026-11-17T00:03:00Z'
    journal.append(scope, report('retracted', entity_id='wall', operation='retract', value=None,
                                supersedes='corrected'), authenticated_producer='sensor-a')
    assert client.get(ROUTE, params=params).json()['status'] == 'retracted'
    assert client.get(ROUTE, params=params | replay_params(second)).json() == second
    # Knowledge time also excludes the later retraction, independently of sequence.
    latest = client.get(ROUTE, params=params).json()
    historical = replay_params(latest) | {'known_at': '2026-11-17T00:02:00Z'}
    assert client.get(ROUTE, params=params | historical).json()['value'] == 'open'
    before_observed = historical | {'as_of': '2026-11-16T23:59:00Z'}
    assert client.get(ROUTE, params=params | before_observed).json()['status'] == 'unavailable'
    expired = historical | {'as_of': '2026-11-17T00:10:00Z'}
    # Future query times are rejected rather than implying a prediction.
    assert client.get(ROUTE, params=params | expired).status_code == 422


@pytest.mark.parametrize('change', [
    {'as_of': '2026-11-17T00:06:00Z'}, {'known_at': '2026-11-17T00:06:00Z'},
    {'as_of': '2026-02-30T00:00:00Z'}, {'known_at': '2026-11-17T00:00:00+00:00'},
    {'through_sequence': '-1'}, {'through_sequence': '1.0'}, {'through_sequence': '01'},
    {'through_sequence': '10000000000000000'}, {'through_sequence': ''},
])
def test_replay_invalid_parameters(registered_door, change):
    client, _, _, params, _, _ = registered_door
    value = client.get(ROUTE, params=params).json()
    assert client.get(ROUTE, params=params | replay_params(value) | change).status_code == 422


def test_replay_requires_complete_unique_context_and_available_sequence(registered_door):
    client, _, _, params, _, _ = registered_door
    value = client.get(ROUTE, params=params).json()
    context = replay_params(value)
    for missing in context:
        partial = {key: item for key, item in context.items() if key != missing}
        assert client.get(ROUTE, params=params | partial).status_code == 422
    duplicate = list((params | context).items()) + [('known_at', context['known_at'])]
    # Shared request authorization rejects ambiguous duplicate query keys first.
    assert client.get(ROUTE, params=duplicate).status_code == 403
    assert client.get(ROUTE, params=params | context | {'extra': '1'}).status_code == 422
    assert client.get(ROUTE, params=params | context | {'through_sequence': '999'}).status_code == 409
    empty = client.get(ROUTE, params=params | context | {'through_sequence': '0'}).json()
    assert empty['status'] == 'unavailable'
    assert empty['reported_at'] is None
    assert empty['through_sequence'] == 0


def test_replay_is_authorized_before_storage(registered_door, monkeypatch):
    client, _, _, params, _, _ = registered_door
    value = client.get(ROUTE, params=params).json()
    def denied(*args, **kwargs):
        pytest.fail('unauthorized replay reached storage')
    monkeypatch.setattr('packages.service.ifc_opening_observations.IfcOpeningObservations.read', denied)
    unauthorized = params | replay_params(value) | {'space_id': 'space-' + '2' * 16}
    assert client.get(ROUTE, params=unauthorized).status_code == 403


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
