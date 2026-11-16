from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3

import pytest

from packages.infrastructure.spatial_observation_store import ObservationJournal


def registration():
    return {'profile': 'cospace.opening-observation-registration/0.1',
            'scope': {'issuer': 'https://platform.example', 'organization': 'org-1', 'workspace': 'workspace-1',
                      'space_id': 'space-' + '1' * 16, 'catalog_sha256': 'a' * 64},
            'data_kind': 'ifc_design_candidate', 'subjects': [{'entity_id': 'door-1', 'role': 'door'}],
            'producers': ['sensor-a', 'sensor-b']}


def report(identity='event-1', **changes):
    return {'profile': 'cospace.opening-observation-report/0.1', 'event_id': identity,
            'producer': 'sensor-a', 'entity_id': 'door-1', 'value': 'closed',
            'observed_at': '2026-11-17T00:00:00Z', 'valid_until': '2026-11-17T00:10:00Z',
            'evidence_sha256': ['b' * 64], **changes}


@pytest.fixture
def journal(tmp_path):
    clock = ['2026-11-17T00:01:00Z']
    store = ObservationJournal(tmp_path, clock=lambda: clock[0])
    doc = registration()
    store.register(doc)
    return store, doc['scope'], clock


def append(env, value):
    store, scope, _ = env
    return store.append(scope, value, authenticated_producer=value['producer'])


def resolve(env, **changes):
    store, scope, _ = env
    return store.resolve(scope, 'door-1', as_of='2026-11-17T00:05:00Z',
                         **({'known_at': '2026-11-17T00:05:00Z'} | changes))


def test_restart_idempotency_and_event_immutability(journal):
    first = append(journal, report())
    journal[2][0] = '2026-11-17T00:02:00Z'
    assert append(journal, report()) == first
    reopened = ObservationJournal(journal[0].path.parent)
    state = reopened.resolve(journal[1], 'door-1', as_of='2026-11-17T00:05:00Z', known_at=journal[2][0])
    assert state['status'] == 'reported' and state['value'] == 'closed'
    assert state['active'][0]['received_at'] == '2026-11-17T00:01:00Z'
    assert state['evidence_content_verified'] is state['real_release_ready'] is False
    with pytest.raises(ValueError, match='event_immutable'):
        append(journal, report(value='open'))


def test_scope_and_producer_are_independent_boundaries(journal):
    store, scope, _ = journal
    with pytest.raises(ValueError, match='producer_mismatch'):
        store.append(scope, report(), authenticated_producer='sensor-b')
    for change in [{'organization': 'org-2'}, {'workspace': 'workspace-2'},
                   {'space_id': 'space-' + '2' * 16}, {'catalog_sha256': 'c' * 64}]:
        with pytest.raises(ValueError, match='scope_not_registered'):
            store.append(scope | change, report(), authenticated_producer='sensor-a')
    for change in [{'producer': 'unknown'}, {'entity_id': 'other-door'}]:
        with pytest.raises(ValueError, match='reference_not_registered'):
            append(journal, report(**change))
    with pytest.raises(ValueError, match='subject_not_registered'):
        store.resolve(scope, 'other-door', as_of=journal[2][0], known_at=journal[2][0])


def test_registration_is_immutable(journal):
    doc = registration()
    assert journal[0].register(doc) == journal[0].register(doc)
    doc['producers'].append('sensor-c')
    with pytest.raises(ValueError, match='registration_immutable'):
        journal[0].register(doc)


def test_correction_is_historical_and_pinned_replay_does_not_change(journal):
    original = append(journal, report())
    before = resolve(journal)
    journal[2][0] = '2026-11-17T00:03:00Z'
    correction = append(journal, report('correction-1', value='open', supersedes='event-1'))
    after = resolve(journal)
    assert after['value'] == 'open'
    assert after['active'][0]['sequence'] == correction['sequence']
    assert resolve(journal, known_at='2026-11-17T00:02:00Z')['value'] == 'closed'
    assert resolve(journal, through_sequence=original['sequence']) == before
    assert after['cursor'] != before['cursor']
    with sqlite3.connect(journal[0].path) as db:
        assert db.execute('SELECT COUNT(*) FROM reports').fetchone()[0] == 2
    for changes in [{'supersedes': 'missing'}, {'supersedes': 'event-1'},
                    {'supersedes': 'correction-1', 'observed_at': '2026-11-17T00:00:01Z'},
                    {'supersedes': 'correction-1', 'producer': 'sensor-b'}]:
        with pytest.raises(ValueError, match='correction_binding'):
            append(journal, report('bad-correction', **changes))
    append(journal, report('correction-2', supersedes='correction-1'))
    assert resolve(journal)['value'] == 'closed'


def test_late_older_observation_expiry_and_conflict(journal):
    append(journal, report('new', value='open', observed_at='2026-11-17T00:00:30Z',
                           valid_until='2026-11-17T00:04:00Z'))
    journal[2][0] = '2026-11-17T00:02:00Z'
    append(journal, report('late-old'))
    assert resolve(journal)['status'] == 'expired'
    append(journal, report('other-source', producer='sensor-b', value='unknown'))
    assert resolve(journal)['status'] == 'unknown'
    append(journal, report('other-conflict', producer='sensor-b', value='open'))
    assert resolve(journal)['status'] == 'conflict'
    assert resolve(journal, known_at='2026-11-17T00:00:00Z')['status'] == 'unavailable'


def test_equal_time_same_source_conflict_requires_explicit_correction(journal):
    append(journal, report())
    append(journal, report('second', value='open'))
    assert resolve(journal)['status'] == 'conflict'


def test_concurrent_retries_insert_once(journal):
    with ThreadPoolExecutor(max_workers=4) as workers:
        rows = list(workers.map(lambda _: append(journal, report()), range(8)))
    assert all(row == rows[0] for row in rows)
    assert len(resolve(journal)['active']) == 1


def test_clock_and_input_guards(journal, monkeypatch):
    store, scope, clock = journal
    append(journal, report())
    clock[0] = '2026-11-17T00:00:30Z'
    with pytest.raises(ValueError, match='clock_reversed'):
        append(journal, report('second'))
    clock[0] = '2026-11-17T00:02:00Z'
    with pytest.raises(ValueError, match='future_report'):
        append(journal, report('future', observed_at='2026-11-17T00:03:00Z'))
    for invalid in [True, -1, 1.5, 999]:
        with pytest.raises(ValueError, match='sequence'):
            resolve(journal, through_sequence=invalid)
    for changes in [{'valid_until': '2026-11-17T00:00:00Z'}, {'received_at': clock[0]},
                    {'value': 'traversable'}, {'evidence_sha256': []}]:
        with pytest.raises(ValueError):
            append(journal, report('invalid', **changes))
    monkeypatch.setattr('packages.infrastructure.spatial_observation_store.MAX_EVENTS', 1)
    with pytest.raises(ValueError, match='write_budget'):
        append(journal, report('full'))


def test_no_implicit_registration_or_creation(tmp_path):
    store = ObservationJournal(tmp_path / 'missing')
    with pytest.raises(sqlite3.OperationalError):
        store.append(registration()['scope'], report(), authenticated_producer='sensor-a')
    assert not store.path.exists()
    bad = deepcopy(registration())
    bad['subjects'].append(bad['subjects'][0])
    with pytest.raises(ValueError, match='duplicates'):
        store.register(bad)


def test_failure_rolls_back_and_read_budget_fails_explicitly(journal, monkeypatch):
    append(journal, report())
    with pytest.raises(ValueError, match='correction_binding'):
        append(journal, report('invalid', supersedes='missing'))
    with sqlite3.connect(journal[0].path) as db:
        assert db.execute('SELECT COUNT(*) FROM reports').fetchone()[0] == 1
    monkeypatch.setattr('packages.infrastructure.spatial_observation_store.MAX_EVENTS', 0)
    with pytest.raises(ValueError, match='read_budget'):
        resolve(journal)


def test_retraction_is_explicit_historical_and_never_revives_older_state(journal):
    append(journal, report('older', observed_at='2026-11-16T23:59:00Z'))
    append(journal, report())
    journal[2][0] = '2026-11-17T00:03:00Z'
    append(journal, report('retract-1', operation='retract', value=None, supersedes='event-1'))
    state = resolve(journal)
    assert state['status'] == 'retracted' and state['value'] is None and not state['active']
    assert len(state['retracted']) == 1
    assert resolve(journal, known_at='2026-11-17T00:02:00Z')['status'] == 'reported'
    with pytest.raises(ValueError, match='retraction_requires'):
        append(journal, report('bad', operation='retract', value=None))
    with pytest.raises(ValueError, match='assertion_requires'):
        append(journal, report('bad', value=None))
    append(journal, report('reinstate', supersedes='retract-1', value='open'))
    assert resolve(journal)['value'] == 'open'
