"""R1c read-only diagnostics, bounded inventory and CLI failure reporting."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest
from packages.infrastructure.agent_audit import PackageAudit
from packages.infrastructure.agent_files import FilePackages
from packages.views.agent.runtime import build, PackageError
from scripts.build_sample import build as build_source


@pytest.fixture
def store(tmp_path):
    source, package = tmp_path / 'source', tmp_path / 'package'
    build_source(source, spatial=True)
    report = build(source, package)
    local = FilePackages(tmp_path / 'store')
    installed = local.install(package, source)
    local.activate(report['source']['scene_id'], report['package_sha256'], 0)
    return local, source, package, installed


def snapshot(root):
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def codes(report):
    return {f['code'] for f in report['findings']}


def test_clean_audit_no_writes_or_source_needed(store):
    local, source, package, _ = store
    shutil.rmtree(source)
    shutil.rmtree(package)
    before = snapshot(local.root)
    report = PackageAudit(local.root).scan()
    assert report['passed'] and report['complete'] and report['integrity_healthy']
    assert report['active'][0]['integrity'] == 'verified'
    assert not report['robot_ready']
    assert snapshot(local.root) == before


@pytest.mark.parametrize('change', ['missing', 'changed', 'bad_metadata'])
def test_corrupt_package_and_active_reported_without_repair(store, change):
    local, _, _, installed = store
    member = local.root / 'packages' / installed['package_sha256'] / 'coverage.json'
    if change == 'missing':
        member.unlink()
    elif change == 'changed':
        member.write_bytes(b'{}')
    else:
        with sqlite3.connect(local.path) as db:
            db.execute('UPDATE packages SET manifest=?', (b'{}',))
    before = snapshot(local.root)
    report = PackageAudit(local.root).scan()
    assert not report['passed'] and not report['integrity_healthy']
    assert {'package_unreadable', 'active_unusable'} <= codes(report)
    assert snapshot(local.root) == before


def test_orphan_staging_extra_and_lock_evidence(store):
    local, _, _, installed = store
    orphan = local.root / 'packages' / ('f' * 64)
    orphan.mkdir()
    (orphan / 'anything').write_bytes(b'not inspected')
    stage = local.root / 'staging' / ('install-' + 'e' * 32)
    stage.mkdir(parents=True, exist_ok=True)
    (local.root / 'packages' / installed['package_sha256'] / 'extra.txt').write_bytes(b'not executed')
    before = snapshot(local.root)
    report = PackageAudit(local.root).scan()
    assert not report['passed'] and report['integrity_healthy']
    assert {'unregistered_content', 'retained_staging', 'extra_member'} <= codes(report)
    assert any(entry['classification'] == 'lock_evidence' for entry in report['entries'])
    assert report['installations'][0]['state'] == 'ready'
    assert snapshot(local.root) == before


def test_missing_store_does_not_initialize_and_bad_version_refused(tmp_path, store):
    missing = tmp_path / 'absent'
    with pytest.raises(PackageError) as error:
        PackageAudit(missing)
    assert error.value.code == 'store_not_found'
    assert not missing.exists()
    local, _, _, _ = store
    with sqlite3.connect(local.path) as db:
        db.execute('PRAGMA user_version=77')
    before = snapshot(local.root)
    with pytest.raises(PackageError) as error:
        PackageAudit(local.root).scan()
    assert error.value.code == 'unsupported_store'
    assert snapshot(local.root) == before


def test_dangling_active_and_unknown_install_state(store):
    local, _, _, installed = store
    with sqlite3.connect(local.path) as db:
        db.execute('UPDATE active SET digest=?', ('a' * 64,))
        db.execute("UPDATE installs SET state='unexpected'")
    report = PackageAudit(local.root).scan()
    assert report['active'][0]['integrity'] == 'missing_registration'
    assert {'active_unusable', 'invalid_installation_state'} <= codes(report)


def test_limit_refuses_partial_database_and_marks_incomplete_directory(store):
    local, _, _, _ = store
    # Package directory contains four files, exceeding limit=1.
    report = PackageAudit(local.root).scan(limit=1)
    assert not report['complete'] and not report['passed']
    with sqlite3.connect(local.path) as db:
        db.execute("INSERT INTO installs VALUES (?,?,?,0,NULL)", ('install-' + 'a' * 32, 'a' * 64, 'copying'))
    with pytest.raises(PackageError) as error:
        PackageAudit(local.root).scan(limit=1)
    assert error.value.code == 'audit_limit'


def test_live_install_report_never_claims_dead_or_changes_state(store, tmp_path):
    local, source, package, _ = store
    marker = tmp_path / 'running.json'
    code = '''
import sys,json,time
from pathlib import Path
from packages.infrastructure.agent_files import FilePackages
s=FilePackages(sys.argv[1])
def barrier(phase, identity):
 if phase=='copied_member':
  Path(sys.argv[4]).write_text(json.dumps({'id':identity}))
  time.sleep(30)
s._checkpoint=barrier
s.install(sys.argv[2],sys.argv[3])
'''
    parent = subprocess.Popen([sys.executable, '-c', code, str(local.root), str(package), str(source), str(marker)])
    try:
        end = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < end:
            time.sleep(.02)
        assert marker.exists()
        identity = json.loads(marker.read_text())['id']
        report = PackageAudit(local.root).scan()
        item = next(i for i in report['installations'] if i['install_id'] == identity)
        assert item['state'] == 'copying' and item['owner_status'] == 'not_probed'
        assert 'nonterminal_installation' in codes(report)
        assert local.installation(identity)['state'] == 'copying'
    finally:
        parent.kill()
        parent.wait(timeout=10)


def test_cli_diagnostics_exit_and_database_corruption(store):
    local, _, _, installed = store
    command = [sys.executable, '-m', 'apps.cli.agent_local', '--root', str(local.root), '--backend', 'files', 'audit']
    good = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert good.returncode == 0 and json.loads(good.stdout)['passed']
    (local.root / 'packages' / installed['package_sha256'] / 'coverage.json').unlink()
    bad = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert bad.returncode == 2 and not json.loads(bad.stdout)['passed']
    local.path.write_bytes(b'broken database')
    before = snapshot(local.root)
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert json.loads(result.stdout)['error']['code'] == 'local_error'
    assert snapshot(local.root) == before


def test_query_only_connection_and_scan_permission_failure(store, monkeypatch):
    local, _, _, _ = store
    audit = PackageAudit(local.root)
    with audit._connect() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute('DELETE FROM active')
    import packages.infrastructure.agent_audit as module
    original = module.os.scandir
    def deny(path):
        if Path(path) == local.root / 'staging':
            raise PermissionError('injected inventory permission failure')
        return original(path)
    monkeypatch.setattr(module.os, 'scandir', deny)
    report = audit.scan()
    assert not report['complete'] and not report['passed']
    assert 'inventory_incomplete' in codes(report)
