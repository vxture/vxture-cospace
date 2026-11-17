from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import zipfile

import pytest

from packages.infrastructure.observation_integrity import validate_observation_database
from packages.infrastructure.spatial_observation_store import ObservationJournal, ObservationStorageUnavailable
from packages.infrastructure.preview_backup import backup, restore, tree
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.spatial.opening_observations import Report
from packages.spatial.scene_identity import canonical
from test_workbench_backup import runtime
from test_observation_journal import registration, report


def seeded(runtime):
    root, _ = runtime
    store = ObservationJournal(root / 'runtime', clock=lambda: '2026-11-17T00:01:00Z')
    document = registration()
    store.register(document)
    store.append(document['scope'], report(), authenticated_producer='sensor-a')
    return store, document


def resolved(store, scope):
    return store.resolve(scope, 'door-1', as_of='2026-11-17T00:05:00Z', known_at='2026-11-17T00:05:00Z')


def test_cli_rejects_logically_corrupt_observations_without_traceback(runtime):
    root, output = runtime
    store, _ = seeded(runtime)
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute('UPDATE reports SET event_id=?', ('mismatched-index',))
    result = subprocess.run(
        [sys.executable, '-m', 'experiments.scripts.workbench_backup', 'backup',
         '--root', str(root), '--output', str(output), '--actor', 'operator', '--reason', 'integrity test'],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert 'backup_rejected: observation_record_reference_invalid' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not output.exists()


def test_backup_restore_preserves_corrections_retractions_cursors_and_next_sequence(runtime):
    root, output = runtime
    store, document = seeded(runtime)
    scope = document['scope']
    original = resolved(store, scope)
    store.append(scope, report('corrected', value='open', supersedes='event-1'), authenticated_producer='sensor-a')
    corrected = resolved(store, scope)
    store.append(scope, report('retracted', value=None, operation='retract', supersedes='corrected'),
                 authenticated_producer='sensor-a')
    current = resolved(store, scope)
    audit = validate_observation_database(store.path)
    assert audit == {'registrations': 1, 'reports': 3, 'highest_sequence': 3}
    before = tree(root)
    result = backup(root, output, actor='operator', reason='observation recovery test')
    assert 'runtime/spatial-observations.sqlite3' in result['manifest']['files']
    with zipfile.ZipFile(output) as archive:
        assert archive.read('runtime/spatial-observations.sqlite3') == store.path.read_bytes()
    root.rename(root.with_name('saved-original'))
    restore(output, root, result['sha256'])
    assert tree(root) == before
    reopened = ObservationJournal(root / 'runtime', clock=lambda: '2026-11-17T00:02:00Z')
    assert resolved(reopened, scope) == current
    for value in (original, corrected):
        replay = reopened.resolve(scope, 'door-1', as_of=value['as_of'], known_at=value['known_at'],
                                  through_sequence=value['through_sequence'])
        assert replay == value
    added = reopened.append(scope, report('restored', value='open', supersedes='retracted'),
                            authenticated_producer='sensor-a')
    assert added['sequence'] == 4
    assert resolved(reopened, scope)['value'] == 'open'


@pytest.mark.parametrize('corruption', [
    'registration', 'producer', 'event', 'supersedes', 'future', 'reversed_time', 'entity',
    'orphan', 'sequence', 'trigger', 'noncanonical', 'correction_target', 'correction_time',
])
def test_sqlite_structural_health_is_not_sufficient_for_observation_backup(runtime, corruption):
    root, output = runtime
    store, document = seeded(runtime)
    value = report('second', observed_at='2026-11-17T00:00:30Z')
    store.clock = lambda: '2026-11-17T00:02:00Z'
    store.append(document['scope'], value, authenticated_producer='sensor-a')
    with closing(sqlite3.connect(store.path)) as db, db:
        if corruption == 'registration':
            db.execute('UPDATE registrations SET document=?', (b'{}',))
        elif corruption in ('producer', 'event', 'supersedes'):
            command = {'producer': 'UPDATE reports SET producer=? WHERE seq=2',
                       'event': 'UPDATE reports SET event_id=? WHERE seq=2',
                       'supersedes': 'UPDATE reports SET supersedes=? WHERE seq=2'}[corruption]
            db.execute(command, ('different',))
        elif corruption == 'future':
            db.execute('UPDATE reports SET received_at=? WHERE seq=2', ('2026-11-16T00:00:00Z',))
        elif corruption == 'reversed_time':
            db.execute('UPDATE reports SET received_at=? WHERE seq=2', ('2026-11-17T00:00:45Z',))
        elif corruption in ('entity', 'correction_target', 'correction_time', 'noncanonical'):
            if corruption == 'entity':
                value['entity_id'] = 'missing-door'
            elif corruption in ('correction_target', 'correction_time'):
                value['supersedes'] = 'missing-event' if corruption == 'correction_target' else 'event-1'
                db.execute('UPDATE reports SET supersedes=? WHERE seq=2', (value['supersedes'],))
            raw = canonical(Report.model_validate(value).model_dump())
            if corruption == 'noncanonical':
                raw = b' ' + raw
            db.execute('UPDATE reports SET document=? WHERE seq=2', (raw,))
        elif corruption == 'orphan':
            db.execute('DELETE FROM registrations')
        elif corruption == 'sequence':
            db.execute('UPDATE sqlite_sequence SET seq=0')
        else:
            db.execute('CREATE TRIGGER unexpected AFTER INSERT ON reports BEGIN SELECT 1; END')
        assert db.execute('PRAGMA quick_check').fetchall() == [('ok',)]
    with pytest.raises((ValueError, ObservationStorageUnavailable)):
        backup(root, output, actor='operator', reason='reject corrupt observation journal')
    assert not output.exists()


def test_recovery_rejects_semantic_damage_even_after_archive_repin(runtime, tmp_path):
    root, output = runtime
    store, _ = seeded(runtime)
    saved = backup(root, output, actor='operator', reason='restore validation')
    with zipfile.ZipFile(output) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    damaged = tmp_path / 'damaged.sqlite3'
    damaged.write_bytes(members['runtime/spatial-observations.sqlite3'])
    with closing(sqlite3.connect(damaged)) as db, db:
        db.execute('UPDATE reports SET producer=?', ('fake-producer',))
    payload = damaged.read_bytes()
    members['runtime/spatial-observations.sqlite3'] = payload
    manifest = saved['manifest']
    manifest['files']['runtime/spatial-observations.sqlite3'] = {
        'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    members['manifest.json'] = json.dumps(manifest).encode()
    altered = tmp_path / 'altered.zip'
    with zipfile.ZipFile(altered, 'w') as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    expected = hashlib.sha256(altered.read_bytes()).hexdigest()
    root.rename(root.with_name('source-before-restore'))
    with pytest.raises(ObservationStorageUnavailable, match='reference_invalid'):
        restore(altered, root, expected)
    assert not root.exists()


@pytest.mark.parametrize('operation', ['register', 'append'])
def test_observation_mutations_cooperate_with_backup_lock(runtime, operation):
    store, document = seeded(runtime)
    entered, finished = threading.Event(), threading.Event()
    def write():
        entered.set()
        if operation == 'register':
            store.register(document)
        else:
            store.append(document['scope'], report('waiting'), authenticated_producer='sensor-a')
        finished.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with mutation_guard(store.path.parent):
            task = pool.submit(write)
            assert entered.wait(timeout=5)
            assert not finished.wait(timeout=.1)
        task.result(timeout=5)
    assert finished.is_set()


def test_absent_journal_is_not_created_or_required_by_legacy_backup(runtime):
    root, output = runtime
    path = root / 'runtime/spatial-observations.sqlite3'
    with pytest.raises(ValueError, match='regular_file'):
        validate_observation_database(path)
    result = backup(root, output, actor='operator', reason='legacy compatibility')
    assert 'runtime/spatial-observations.sqlite3' not in result['manifest']['files']
    assert not path.exists()


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_audit_refuses_uncheckpointed_or_active_sidecars(runtime, suffix):
    store, _ = seeded(runtime)
    Path(str(store.path) + suffix).write_bytes(b'pending')
    with pytest.raises(ValueError, match='cold_database'):
        validate_observation_database(store.path)


@pytest.mark.parametrize('budget', ['MAX_SCOPES', 'MAX_TOTAL_EVENTS'])
def test_audit_budget_refuses_incomplete_validation(runtime, monkeypatch, budget):
    store, _ = seeded(runtime)
    monkeypatch.setattr('packages.infrastructure.observation_integrity.' + budget, 0)
    with pytest.raises(ValueError, match='total_budget'):
        validate_observation_database(store.path)


def test_scope_budget_and_empty_registration_are_validated(runtime, monkeypatch):
    store, document = seeded(runtime)
    other = registration()
    other['scope']['organization'] = 'org-other'
    store.register(other)
    assert validate_observation_database(store.path)['registrations'] == 2
    monkeypatch.setattr('packages.infrastructure.observation_integrity.MAX_EVENTS', 0)
    with pytest.raises(ValueError, match='scope_budget'):
        validate_observation_database(store.path)


def test_multiple_scopes_and_unused_sequence_high_water_survive_restore(runtime):
    root, output = runtime
    store, document = seeded(runtime)
    other = registration()
    other['scope']['organization'] = 'org-other'
    store.register(other)
    store.append(other['scope'], report(value='open'), authenticated_producer='sensor-a')
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute('UPDATE sqlite_sequence SET seq=100')
    before = [resolved(store, scope) for scope in (document['scope'], other['scope'])]
    assert [v['value'] for v in before] == ['closed', 'open']
    assert validate_observation_database(store.path)['reports'] == 2
    saved = backup(root, output, actor='operator', reason='multi-scope sequence retention')
    root.rename(root.with_name('old-scopes'))
    restore(output, root, saved['sha256'])
    reopened = ObservationJournal(root / 'runtime', clock=lambda: '2026-11-17T00:02:00Z')
    assert [resolved(reopened, scope) for scope in (document['scope'], other['scope'])] == before
    added = reopened.append(document['scope'], report('next'), authenticated_producer='sensor-a')
    assert added['sequence'] == 101
