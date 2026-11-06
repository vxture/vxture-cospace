from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest
from test_preview_consumer import deliveries
from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
from packages.views.agent.preview_offline import OfflinePreview, export_bundle, sha


def install(store, delivery):
    path, publication, digest = delivery
    return store.install(path, publication, digest)


def activate(store, delivery, revision):
    return store.activate(delivery[1], delivery[2], revision)


def test_install_is_independent_and_restart_requires_explicit_exact_restore(tmp_path, monkeypatch):
    old, new = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old)
    assert store.status()['revision'] == 0 and store.status()['saved_reference'] is None
    with pytest.raises(ValueError, match='no_active'):
        store.session()
    first = activate(store, old, 0)
    expected = first.query([-.05,.05,.05])
    install(store, new)
    assert store.session() is first and store.status()['revision'] == 1
    # Source ZIP can disappear; installed content is self-contained.
    old[0].unlink()
    restarted = PersistentPreviewConsumer(store.root)
    assert restarted.status()['restore_required'] and restarted.status()['session_reference'] is None
    with pytest.raises(ValueError, match='no_active'):
        restarted.session()
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network must stay unused'))
    with pytest.raises(ValueError, match='saved_reference_mismatch'):
        restarted.restore(new[1], new[2], 1)
    restored = restarted.restore(old[1], old[2], 1)
    assert restored.query([-.05,.05,.05]) == expected
    assert not restarted.status()['restore_required']
    assert restarted.status()['robot_ready'] is False


def test_new_activation_and_historical_review_leave_old_sessions_fixed(tmp_path):
    old, new = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old); install(store, new)
    first = activate(store, old, 0)
    original = first.query([-.05,.05,.05])
    second = activate(store, new, 1)
    assert second.query([-.05,.05,.05])['state'] == 'unknown'
    assert first.query([-.05,.05,.05]) == original
    restarted = PersistentPreviewConsumer(store.root)
    assert restarted.restore(new[1], new[2], 2).publication_id == new[1]
    with pytest.raises(ValueError, match='revision_changed'):
        activate(restarted, old, 1)
    review = activate(restarted, old, 2)
    assert review.revision == 3 and review.publication_id == old[1]
    assert second.publication_id == new[1] and first.query([-.05,.05,.05]) == original


@pytest.mark.parametrize('kind', ['data', 'metadata', 'missing'])
def test_corrupt_installed_data_refused_on_restore_without_repair_or_fallback(tmp_path, kind):
    old, _ = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old); activate(store, old, 0)
    with sqlite3.connect(store.path) as db:
        if kind == 'data':
            db.execute('UPDATE packages SET data=?', (b'changed',))
        elif kind == 'metadata':
            binding = store.status()['saved_reference'] | {'model_id':'different-model'}
            db.execute('UPDATE packages SET binding=?', (json.dumps(binding),))
        else:
            db.execute('DELETE FROM packages')
    restarted = PersistentPreviewConsumer(store.root)
    with pytest.raises((ValueError, KeyError)):
        restarted.restore(old[1], old[2], 1)
    with pytest.raises(ValueError, match='no_active'):
        restarted.session()
    if kind != 'missing':
        with pytest.raises(ValueError):
            install(restarted, old)  # No silent repair of a corrupted installation.


def test_failed_sql_transaction_keeps_saved_reference_and_session(tmp_path):
    old, new = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old); install(store, new)
    first = activate(store, old, 0)
    before = store.status()
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER fail_switch BEFORE UPDATE ON consumer BEGIN SELECT RAISE(ABORT,'simulated_write_failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='simulated_write_failure'):
        activate(store, new, 1)
    assert store.status() == before and store.session() is first
    assert PersistentPreviewConsumer(store.root).status()['saved_reference'] == before['saved_reference']


def test_independent_instances_compare_and_swap_and_pinned_sessions(tmp_path):
    old, new = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old); install(store, new)
    first = activate(store, old, 0)
    instances = [PersistentPreviewConsumer(store.root), PersistentPreviewConsumer(store.root)]
    def attempt(instance):
        try:
            return activate(instance, new, 1).revision
        except ValueError as exc:
            return str(exc)
    with ThreadPoolExecutor(2) as pool:
        assert sorted(map(str, pool.map(attempt, instances))) == ['2','consumer_revision_changed']
    assert store.status()['restore_required'] and store.session() is first
    assert first.publication_id == old[1]


def test_wrong_package_scope_and_revision_never_change_saved_state(tmp_path):
    old, _ = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old); activate(store, old, 0)
    before = store.status()
    with pytest.raises(ValueError): store.install(old[0], 'preview-wrong', old[2])
    with pytest.raises(ValueError): store.install(old[0], old[1], '0'*64)
    for revision in [True, 1.0, -1, None]:
        with pytest.raises(ValueError, match='invalid_consumer_revision'):
            store.restore(old[1], old[2], revision)
    assert store.status() == before
    scoped = PersistentPreviewConsumer.initialize(tmp_path/'other-space', 'space-other')
    with pytest.raises(ValueError, match='space_mismatch'): install(scoped, old)
    assert scoped.packages() == []


def test_open_missing_store_never_creates_it_and_init_never_reuses(tmp_path):
    root = tmp_path/'consumer'
    with pytest.raises(sqlite3.OperationalError): PersistentPreviewConsumer(root)
    assert not root.exists()
    PersistentPreviewConsumer.initialize(root)
    with pytest.raises(FileExistsError): PersistentPreviewConsumer.initialize(root)


def test_same_publication_different_zip_bytes_never_rebinds(tmp_path):
    old, _ = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old)
    # ZIP permits trailing bytes; this is a different delivery for the same publication.
    changed = old[0].read_bytes()+b'another-delivery'
    old[0].write_bytes(changed)
    with pytest.raises(ValueError, match='publication_package_conflict'):
        store.install(old[0], old[1], sha(changed))
    assert len(store.packages()) == 1 and store.status()['revision'] == 0


def test_process_death_before_transaction_commit_keeps_original_reference(tmp_path):
    old, new = deliveries(tmp_path)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer')
    install(store, old); install(store, new); activate(store, old, 0)
    code = """import sqlite3,sys
db=sqlite3.connect(sys.argv[1]);db.execute('BEGIN IMMEDIATE')
db.execute('UPDATE consumer SET revision=2,digest=? WHERE id=1',(sys.argv[2],))
print('uncommitted',flush=True)
sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable,'-c',code,str(store.path),new[2]],
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip() == 'uncommitted'
        child.kill(); child.wait(timeout=10)
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=10)
        child.stdin.close(); child.stdout.close()
    restarted = PersistentPreviewConsumer(store.root)
    assert restarted.status()['revision'] == 1
    assert restarted.restore(old[1], old[2], 1).publication_id == old[1]


def test_semantic_and_range_queries_restore_same_model_and_ontology(tmp_path):
    from test_preview_objects import fixture
    from packages.construction.preview_semantics import annotate
    from packages.spatial.preview_objects import SemanticRequest
    from packages.service.preview_publications import PreviewPublications
    _, jobs, _, _, ontologies, request = fixture(tmp_path)
    candidate = annotate(jobs, ontologies, SemanticRequest.model_validate(request))
    selection = jobs.select(candidate['id'], 0, request['space_id'])
    publications = PreviewPublications(jobs)
    record = publications.publish(candidate['id'], selection['revision'], request['space_id'])
    data = export_bundle(*publications.read(record['id']))
    path = tmp_path/'semantic.zip'; path.write_bytes(data)
    store = PersistentPreviewConsumer.initialize(tmp_path/'consumer', request['space_id'])
    store.install(path, record['id'], sha(data)); store.activate(record['id'], sha(data), 0)
    restored = PersistentPreviewConsumer(store.root).restore(record['id'], sha(data), 1)
    offline = OfflinePreview(data, record['id'], sha(data))
    for method, args in [('objects', []), ('objects', ['object-001']),
                         ('query_range', [[[-1,-1,-1],[1,1,3]], 'anchor', 1]),
                         ('query', [[0,0,2]])]:
        result = getattr(restored, method)(*args)
        assert result == getattr(offline, method)(*args) | {'consumer_revision':1,'package_sha256':sha(data)}
    with pytest.raises(ValueError): restored.query_range([[0,0,0],[1,1,1]], 'wrong-frame')


def test_cli_separate_processes_recover_and_error_codes(tmp_path):
    old, _ = deliveries(tmp_path)
    root = tmp_path/'consumer'
    def cli(*args):
        return subprocess.run([sys.executable,'-m','apps.cli.preview_consumer','--root',str(root),*map(str,args)],capture_output=True,text=True)
    assert cli('init','--legacy').returncode == 0
    assert cli('install',old[0],'--publication',old[1],'--sha256',old[2]).returncode == 0
    command = ['--publication',old[1],'--sha256',old[2],'--expected-revision',0]
    assert cli('activate',*command).returncode == 0
    status = json.loads(cli('status').stdout)
    assert status['restore_required'] and status['session_reference'] is None
    command[-1] = 1
    restored = cli('restore',*command,'--point',-.05,.05,.05)
    assert restored.returncode == 0 and json.loads(restored.stdout)['state'] == 'surface_candidate'
    assert cli('restore',*command,'--bounds',-1,-1,-1,1,1,1,'--frame-id','anchor','--limit',1).returncode == 3
    command[-1] = 0
    assert cli('restore',*command).returncode == 2
    assert json.loads(cli('status').stdout)['revision'] == 1
