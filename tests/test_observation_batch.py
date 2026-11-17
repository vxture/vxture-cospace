from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3

import pytest

from packages.infrastructure.spatial_observation_store import ObservationJournal
from packages.service.ifc_opening_observations import ObservationBatchQuery
from test_observation_journal import registration, report
from test_ifc_observation_http import registered_door, door_source
from test_ifc_structure_http import declare
from test_ifc_workspace import ifc_secured
from test_platform_business import secured, sign_in
from test_platform_login import runtime

ROUTE = '/api/scene-ifc/opening-observations'
WHEN = '2026-11-17T00:05:00Z'


@pytest.fixture
def pair(tmp_path):
    store = ObservationJournal(tmp_path, clock=lambda: '2026-11-17T00:01:00Z')
    document = registration()
    document['subjects'].append({'entity_id': 'door-2', 'role': 'door'})
    store.register(document)
    store.append_batch(document['scope'], [report(), report('second', entity_id='door-2', value='open')],
                       authenticated_producer='sensor-a')
    return store, document['scope']


def read(pair, **changes):
    store, scope = pair
    return store.resolve_many(scope, ['door-1', 'door-2'], as_of=WHEN, known_at=WHEN, **changes)


def test_batch_has_common_context_and_compatible_single_cursors(pair, monkeypatch):
    import packages.infrastructure.spatial_observation_store as module
    original = module._records
    calls = []
    def capture(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(module, '_records', capture)
    batch = read(pair)
    assert len(calls) == 1
    assert [s['value'] for s in batch['states']] == ['closed', 'open']
    for state in batch['states']:
        for key in ('records_sha256', 'registration_sha256', 'as_of', 'known_at', 'through_sequence'):
            assert state[key] == batch[key]
        assert pair[0].resolve(pair[1], state['entity_id'], as_of=WHEN, known_at=WHEN) == state


def test_append_between_object_resolutions_cannot_mix_batch_state(pair, monkeypatch):
    import packages.infrastructure.spatial_observation_store as module
    store, scope = pair
    before = read(pair)
    original = module._resolved_state
    calls = []
    def append_during_resolution(*args, **kwargs):
        if not calls:
            calls.append(True)
            store.append(scope, report('corrected-second', entity_id='door-2', value='closed', supersedes='second'),
                         authenticated_producer='sensor-a')
        return original(*args, **kwargs)
    monkeypatch.setattr(module, '_resolved_state', append_during_resolution)
    assert read(pair) == before
    assert read(pair)['states'][1]['value'] == 'closed'
    assert read(pair, through_sequence=before['through_sequence']) == before


def test_sqlite_read_snapshot_excludes_concurrent_commit_after_registration_read(pair, monkeypatch):
    import packages.infrastructure.spatial_observation_store as module
    store, scope = pair
    # WAL allows a separate writer to commit while the read transaction remains open.
    from contextlib import closing
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    before = read(pair)
    original = module._records
    calls = []
    def append_before_records(db, key):
        if not calls:
            calls.append(True)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(store.append, scope, report('late', entity_id='door-2', value='closed', supersedes='second'),
                            authenticated_producer='sensor-a').result(timeout=5)
        return original(db, key)
    monkeypatch.setattr(module, '_records', append_before_records)
    assert read(pair) == before
    assert read(pair)['states'][1]['value'] == 'closed'


@pytest.mark.parametrize('entities', [[], ['door-1', 'door-1'], ['door-1'] * 129, [None], 'door-1', ['missing']])
def test_batch_refuses_invalid_or_unregistered_subjects(pair, entities):
    store, scope = pair
    with pytest.raises(ValueError):
        store.resolve_many(scope, entities, as_of=WHEN, known_at=WHEN)


def test_batch_can_replay_empty_prefix_and_order_is_explicit(pair):
    empty = read(pair, through_sequence=0)
    assert [s['status'] for s in empty['states']] == ['unavailable', 'unavailable']
    normal = read(pair)
    reverse = pair[0].resolve_many(pair[1], ['door-2', 'door-1'], as_of=WHEN, known_at=WHEN)
    assert reverse['states'] == list(reversed(normal['states']))
    assert reverse['cursor'] != normal['cursor']


def test_full_batch_budget_accepts_128_distinct_registered_subjects(tmp_path):
    store = ObservationJournal(tmp_path)
    document = registration()
    subjects = [f'door-{i}' for i in range(128)]
    document['subjects'] = [{'entity_id': identity, 'role': 'door'} for identity in subjects]
    store.register(document)
    batch = store.resolve_many(document['scope'], subjects, as_of=WHEN, known_at=WHEN)
    assert len(batch['states']) == 128
    assert all(state['status'] == 'unavailable' for state in batch['states'])
    with pytest.raises(ValueError, match='subject_not_registered'):
        store.resolve_many(document['scope'], ['door-0', 'not-registered'], as_of=WHEN, known_at=WHEN)


def body(params):
    return {key: value for key, value in params.items() if key != 'element_id'} | {'element_ids': [params['element_id']]}


def csrf(client):
    return {'Origin': str(client.base_url).rstrip('/'), 'X-CoSpace-CSRF': client.get('/api/auth/session').json()['csrf']}


def test_http_batch_preserves_single_state_and_replays_after_correction(registered_door):
    client, journal, _, params, scope, _ = registered_door
    headers = csrf(client)
    single = client.get('/api/scene-ifc/opening-observation', params=params).json()
    response = client.post(ROUTE, json=body(params), headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    batch = response.json()
    state = batch['states'][0]
    for key in state:
        assert state[key] == single[key]
    assert 'scope' not in batch
    assert 'active' not in state
    assert 'producer' not in json.dumps(batch)
    journal.append(scope, report('correction', entity_id='wall', value='open', supersedes='event-1'),
                   authenticated_producer='sensor-a')
    assert client.post(ROUTE, json=body(params), headers=headers).json()['states'][0]['value'] == 'open'
    replay = {key: str(batch[key]) for key in ('as_of', 'known_at', 'through_sequence')}
    assert client.post(ROUTE, json=body(params) | {'replay': replay}, headers=headers).json() == batch
    assert client.post(ROUTE, json=body(params)).status_code == 403


def test_http_authorization_precedes_batch_read_and_no_registration_is_created(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    client = env[1]
    pin = door_source(root, config)
    query = {'space_id': env[6][0]['id'], 'catalog_sha256': pin, 'element_ids': ['e00001']}
    assert client.post(ROUTE, json=query).status_code == 401
    original = access.ifc_observations.read_many
    def never(*args):
        pytest.fail('unauthorized batch reached storage')
    monkeypatch.setattr(access.ifc_observations, 'read_many', never)
    headers, _ = sign_in(env, 'usr_local_test')
    assert client.post(ROUTE, json=query, headers=headers).status_code == 403
    headers, _ = sign_in(env, 'usr_engineer')
    assert client.post(ROUTE, json=query | {'space_id': env[6][1]['id']}, headers=headers).status_code == 403
    monkeypatch.setattr(access.ifc_observations, 'read_many', original)
    assert client.post(ROUTE, json=query, headers=headers).status_code == 409
    assert not access.ifc_observations.journal.path.exists()
    assert client.get(ROUTE, params=query).status_code == 403


@pytest.mark.parametrize('change', [
    {'element_ids': []}, {'element_ids': ['e00001', 'e00001']}, {'element_ids': ['../private']},
    {'element_ids': ['e00001'] * 129}, {'extra': 'value'},
    {'replay': {'as_of': WHEN}},
    {'replay': {'as_of': '2026-11-17T00:06:00Z', 'known_at': WHEN, 'through_sequence': '1'}},
])
def test_http_invalid_batch_context_is_rejected(registered_door, change):
    client, _, _, params, _, _ = registered_door
    assert client.post(ROUTE, json=body(params) | change, headers=csrf(client)).status_code == 422


@pytest.mark.parametrize('change', [{'element_ids': ['e00000']}, {'element_ids': ['e99999']},
                                    {'catalog_sha256': '0' * 64}])
def test_http_unavailable_sources_or_nondoors_are_not_partial_results(registered_door, change):
    client, _, _, params, _, _ = registered_door
    assert client.post(ROUTE, json=body(params) | change, headers=csrf(client)).status_code == 409


def test_http_multiple_doors_share_one_read_and_unknown_is_distinct_from_unregistered(registered_door, ifc_secured, monkeypatch):
    client, journal, root, params, scope, document = registered_door
    _, access, _, config = ifc_secured
    catalog = json.loads((root / 'ifc.json').read_bytes())
    catalog['products'].append(catalog['products'][0] | {'global_id': 'door-two', 'ifc_type': 'IfcDoor',
                                                       'geometry_status': 'no_representation'})
    catalog['product_count'] += 1
    catalog['structure']['entities'].append({'entity_id': 'door-two', 'geometry_product_id': 'door-two',
                                             'ifc_type': 'IfcDoor', 'role': 'door'})
    (root / 'ifc.json').write_text(json.dumps(catalog), encoding='utf-8')
    pin = declare(root, config, catalog['structure'])
    scope = scope | {'catalog_sha256': pin}
    document = document | {'scope': scope, 'subjects': document['subjects'] + [{'entity_id': 'door-two', 'role': 'door'}]}
    journal.register(document)
    journal.append(scope, report(entity_id='wall'), authenticated_producer='sensor-a')
    query = body(params) | {'catalog_sha256': pin, 'element_ids': ['e00002', 'e00001']}
    original = access.scene_ifc.structure_view
    calls = []
    def capture(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(access.scene_ifc, 'structure_view', capture)
    result = client.post(ROUTE, json=query, headers=csrf(client))
    assert result.status_code == 200, result.text
    assert len(calls) == 1
    batch = result.json()
    assert [s['element_id'] for s in batch['states']] == query['element_ids']
    assert [s['status'] for s in batch['states']] == ['unavailable', 'reported']
    assert [s['value'] for s in batch['states']] == [None, 'closed']
    journal.append(scope, report('conflicting', entity_id='wall', value='open'), authenticated_producer='sensor-a')
    assert client.post(ROUTE, json=query, headers=csrf(client)).json()['states'][1]['status'] == 'conflict'
    # A registered door with no reports differs from a door absent from the registration.
    from contextlib import closing
    from packages.spatial.scene_identity import canonical
    with closing(sqlite3.connect(journal.path)) as db, db:
        raw = canonical(document | {'subjects': [{'entity_id': 'wall', 'role': 'door'}]})
        from packages.spatial.opening_observations import scope_key
        db.execute('UPDATE registrations SET document=? WHERE scope=?', (raw, scope_key(scope)))
    assert client.post(ROUTE, json=query, headers=csrf(client)).status_code == 409


def test_http_batch_query_is_read_only_and_storage_failure_is_503(registered_door):
    client, journal, _, params, _, _ = registered_door
    headers = csrf(client)
    before = journal.path.read_bytes()
    assert client.post(ROUTE, json=body(params), headers=headers).status_code == 200
    assert journal.path.read_bytes() == before
    assert client.post(ROUTE + '?extra=1', json=body(params), headers=headers).status_code == 422
    journal.path.write_bytes(b'broken')
    result = client.post(ROUTE, json=body(params), headers=headers)
    assert result.status_code == 503
    assert result.json()['detail'] == 'observation_storage_unavailable'


def test_request_schema_matches_runtime():
    path = Path('contracts/schemas/ifc-opening-observation-batch-request-v0.1.schema.json')
    assert json.loads(path.read_bytes()) == ObservationBatchQuery.model_json_schema()
