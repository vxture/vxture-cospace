"""Unified observations must remain read-only and separate from runtime permission."""
import copy
import json
import os
import subprocess
import sys

import pytest

from experiments.scripts.delivery_audit import DeliveryAudit
from tests.test_recovery_session import consumer
from tests.test_recovery_state import recovery, pending, plan
from tests.test_validity_probe import gate, proofs
from tests.test_recovery_journal import connection

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows synthetic journal fixture')


def scan(f):
    return DeliveryAudit(f['files'].root, f['journal'].root).scan(f['binding'])


def test_matching_report_preserves_file_bytes_without_permission(consumer):
    roots = [consumer['files'].root, consumer['journal'].root]
    def snapshot():
        return {(str(root), p.relative_to(root).as_posix()): p.read_bytes() for root in roots for p in root.rglob('*') if p.is_file()}
    before = snapshot()
    report = scan(consumer)
    assert report['complete'] and not report['needs_attention']
    assert report['observed']['binding_match'] and snapshot() == before
    assert report['validity'] == 'not_evaluated' and not report['authorized'] and not report['repair_authorized']


@pytest.mark.parametrize('field', ['package_sha256', 'scope_sha256', 'release_id'])
def test_binding_mismatch_localizes_both_components(consumer, field):
    binding = copy.deepcopy(consumer['binding'])
    binding[field] = 'f' * 64
    report = DeliveryAudit(consumer['files'].root, consumer['journal'].root).scan(binding)
    codes = {f['code'] for f in report['findings']}
    assert {'file_binding_mismatch', 'journal_binding_missing_or_ambiguous'} <= codes
    assert not report['observed']['binding_match']


def test_pending_recovery_and_missing_grant_have_actions(consumer):
    pending(consumer, proofs(consumer, sequence=2)[0])
    report = scan(consumer)
    assert report['needs_attention'] and report['components']['journal']['pending']
    _, proposed = plan(consumer)
    assert scan(consumer)['components']['journal']['runs'][0]['phase'] == 'planned'
    consumer['journal'].commit_recovery(proposed)
    final = scan(consumer)
    assert 'proof_fields_missing' in {f['code'] for f in final['findings']}
    assert all(f['next_action'] for f in final['findings'])


def test_file_corruption_keeps_journal_diagnostics(consumer):
    path = consumer['files'].root / 'packages' / consumer['binding']['package_sha256'] / 'coverage.json'
    path.write_bytes(b'bad coverage')
    result = scan(consumer)
    assert result['needs_attention'] and result['components']['journal']['complete']
    assert 'file_binding_unavailable' in {f['code'] for f in result['findings']}


def test_missing_stores_never_created(consumer, tmp_path):
    files, journal = tmp_path / 'absent-files', tmp_path / 'absent-journal'
    result = DeliveryAudit(files, journal).scan(consumer['binding'])
    assert not result['complete'] and not files.exists() and not journal.exists()


def test_revoked_status_fields_are_never_reported_as_runtime_approval(consumer):
    import uuid
    consumer['journal'].accept(consumer['binding'], proofs(consumer, sequence=2, state='revoked')[0],
                                'status_snapshot', intent_id=str(uuid.uuid4()))
    report = scan(consumer)
    assert report['observed']['journal_status'] == 'proof_fields_missing'
    assert report['validity'] == 'not_evaluated' and not report['robot_ready']


def test_changed_observation_detected(consumer, monkeypatch):
    from experiments.scripts.delivery_audit import RecoveryAudit
    original = RecoveryAudit.scan
    def altered(self, limit=100):
        report = original(self, limit)
        report['control']['generation'] += 1
        return report
    monkeypatch.setattr(RecoveryAudit, 'scan', altered)
    report = scan(consumer)
    assert not report['complete']
    assert 'journal_observation_changed' in {f['code'] for f in report['findings']}


def test_cli_readonly_and_exit_codes(consumer, tmp_path):
    binding = tmp_path / 'binding.json'
    binding.write_text(json.dumps(consumer['binding']))
    command = [sys.executable, '-m', 'experiments.scripts.delivery_audit', '--files', str(consumer['files'].root),
               '--journal', str(consumer['journal'].root), '--binding', str(binding)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0 and not json.loads(result.stdout)['authorized']
    pending(consumer)
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 2 and json.loads(result.stdout)['needs_attention']


def test_readonly_sql_authorizer_and_limits(consumer, monkeypatch):
    import sqlite3
    import experiments.scripts.delivery_audit as module
    original = sqlite3.connect
    def connect(database, **kwargs):
        assert database.endswith('?mode=ro') and kwargs['uri']
        db = original(database, **kwargs)
        db.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in
            (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE) else sqlite3.SQLITE_OK)
        return db
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    assert scan(consumer)['complete']
    assert not DeliveryAudit(consumer['files'].root, consumer['journal'].root).scan(consumer['binding'], 1)['complete']


def test_generation_identifies_each_observation_without_rewriting_sources(consumer):
    from packages.data.delivery_report import validate_generation
    roots = [consumer['files'].root, consumer['journal'].root]
    before = {str(p): p.read_bytes() for root in roots for p in root.rglob('*') if p.is_file()}
    first, second = scan(consumer), scan(consumer)
    assert first['schema_version'] == 'cospace.test-delivery-audit/0.2'
    assert first['generation']['report_id'] != second['generation']['report_id']
    assert first['generation']['payload_sha256'] == second['generation']['payload_sha256']
    assert first['generation']['sources']['journal']['control'] == first['components']['journal']['control']
    validate_generation(first)
    validate_generation(second)
    assert before == {str(p): p.read_bytes() for root in roots for p in root.rglob('*') if p.is_file()}


def test_generation_clock_regression_is_recorded_not_repaired(consumer, monkeypatch):
    from datetime import datetime, timezone
    import experiments.scripts.delivery_audit as module
    clocks = iter([datetime(2026, 10, 27, 0, 0, 2, tzinfo=timezone.utc),
                   datetime(2026, 10, 27, 0, 0, 1, tzinfo=timezone.utc)])
    class Clock:
        @staticmethod
        def now(zone): return next(clocks)
    monkeypatch.setattr(module, 'datetime', Clock)
    monotonic = iter([2_000_000_000, 2_100_000_000])
    monkeypatch.setattr(module.time, 'monotonic_ns', lambda: next(monotonic))
    report = scan(consumer)
    assert report['generation']['interval']['wall_end_before_start']
    assert report['generation']['interval']['elapsed_ms'] == 100
    assert report['validity'] == 'not_evaluated' and not report['authorized']


def test_explicit_generate_cli_saves_outside_observed_roots(consumer, tmp_path):
    from packages.infrastructure.delivery_reports import ReportArchive
    binding = tmp_path / 'archive-binding.json'
    binding.write_text(json.dumps(consumer['binding']), encoding='utf-8')
    output = tmp_path / 'archive-output'
    roots = [consumer['files'].root, consumer['journal'].root]
    before = {str(p): p.read_bytes() for root in roots for p in root.rglob('*') if p.is_file()}
    command = [sys.executable, '-m', 'experiments.scripts.delivery_generate', '--files', str(roots[0]),
               '--journal', str(roots[1]), '--binding', str(binding), '--output', str(output)]
    result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    report = ReportArchive(output).read(consumer['binding']['scene_id'], consumer['binding']['release_id'], receipt['report_key'])
    assert report['report']['generation'] and not report['report']['authorized']
    assert before == {str(p): p.read_bytes() for root in roots for p in root.rglob('*') if p.is_file()}
