"""Read-only failure evidence must never become cleanup or gate authority."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from experiments.scripts.validity_audit import ValidityAudit
from packages.data.imports import canonical, sha
from tests.test_validity_probe import gate, proofs, decision


def inventory(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def marker(gate, token, kind='status_snapshot', name=None):
    path = gate['store'].pending / (name or ('a' * 32 + '.json'))
    path.write_bytes(canonical({'kind': kind, 'token_sha256': sha(token.encode('ascii'))}))
    return path


def test_missing_store_is_not_created(tmp_path):
    root = tmp_path / 'missing'
    result = ValidityAudit(root).scan()
    assert not result['complete'] and not root.exists()
    assert not result['recovery_authorized']


def test_clean_report_preserves_bytes_and_does_not_authorize(gate):
    root = gate['store'].root
    before = inventory(root)
    report = ValidityAudit(root).scan()
    assert report['complete'] and not report['needs_attention']
    assert report['retained_proof_count'] == 3
    assert not report['authorized'] and not report['proofs_verified']
    assert inventory(root) == before


def test_digest_matches_retained_message_without_releasing_gate(gate):
    status, _ = proofs(gate)
    path = marker(gate, status)
    before = inventory(gate['store'].root)
    result = ValidityAudit(gate['store'].root).scan()
    assert result['pending'][0]['classification'] == 'retained_digest_match'
    assert not result['cleanup_authorized'] and result['needs_attention']
    assert path.exists() and inventory(gate['store'].root) == before
    assert decision(gate)['reason'] == 'storage_error'


def test_failed_commit_message_is_not_claimed_uncommitted(gate, monkeypatch):
    def fail():
        raise sqlite3.OperationalError('injected')
    monkeypatch.setattr(gate['store'], '_before_commit', fail)
    revoked, _ = proofs(gate, sequence=2, state='revoked')
    with pytest.raises(sqlite3.OperationalError):
        gate['store'].accept(gate['binding'], revoked, 'status_snapshot')
    result = ValidityAudit(gate['store'].root).scan()
    assert result['complete']
    assert result['pending'][0]['classification'] == 'not_in_retained_snapshot'
    assert not result['recovery_authorized']


@pytest.mark.parametrize('raw,name', [(b'{', None), (b'x' * 1025, None),
    (b'{}', 'unexpected'), (b'{"kind":"x","kind":"y"}', None)])
def test_unknown_malformed_oversized_entries_retained(gate, raw, name):
    path = gate['store'].pending / (name or ('b' * 32 + '.json'))
    path.write_bytes(raw)
    result = ValidityAudit(gate['store'].root).scan()
    assert not result['complete'] and result['needs_attention']
    assert path.read_bytes() == raw and not result['cleanup_authorized']


def test_database_corruption_does_not_hide_pending(gate):
    status, _ = proofs(gate)
    marker(gate, status)
    gate['store'].path.write_bytes(b'broken database')
    before = inventory(gate['store'].root)
    result = ValidityAudit(gate['store'].root).scan()
    assert not result['complete'] and not result['database_observed']
    assert result['pending'][0]['classification'] == 'database_unknown'
    assert inventory(gate['store'].root) == before


def test_entry_and_row_limits_do_not_suggest_recovery(gate):
    status, _ = proofs(gate)
    marker(gate, status)
    marker(gate, status, name='c' * 32 + '.json')
    assert not ValidityAudit(gate['store'].root).scan(1)['complete']
    with sqlite3.connect(gate['store'].path) as db:
        db.execute('INSERT INTO states SELECT ?,binding,content,status,grant_proof,revoked FROM states', ('0' * 64,))
    result = ValidityAudit(gate['store'].root).scan(1)
    assert not result['complete'] and not result['database_observed']
    assert not result['recovery_authorized']


def test_readonly_sql_and_cli_exit_status(gate, monkeypatch):
    import experiments.scripts.validity_audit as module
    original = sqlite3.connect
    def connect(database_uri, **kwargs):
        assert database_uri.endswith('?mode=ro') and kwargs['uri']
        db = original(database_uri, **kwargs)
        def authorize(action, *args):
            return sqlite3.SQLITE_DENY if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE,
                sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE) else sqlite3.SQLITE_OK
        db.set_authorizer(authorize)
        return db
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    assert ValidityAudit(gate['store'].root).scan()['complete']
    command = [sys.executable, '-m', 'experiments.scripts.validity_audit', '--root', str(gate['store'].root)]
    clean = subprocess.run(command, capture_output=True, text=True)
    assert clean.returncode == 0 and not json.loads(clean.stdout)['authorized']
    status, _ = proofs(gate)
    marker(gate, status)
    dirty = subprocess.run(command, capture_output=True, text=True)
    assert dirty.returncode == 2 and json.loads(dirty.stdout)['needs_attention']


def test_pending_directory_is_not_followed(gate, monkeypatch):
    import experiments.scripts.validity_audit as module
    original = module.safe_path
    def reject(path):
        if Path(path) == gate['store'].pending:
            raise ValueError('unsafe reparse point')
        return original(path)
    monkeypatch.setattr(module, 'safe_path', reject)
    result = ValidityAudit(gate['store'].root).scan()
    assert not result['complete'] and result['findings'][-1]['code'] == 'pending_inventory_incomplete'


def test_superseded_committed_status_can_also_be_absent_from_snapshot(gate):
    old, _ = proofs(gate, sequence=2)
    gate['store'].accept(gate['binding'], old, 'status_snapshot')
    marker(gate, old)
    newer, _ = proofs(gate, sequence=3)
    gate['store'].accept(gate['binding'], newer, 'status_snapshot')
    result = ValidityAudit(gate['store'].root).scan()
    assert result['pending'][0]['classification'] == 'not_in_retained_snapshot'
    assert not result['recovery_authorized']


def test_audit_during_live_write_never_claims_abandoned_owner(gate):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    reached, release = threading.Event(), threading.Event()
    def barrier():
        reached.set()
        assert release.wait(10)
    gate['store']._before_commit = barrier
    status, _ = proofs(gate, sequence=2)
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(gate['store'].accept, gate['binding'], status, 'status_snapshot')
        try:
            assert reached.wait(10)
            result = ValidityAudit(gate['store'].root).scan()
            assert result['complete'] and result['needs_attention']
            assert result['pending'][0]['classification'] == 'not_in_retained_snapshot'
            assert 'ownership unknown' in result['observation']
            assert not result['cleanup_authorized']
        finally:
            release.set()
        task.result(timeout=10)
