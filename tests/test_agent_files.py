"""R1b real process interruption, immutable files and conservative recovery."""
import json
import errno
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest
from packages.infrastructure.agent_files import FilePackages
from packages.views.agent.local import LocalPackages
from packages.views.agent.runtime import build, PackageError
from scripts.build_sample import build as build_source


@pytest.fixture
def installed(tmp_path):
    source, package = tmp_path / 'source', tmp_path / 'package'
    build_source(source, spatial=True)
    report = build(source, package)
    store = FilePackages(tmp_path / 'store')
    result = store.install(package, source)
    store.activate(report['source']['scene_id'], report['package_sha256'], 0)
    return store, source, package, result


def test_files_ready_restart_and_sessions(installed, tmp_path):
    store, source, package, first = installed
    scene = first['source']['scene_id']
    assert store.installation(first['install_id'])['state'] == 'ready'
    before = store.open_session(scene)
    def changed(name, document):
        if name == 'coverage.json':
            document['regions'][0]['state'] = 'occupied'
    source2, package2 = tmp_path / 'source2', tmp_path / 'package2'
    build_source(source2, mutate=changed, spatial=True)
    second = build(source2, package2)
    store.install(package2, source2)
    store.activate(scene, second['package_sha256'], 1)
    shutil.rmtree(source)
    shutil.rmtree(package)
    after = FilePackages(store.root).open_session(scene)
    assert before.query([1, 0, 1])['state'] == 'observed_free'
    assert after.query([1, 0, 1])['state'] == 'occupied'
    with sqlite3.connect(store.path) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(packages)')}
        assert 'members' not in columns
    before.close()
    after.close()


@pytest.mark.parametrize('phase,expected_state', [('copying', 'copying'), ('copied_member', 'copying'),
                                                ('sealed_before_state', 'verified'), ('before_commit', 'sealed')])
def test_crash_and_conservative_recovery(installed, tmp_path, phase, expected_state):
    store, source, _, first = installed
    package2 = tmp_path / 'new-package'
    report = build(source, package2)
    code = '''
import os,sys
from packages.infrastructure.agent_files import FilePackages
s=FilePackages(sys.argv[1])
def barrier(phase, identity):
 if phase==sys.argv[4]: os._exit(72)
s._checkpoint=barrier
s.install(sys.argv[2],sys.argv[3])
'''
    result = subprocess.run([sys.executable, '-c', code, str(store.root), str(package2), str(source), phase], timeout=20)
    assert result.returncode == 72
    reopened = FilePackages(store.root)
    record = reopened.installations()['items'][0]
    assert record['state'] == expected_state
    with pytest.raises(PackageError) as error:
        reopened.activate(first['source']['scene_id'], report['package_sha256'], 1)
    assert error.value.code == 'package_not_found'
    assert reopened.status(first['source']['scene_id'])['package_sha256'] == first['package_sha256']
    recovered = reopened.recover_installation(record['install_id'], record['revision'])
    assert recovered['state'] == 'interrupted'
    with pytest.raises(PackageError):
        reopened.recover_installation(record['install_id'], record['revision'])
    # Retry is a fresh install; it validates a retained sealed directory instead of promoting it implicitly.
    retry = reopened.install(package2, source)
    assert retry['install_id'] != record['install_id']
    assert retry['installation_state'] == 'ready'
    assert reopened.installation(record['install_id'])['state'] == 'interrupted'


def test_live_owner_recovery_blocked(installed, tmp_path):
    store, source, package, _ = installed
    marker = tmp_path / 'owner.json'
    code = '''
import sys,time,json
from pathlib import Path
from packages.infrastructure.agent_files import FilePackages
s=FilePackages(sys.argv[1])
def barrier(phase, identity):
 if phase=='copying':
  Path(sys.argv[4]).write_text(json.dumps({'id':identity}))
  time.sleep(30)
s._checkpoint=barrier
s.install(sys.argv[2],sys.argv[3])
'''
    parent = subprocess.Popen([sys.executable, '-c', code, str(store.root), str(package), str(source), str(marker)])
    try:
        end = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < end:
            time.sleep(.02)
        assert marker.exists()
        identity = json.loads(marker.read_text())['id']
        with pytest.raises(PackageError) as error:
            store.recover_installation(identity, 0)
        assert error.value.code == 'owner_alive'
        assert store.installation(identity)['state'] == 'copying'
    finally:
        parent.kill()
        parent.wait(timeout=10)
    assert store.recover_installation(identity, 0)['state'] == 'interrupted'


def test_corrupt_files_never_overwritten_or_activated(installed):
    store, source, package, first = installed
    session = store.open_session(first['source']['scene_id'])
    sealed = store.root / 'packages' / first['package_sha256'] / 'coverage.json'
    sealed.write_bytes(b'{}')
    with pytest.raises(ValueError):
        store.install(package, source)
    assert store.installations()['items'][0]['state'] == 'failed'
    assert sealed.read_bytes() == b'{}'
    with pytest.raises(ValueError):
        store.open_session(first['source']['scene_id'])
    assert session.query([1, 0, 1])['state'] == 'observed_free'
    session.close()


def test_injected_write_and_db_failure_preserve_current(installed, tmp_path, monkeypatch):
    store, source, _, first = installed
    package2 = tmp_path / 'second'
    report = build(source, package2)
    def fail_commit(operation):
        raise sqlite3.OperationalError('injected commit failure')
    monkeypatch.setattr(store, '_before_commit', fail_commit)
    with pytest.raises(sqlite3.OperationalError):
        store.install(package2, source)
    assert store.installations()['items'][0]['state'] == 'failed'
    assert store.status(first['source']['scene_id'])['package_sha256'] == first['package_sha256']
    assert (store.root / 'packages' / report['package_sha256']).exists()
    monkeypatch.setattr(store, '_before_commit', lambda operation: None)
    store.install(package2, source)
    import packages.infrastructure.agent_files as files
    def no_space(*args):
        raise OSError(28, 'injected disk full')
    monkeypatch.setattr(files, 'write_new', no_space)
    with pytest.raises(OSError):
        store.install(package2, source)
    assert store.status(first['source']['scene_id'])['revision'] == 1
    assert store.installations()['items'][0]['state'] == 'failed'


def test_store_backend_separation_and_invalid_ids(installed, tmp_path):
    store, _, _, first = installed
    with pytest.raises(PackageError) as error:
        LocalPackages(store.root)
    assert error.value.code == 'files_store'
    blob = LocalPackages(tmp_path / 'legacy')
    with pytest.raises(PackageError):
        FilePackages(blob.root)
    with pytest.raises(PackageError):
        store.installation('../escape')
    with pytest.raises(PackageError):
        store.recover_installation(first['install_id'], 0)


def test_sqlite_corruption_does_not_create_new_empty_store(installed):
    store, _, _, _ = installed
    store.path.write_bytes(b'not sqlite')
    with pytest.raises(sqlite3.DatabaseError):
        FilePackages(store.root)
    assert store.path.read_bytes() == b'not sqlite'


def test_independent_process_activation_and_commit_crash(installed):
    store, _, _, first = installed
    scene, digest = first['source']['scene_id'], first['package_sha256']
    code = '''
import sys
from packages.infrastructure.agent_files import FilePackages
from packages.views.agent.runtime import PackageError
try:
 FilePackages(sys.argv[1]).activate(sys.argv[2],sys.argv[3],1)
except PackageError as error:
 print(error.code)
 sys.exit(2)
'''
    commands = [subprocess.Popen([sys.executable, '-c', code, str(store.root), scene, digest],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    results = [process.communicate(timeout=20) for process in commands]
    assert sorted(process.returncode for process in commands) == [0, 2]
    assert any(b'state_conflict' in output for output, _ in results)
    crash = '''
import os,sys
from packages.infrastructure.agent_files import FilePackages
s=FilePackages(sys.argv[1])
s._before_commit=lambda operation: os._exit(73)
s.activate(sys.argv[2],sys.argv[3],2)
'''
    result = subprocess.run([sys.executable, '-c', crash, str(store.root), scene, digest], timeout=20)
    assert result.returncode == 73
    assert FilePackages(store.root).status(scene)['revision'] == 2


@pytest.mark.parametrize('error_number', [errno.EEXIST, errno.ENOTEMPTY])
def test_existing_sealed_directory_reverified_for_both_os_errors(installed, monkeypatch, error_number):
    store, source, package, first = installed
    rename = Path.rename
    def collision(path, target):
        if path.parent == store.root / 'staging':
            raise OSError(error_number, 'synthetic destination collision')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', collision)
    result = store.install(package, source)
    assert result['package_sha256'] == first['package_sha256']
    assert result['installation_state'] == 'ready'


@pytest.mark.parametrize('error_number', [errno.EACCES, errno.EIO])
def test_other_seal_errors_still_propagate(installed, monkeypatch, error_number):
    store, source, package, first = installed
    rename = Path.rename
    def failure(path, target):
        if path.parent == store.root / 'staging':
            raise OSError(error_number, 'synthetic filesystem failure')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', failure)
    with pytest.raises(OSError) as caught:
        store.install(package, source)
    assert caught.value.errno == error_number
    assert store.status(first['source']['scene_id'])['package_sha256'] == first['package_sha256']
