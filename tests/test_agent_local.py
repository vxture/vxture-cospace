"""R1a transactional visibility, pinned sessions and real process interruption."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest
from packages.data.imports import canonical
from packages.views.agent.local import LocalPackages
from packages.views.agent.runtime import build, PackageError
from scripts.build_sample import build as build_source


@pytest.fixture
def local(tmp_path):
    source, package = tmp_path / 'source', tmp_path / 'package'
    build_source(source, spatial=True)
    first = build(source, package)
    store = LocalPackages(tmp_path / 'store')
    receipt = store.install(package, source)
    assert receipt == first
    return store, source, package, first


def second(local, tmp_path):
    store, source, _, _ = local
    def change(name, document):
        if name == 'coverage.json':
            document['regions'][0]['state'] = 'occupied'
    changed_source, changed_package = tmp_path / 'new-source', tmp_path / 'new-package'
    build_source(changed_source, mutate=change, spatial=True)
    report = build(changed_source, changed_package)
    store.install(changed_package, changed_source)
    return report


def test_offline_restart_and_closed_session(local):
    store, source, package, first = local
    scene = first['source']['scene_id']
    assert store.status(scene)['revision'] == 0
    store.activate(scene, first['package_sha256'], 0)
    shutil.rmtree(source)
    shutil.rmtree(package)
    reopened = LocalPackages(store.root)
    session = reopened.open_session(scene)
    assert session.query([1, 0, 1])['state'] == 'observed_free'
    assert session.query([100, 0, 1])['state'] == 'out_of_scope'
    assert session.query([9, 5, 2])['state'] == 'unknown'
    session.close()
    with pytest.raises(PackageError, match='closed'):
        session.query([1, 0, 1])


def test_pinned_session_across_switch(local, tmp_path):
    store, _, _, first = local
    scene = first['source']['scene_id']
    store.activate(scene, first['package_sha256'], 0)
    before = store.open_session(scene)
    new = second(local, tmp_path)
    store.activate(scene, new['package_sha256'], 1)
    after = store.open_session(scene)
    assert before.query([1, 0, 1])['state'] == 'observed_free'
    assert after.query([1, 0, 1])['state'] == 'occupied'
    assert before.query([1, 0, 1])['package_id'] == first['package_id']
    assert after.query([1, 0, 1])['package_id'] == new['package_id']
    before.close()
    after.close()


def test_concurrent_activation_single_winner(local):
    store, _, _, first = local
    scene = first['source']['scene_id']
    def activate(_):
        try:
            return store.activate(scene, first['package_sha256'], 0)['revision']
        except PackageError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(activate, range(2)))
    assert sorted(map(str, outcomes)) == ['1', 'state_conflict']


def test_failed_install_and_disk_headroom_leave_active(local):
    store, source, package, first = local
    scene = first['source']['scene_id']
    store.activate(scene, first['package_sha256'], 0)
    (package / 'coverage.json').write_bytes(b'{}')
    with pytest.raises(ValueError):
        store.install(package, source)
    assert store.status(scene)['revision'] == 1
    # A fresh valid fixture is rejected by free-space preflight, no commit.
    other = package.parent / 'fresh'
    build(source, other)
    with patch('packages.views.agent.local.shutil.disk_usage', return_value=type('Usage', (), {'free': 0})()):
        with pytest.raises(PackageError) as error:
            store.install(other, source)
    assert error.value.code == 'disk_space'
    assert store.status(scene)['package_sha256'] == first['package_sha256']


def test_idempotency_identity_conflict_and_corruption(local):
    store, source, package, first = local
    assert store.install(package, source)['package_sha256'] == first['package_sha256']
    path = package / 'agent-package.json'
    manifest = json.loads(path.read_text())
    manifest['components'][0]['component_id'] = 'renamed'
    path.write_bytes(canonical(manifest))
    with pytest.raises(PackageError) as error:
        store.install(package, source)
    assert error.value.code == 'identity_conflict'
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE packages SET members=?', (b'{}',))
    with pytest.raises(PackageError) as error:
        store.activate(first['source']['scene_id'], first['package_sha256'], 0)
    assert error.value.code == 'content_corrupt'
    assert store.status(first['source']['scene_id'])['revision'] == 0


@pytest.mark.parametrize('operation', ['install', 'activate'])
def test_real_process_exit_before_commit(local, tmp_path, operation):
    store, source, _, first = local
    scene = first['source']['scene_id']
    store.activate(scene, first['package_sha256'], 0)
    source2, package2 = tmp_path / 'crash-source', tmp_path / 'crash-package'
    build_source(source2, spatial=True)
    new = build(source2, package2)
    if operation == 'activate':
        store.install(package2, source2)
    code = '''
import os,sys
from packages.views.agent.local import LocalPackages
s=LocalPackages(sys.argv[1])
s._before_commit=lambda operation: os._exit(71)
if sys.argv[2]=='install': s.install(sys.argv[3],sys.argv[4])
else: s.activate(sys.argv[5],sys.argv[6],1)
'''
    result = subprocess.run([sys.executable, '-c', code, str(store.root), operation,
                             str(package2), str(source2), scene, new['package_sha256']], timeout=20)
    assert result.returncode == 71
    reopened = LocalPackages(store.root)
    assert reopened.status(scene)['package_sha256'] == first['package_sha256']
    assert reopened.status(scene)['revision'] == 1
    if operation == 'install':
        with sqlite3.connect(store.path) as db:
            assert db.execute('SELECT count(*) FROM packages').fetchone()[0] == 1


def test_scene_and_revision_rejections(local):
    store, _, _, first = local
    with pytest.raises(PackageError) as error:
        store.activate('other-scene', first['package_sha256'], 0)
    assert error.value.code == 'scene_mismatch'
    with pytest.raises(PackageError):
        store.activate(first['source']['scene_id'], first['package_sha256'], True)
    with pytest.raises(PackageError):
        store.open_session(first['source']['scene_id'])
