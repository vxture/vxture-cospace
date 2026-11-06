"""J4 file snapshots, generation fences and read-only journal metadata."""
import copy
import os
import sqlite3
import json
import subprocess
import sys

import pytest

from experiments.scripts.recovery_session import RecoverySession
from experiments.scripts.recovery_audit import RecoveryAudit
from experiments.scripts.validity_probe import GateError, IntervalClock
from packages.infrastructure.agent_files import FilePackages
from tests.test_recovery_state import recovery, pending, plan, reopen
from tests.test_validity_probe import gate, proofs
from tests.test_recovery_journal import connection

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows recovery lock')


@pytest.fixture
def consumer(recovery, tmp_path):
    files = FilePackages(tmp_path / 'files')
    installed = files.install('examples/agent-runtime', 'examples/indoor-spatial')
    files.activate(recovery['binding']['scene_id'], installed['package_sha256'], 0)
    recovery['files'] = files
    return recovery


def session(fixture, ledger=None, clock=None):
    return RecoverySession(fixture['files'], fixture['binding']['scene_id'],
                           ledger or fixture['journal'], fixture['binding'], clock or fixture['clock'])


def test_old_session_fenced_after_begin_and_completion_fresh_session_works(consumer):
    old = session(consumer)
    first = old.query([1, 0, 1])
    assert first['state'] == 'observed_free' and first['session_generation'] == 1
    pending(consumer, proofs(consumer)[0])
    with pytest.raises(GateError, match='storage_error|recovery_required'):
        old.query([1, 0, 1])
    rid, proposed = plan(consumer)
    with pytest.raises(GateError, match='stale_generation'):
        old.query([1, 0, 1])
    with pytest.raises(GateError, match='session_not_allowed'):
        session(consumer)
    consumer['journal'].commit_recovery(proposed)
    with pytest.raises(GateError, match='stale_generation'):
        old.query([1, 0, 1])
    consumer['journal'] = reopen(consumer)
    new = session(consumer, clock=IntervalClock(lambda: ('fresh', 0), ('fresh', 0, 110, 110)))
    after = new.query([1, 0, 1])
    assert after['state'] == first['state'] and after['session_generation'] == 3
    assert after['gate']['deadline'] == first['gate']['deadline']
    assert not after['authorized'] and not after['robot_ready']
    old.close()
    new.close()
    with pytest.raises(GateError, match='session_closed'):
        new.query([1, 0, 1])


def test_recovered_revocation_never_reopens_spatial_session(consumer):
    old = session(consumer)
    pending(consumer)
    _, proposed = plan(consumer)
    consumer['journal'].commit_recovery(proposed)
    consumer['journal'] = reopen(consumer)
    with pytest.raises(GateError, match='session_not_allowed'):
        session(consumer)
    with pytest.raises(GateError, match='stale_generation'):
        old.query([1, 0, 1])
    old.close()


def test_expired_or_missing_anchor_cannot_open_after_recovery(consumer):
    pending(consumer, proofs(consumer)[0])
    _, proposed = plan(consumer)
    consumer['journal'].commit_recovery(proposed)
    consumer['journal'] = reopen(consumer)
    for clock in (IntervalClock(lambda: ('x', 0)), IntervalClock(lambda: ('x', 0), ('x', 0, 130, 130))):
        with pytest.raises(GateError, match='session_not_allowed'):
            session(consumer, clock=clock)


@pytest.mark.parametrize('field', ['scene_id', 'scope_sha256', 'truth_sha256', 'package_sha256'])
def test_wrong_file_binding_rejected(consumer, field):
    binding = copy.deepcopy(consumer['binding'])
    binding[field] = 'other' if field == 'scene_id' else 'f' * 64
    with pytest.raises(GateError, match='scene_binding_mismatch|binding_conflict|active_package_mismatch'):
        RecoverySession(consumer['files'], consumer['binding']['scene_id'], consumer['journal'], binding, consumer['clock'])


def test_active_revision_switch_keeps_pinned_session(consumer):
    old = session(consumer)
    # Same content reactivation advances active revision without changing pinned session.
    files = consumer['files']
    files.activate(consumer['binding']['scene_id'], consumer['binding']['package_sha256'], 1)
    assert old.query([1, 0, 1])['revision'] == 1
    fresh = session(consumer)
    assert fresh.query([1, 0, 1])['revision'] == 2
    assert old.query([1, 0, 1])['state'] == fresh.query([1, 0, 1])['state']
    old.close()
    fresh.close()


def test_actual_content_switch_preserves_old_snapshot_and_requires_new_binding(consumer, tmp_path):
    from scripts.build_sample import build as build_source
    from packages.views.agent.runtime import build
    old = session(consumer)
    def mutate(name, document):
        if name == 'coverage.json':
            document['regions'][0]['state'] = 'occupied'
    source, package = tmp_path / 'source2', tmp_path / 'package2'
    build_source(source, spatial=True, mutate=mutate)
    changed = build(source, package)
    consumer['files'].install(package, source)
    consumer['files'].activate(consumer['binding']['scene_id'], changed['package_sha256'], 1)
    assert old.query([1, 0, 1])['state'] == 'observed_free'
    with pytest.raises(GateError, match='active_package_mismatch'):
        session(consumer)
    # New binding has no content/status/grant proof, so cannot open a gated new session.
    manifest = json.loads((package / 'agent-package.json').read_text())
    from packages.data.imports import canonical, sha
    binding = {k: manifest['source'][k] for k in consumer['binding'] if k in manifest['source']}
    binding.update(package_sha256=changed['package_sha256'], profile=manifest['profile'], scope_sha256=sha(canonical(manifest['scope'])))
    with pytest.raises(GateError, match='session_not_allowed'):
        RecoverySession(consumer['files'], binding['scene_id'], consumer['journal'], binding, consumer['clock'])
    old.close()


def test_audit_pending_planned_reconciled_preserves_all_bytes(consumer):
    root = consumer['journal'].root
    def snapshot():
        return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    def report():
        before = snapshot()
        result = RecoveryAudit(root).scan()
        assert snapshot() == before
        assert result['complete'] and not result['proofs_verified'] and not result['recovery_authorized']
        return result
    assert not report()['needs_attention']
    pending(consumer, proofs(consumer)[0])
    assert len(report()['pending']) == 1
    rid, proposed = plan(consumer)
    assert report()['runs'][0]['phase'] == 'planned'
    consumer['journal'].commit_recovery(proposed)
    final = report()
    assert not final['needs_attention'] and final['runs'][0]['phase'] == 'reconciled'


def test_audit_missing_corrupt_and_limits_never_initialize(consumer, tmp_path):
    root = tmp_path / 'absent'
    assert not RecoveryAudit(root).scan()['complete'] and not root.exists()
    assert not RecoveryAudit(consumer['journal'].root).scan(1)['complete']
    with connection(consumer['journal'].path) as db:
        db.execute('UPDATE control SET mode=?', ('recovering',))
    report = RecoveryAudit(consumer['journal'].root).scan()
    assert not report['complete'] and report['findings'][0]['code'] == 'recovery_control_inconsistent'


def test_audit_uses_readonly_connection(consumer, monkeypatch):
    import experiments.scripts.recovery_audit as module
    original = sqlite3.connect
    def connect(database, **kwargs):
        assert database.endswith('?mode=ro') and kwargs['uri']
        db = original(database, **kwargs)
        db.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in
            (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE) else sqlite3.SQLITE_OK)
        return db
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    assert RecoveryAudit(consumer['journal'].root).scan()['complete']


def test_audit_cli_clean_pending_exit_codes_and_no_token_body(consumer):
    command = [sys.executable, '-m', 'experiments.scripts.recovery_audit', '--root', str(consumer['journal'].root)]
    clean = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert clean.returncode == 0 and json.loads(clean.stdout)['complete']
    pending(consumer)
    blocked = subprocess.run(command, capture_output=True, text=True, timeout=10)
    report = json.loads(blocked.stdout)
    assert blocked.returncode == 2 and report['needs_attention']
    assert 'token' not in report['pending'][0] and not report['recovery_authorized']


def test_audit_bad_database_retains_incomplete_state(consumer):
    consumer['journal'].path.write_bytes(b'bad database')
    result = RecoveryAudit(consumer['journal'].root).scan()
    assert not result['complete'] and result['needs_attention']


def test_adapter_rejects_v1_ledger(consumer):
    with pytest.raises(GateError, match='recovery_store_required'):
        session(consumer, ledger=consumer['store'])
