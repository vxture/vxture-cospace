from contextlib import closing
import json
import sqlite3

import pytest

from packages.infrastructure.spatial_observation_store import ObservationStorageUnavailable
from packages.spatial.opening_observations import Report, scope_key
from packages.spatial.scene_identity import canonical
from test_ifc_observation_http import registered_door
from test_ifc_workspace import ifc_secured
from test_platform_business import secured
from test_platform_login import runtime
from test_observation_journal import report, registration
from test_observation_batch import pair, read, csrf, body, WHEN


def damage(journal, scope, kind):
    # Second report allows receive-time and correction-chain checks to be exercised.
    second = report('second', entity_id='wall', observed_at='2026-11-17T00:00:30Z')
    journal.clock = lambda: '2026-11-17T00:02:00Z'
    journal.append(scope, second, authenticated_producer='sensor-a')
    with closing(sqlite3.connect(journal.path)) as db, db:
        key = scope_key(scope)
        if kind in ('index_producer', 'index_event', 'index_supersedes'):
            sql = {'index_producer': 'UPDATE reports SET producer=? WHERE scope=? AND event_id=?',
                   'index_event': 'UPDATE reports SET event_id=? WHERE scope=? AND event_id=?',
                   'index_supersedes': 'UPDATE reports SET supersedes=? WHERE scope=? AND event_id=?'}[kind]
            db.execute(sql, ('wrong', key, 'second'))
        elif kind in ('future', 'clock_reversed'):
            received = '2026-11-16T00:00:00Z' if kind == 'future' else '2026-11-17T00:00:45Z'
            db.execute('UPDATE reports SET received_at=? WHERE scope=? AND event_id=?', (received, key, 'second'))
        elif kind in ('registration_canonical', 'registration_duplicate_key'):
            raw = db.execute('SELECT document FROM registrations WHERE scope=?', (key,)).fetchone()[0]
            raw = b' ' + raw if kind == 'registration_canonical' else b'{"data_kind":"ifc_design_candidate",' + raw[1:]
            db.execute('UPDATE registrations SET document=? WHERE scope=?', (raw, key))
        else:
            if kind == 'unknown_producer':
                second['producer'] = 'unknown'
                db.execute('UPDATE reports SET producer=? WHERE scope=? AND event_id=?', ('unknown', key, 'second'))
            elif kind == 'unknown_subject':
                second['entity_id'] = 'not-registered'
            elif kind in ('missing_correction', 'wrong_correction_time'):
                second['supersedes'] = 'missing' if kind == 'missing_correction' else 'event-1'
                db.execute('UPDATE reports SET supersedes=? WHERE scope=? AND event_id=?', (second['supersedes'], key, 'second'))
            raw = canonical(Report.model_validate(second).model_dump())
            if kind == 'record_canonical':
                raw = b' ' + raw
            elif kind == 'record_duplicate_key':
                raw = b'{"value":"closed",' + raw[1:]
            db.execute('UPDATE reports SET document=? WHERE scope=? AND event_id=?', (raw, key, 'second'))
        assert db.execute('PRAGMA quick_check').fetchall() == [('ok',)]


@pytest.mark.parametrize('kind', [
    'index_producer', 'index_event', 'index_supersedes', 'future', 'clock_reversed',
    'unknown_producer', 'unknown_subject', 'missing_correction', 'wrong_correction_time',
    'record_canonical', 'record_duplicate_key', 'registration_canonical', 'registration_duplicate_key',
])
def test_corruption_is_503_for_single_batch_and_pinned_empty_prefix(registered_door, kind):
    client, journal, _, params, scope, _ = registered_door
    damage(journal, scope, kind)
    before = journal.path.read_bytes()
    headers = csrf(client)
    single = client.get('/api/scene-ifc/opening-observation', params=params)
    batch = client.post('/api/scene-ifc/opening-observations', json=body(params), headers=headers)
    replay = {'as_of': WHEN, 'known_at': WHEN, 'through_sequence': '0'}
    historical = client.get('/api/scene-ifc/opening-observation', params=params | replay)
    for response in (single, batch, historical):
        assert response.status_code == 503, response.text
        assert response.json()['detail'] == 'observation_storage_unavailable'
        assert response.headers['cache-control'] == 'no-store'
        assert 'wrong' not in response.text
    assert journal.path.read_bytes() == before


def test_corrupted_other_subject_cannot_be_skipped_by_one_object_query(pair):
    store, scope = pair
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute('UPDATE reports SET event_id=? WHERE event_id=?', ('wrong', 'second'))
    with pytest.raises(ObservationStorageUnavailable, match='reference_invalid'):
        store.resolve(scope, 'door-1', as_of=WHEN, known_at=WHEN)


def test_unrelated_scope_is_not_scanned_or_exposed(pair):
    store, _ = pair
    before = read(pair)
    other = registration()
    other['scope']['organization'] = 'other-org'
    store.register(other)
    store.append(other['scope'], report(), authenticated_producer='sensor-a')
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute('UPDATE reports SET document=? WHERE scope=?', (b'broken', scope_key(other['scope'])))
    assert read(pair) == before
    with pytest.raises(ObservationStorageUnavailable):
        store.resolve(other['scope'], 'door-1', as_of=WHEN, known_at=WHEN)


@pytest.mark.parametrize('operation', ['retry', 'correction'])
def test_targeted_write_refuses_corrupted_index_without_appending(pair, operation):
    store, scope = pair
    with closing(sqlite3.connect(store.path)) as db, db:
        raw = canonical(Report.model_validate(report(value='open')).model_dump())
        # Report bytes disagree with the indexed producer, while remaining schema-valid.
        changed = json.loads(raw) | {'producer': 'sensor-b'}
        db.execute('UPDATE reports SET document=? WHERE event_id=?', (canonical(changed), 'event-1'))
    before = store.path.read_bytes()
    query = report() if operation == 'retry' else report('corrected', supersedes='event-1')
    with pytest.raises(ObservationStorageUnavailable, match='index_invalid'):
        store.append(scope, query, authenticated_producer='sensor-a')
    assert store.path.read_bytes() == before
