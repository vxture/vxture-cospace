"""B04a durable authoring, fixed review identity and immutable version releases."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from itertools import count

import pytest

from packages.ontology.authoring_sqlite import SQLiteAuthoringPort
from packages.ontology.kernel import Catalog, builtin_catalog, canonical_bytes
from packages.ontology.kernel.authoring import AuthoringError, DefinitionAuthoring


def service(tmp_path):
    roles = {'editor': {'read', 'edit', 'submit'}, 'reviewer': {'read', 'review'},
             'publisher': {'read', 'publish'}}
    return DefinitionAuthoring(SQLiteAuthoringPort(tmp_path),
                               authorize=lambda scope, actor, action: action in roles.get(actor, set()),
                               clock=lambda: '2026-11-20T00:00:00Z')


def request_ids():
    return (f'{i:032x}' for i in count(1))


def save(svc, ids, bundle, revision=0, base=None, scope='park-library'):
    return svc.save(scope, 'editor', next(ids), module_id=bundle['modules'][-1]['module_id'],
                    expected_revision=revision, bundle=bundle, base_reference=base)


def publish(svc, ids, identity, revision=1, scope='park-library'):
    review = svc.submit(scope, 'editor', next(ids), module_id=identity, expected_revision=revision)
    svc.decide(scope, 'reviewer', next(ids), review_id=review['review_id'], decision='approved', reason='工程定义与依赖核对通过')
    return svc.publish(scope, 'publisher', next(ids), review_id=review['review_id'], expected_revision=revision)


def core():
    return builtin_catalog().export('core')


def test_invalid_intermediate_draft_can_be_saved_but_not_submitted(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    bundle = core()
    bundle['modules'][0]['concepts']['physical_object']['parent'] = 'core:missing'
    save(svc, ids, bundle)
    assert service(tmp_path).read_draft('park-library', 'editor', 'core')['bundle'] == bundle
    report = svc.validate('park-library', 'editor', 'core', 1)
    assert not report['valid'] and report['diagnostics'][0]['code'] == 'unresolved_concept'
    with pytest.raises(AuthoringError, match='validation_failed'):
        svc.submit('park-library', 'editor', next(ids), module_id='core', expected_revision=1)


def test_durable_release_exact_history_and_detached_results(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    release = publish(svc, ids, 'core')
    original = deepcopy(release)
    assert release['state'] == 'published' and release['published_at'].endswith('Z')
    assert release['bundle']['modules'][0]['status'] == 'draft'  # semantic maturity is independent
    release['bundle']['modules'][0]['title'] = 'changed by caller'
    assert service(tmp_path).read_release('park-library', 'editor', original['reference']) == original
    next_bundle = core()
    next_bundle['modules'][0].update(version='0.2.0', title='通用核心更新')
    save(svc, ids, next_bundle, revision=1, base=original['reference'])
    diff = svc.compare('park-library', 'editor', 'core', 2)
    assert {d['path'] for d in diff['changes']} == {'/title', '/version'}
    updated = publish(svc, ids, 'core', revision=2)
    assert updated['reference']['version'] == '0.2.0'
    assert svc.read_release('park-library', 'editor', original['reference']) == original
    assert len(svc.list_releases('park-library', 'editor', 'core')) == 2
    with pytest.raises(AuthoringError, match='release_not_found'):
        svc.read_release('park-library', 'editor', {**original['reference'], 'sha256': '0' * 64})


def test_authorization_precedes_read_write_and_idempotent_replay(tmp_path):
    svc = service(tmp_path)
    request = 'a' * 32
    kwargs = dict(module_id='core', expected_revision=0, bundle=core())
    first = svc.save('a', 'editor', request, **kwargs)
    assert svc.save('a', 'editor', request, **kwargs) == first
    for actor in ('reviewer', 'publisher', 'unknown'):
        with pytest.raises(AuthoringError, match='forbidden'):
            svc.save('a', actor, request, **kwargs)
    with pytest.raises(AuthoringError, match='request_conflict'):
        svc.save('a', 'editor', request, **{**kwargs, 'expected_revision': 1})
    with pytest.raises(AuthoringError, match='forbidden'):
        svc.read_draft('a', 'unknown', 'core')
    with pytest.raises(AuthoringError, match='draft_not_found'):
        svc.read_draft('b', 'editor', 'core')


def test_concurrent_saves_only_one_revision_wins(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())

    def attempt(identity):
        try:
            svc.save('park-library', 'editor', f'{identity:032x}', module_id='core', expected_revision=1, bundle=core())
            return 'saved'
        except AuthoringError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, [101, 102])) == ['revision_changed', 'saved']
    assert svc.read_draft('park-library', 'editor', 'core')['revision'] == 2


def test_approval_is_bound_to_exact_draft_revision(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    review = svc.submit('park-library', 'editor', next(ids), module_id='core', expected_revision=1)
    svc.decide('park-library', 'reviewer', next(ids), review_id=review['review_id'], decision='approved', reason='核对通过')
    changed = core()
    changed['modules'][0]['title'] = '再次修改'
    save(svc, ids, changed, revision=1)
    with pytest.raises(AuthoringError, match='review_stale'):
        svc.publish('park-library', 'publisher', next(ids), review_id=review['review_id'], expected_revision=2)
    assert svc.list_releases('park-library', 'editor', 'core') == []


def test_pending_review_cannot_be_decided_after_draft_changes(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    review = svc.submit('park-library', 'editor', next(ids), module_id='core', expected_revision=1)
    save(svc, ids, core(), revision=1)
    with pytest.raises(AuthoringError, match='revision_changed'):
        svc.decide('park-library', 'reviewer', next(ids), review_id=review['review_id'], decision='approved', reason='核对通过')
    frozen_review = svc.read_review('park-library', 'editor', review['review_id'])
    assert frozen_review['state'] == 'pending'
    assert frozen_review['submitted_bundle'] == core()


def test_separate_actor_review_and_rejection_gate(tmp_path):
    port = SQLiteAuthoringPort(tmp_path)
    svc = DefinitionAuthoring(port, authorize=lambda *args: True)
    ids = request_ids()
    save(svc, ids, core())
    review = svc.submit('park-library', 'editor', next(ids), module_id='core', expected_revision=1)
    with pytest.raises(AuthoringError, match='self_approval_forbidden'):
        svc.decide('park-library', 'editor', next(ids), review_id=review['review_id'], decision='approved', reason='自己批准')
    svc.decide('park-library', 'reviewer', next(ids), review_id=review['review_id'], decision='rejected', reason='需补充评审')
    with pytest.raises(AuthoringError, match='approval_required'):
        svc.publish('park-library', 'publisher', next(ids), review_id=review['review_id'], expected_revision=1)


def test_dependencies_must_be_published_exactly_and_closure_is_preserved(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    # Explicit save here because sorted export places the target after core.
    save(svc, ids, builtin_catalog().export('electrical'))
    with pytest.raises(AuthoringError, match='release_not_found'):
        svc.submit('park-library', 'editor', next(ids), module_id='electrical', expected_revision=1)
    save(svc, ids, core())
    publish(svc, ids, 'core')
    electrical = publish(svc, ids, 'electrical')
    assert Catalog.from_bytes(canonical_bytes(electrical['bundle'])).export() == electrical['bundle']
    assert len(electrical['bundle']['modules']) == 2


def test_published_version_cannot_be_overwritten_even_after_approval(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    release = publish(svc, ids, 'core')
    save(svc, ids, core(), revision=1)
    with pytest.raises(AuthoringError, match='version_exists'):
        svc.submit('park-library', 'editor', next(ids), module_id='core', expected_revision=2)
    assert svc.read_release('park-library', 'editor', release['reference']) == release


def test_transaction_failure_does_not_write_state(tmp_path):
    port = SQLiteAuthoringPort(tmp_path)
    with pytest.raises(RuntimeError):
        with port.transaction('scope') as state:
            state['drafts'] = {'should-not-exist': {}}
            raise RuntimeError('rollback')
    with port.transaction('scope') as state:
        assert state == {}


def test_release_reads_detect_content_corruption(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    release = publish(svc, ids, 'core')
    with svc.port.transaction('park-library') as state:
        state['releases']['core@0.1.0']['bundle']['modules'][0]['title'] = 'tampered'
    with pytest.raises(AuthoringError, match='release_integrity'):
        svc.read_release('park-library', 'editor', release['reference'])


def test_dependency_upgrade_is_explicit_and_old_bundle_remains_readable(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    initial_core = publish(svc, ids, 'core')
    original_electrical = builtin_catalog().export('electrical')
    save(svc, ids, original_electrical)
    old_release = publish(svc, ids, 'electrical')
    upgraded_core = core()
    upgraded_core['modules'][0]['version'] = '0.2.0'
    save(svc, ids, upgraded_core, revision=1, base=initial_core['reference'])
    new_core = publish(svc, ids, 'core', revision=2)
    new_electrical = deepcopy(original_electrical)
    new_electrical['modules'][0] = deepcopy(upgraded_core['modules'][0])
    new_electrical['modules'][1]['version'] = '0.3.0'
    # An un-rebound old dependency digest must fail; the service never updates it for the caller.
    save(svc, ids, new_electrical, revision=1, base=old_release['reference'])
    assert not svc.validate('park-library', 'editor', 'electrical', 2)['valid']
    new_electrical['modules'][1]['requires'] = [new_core['reference']]
    save(svc, ids, new_electrical, revision=2, base=old_release['reference'])
    new_release = publish(svc, ids, 'electrical', revision=3)
    assert new_release['bundle']['modules'][0]['version'] == '0.2.0'
    assert svc.read_release('park-library', 'editor', old_release['reference'])['bundle'] == original_electrical


def test_storage_budget_rejection_rolls_back_save(monkeypatch, tmp_path):
    import packages.ontology.authoring_sqlite as adapter
    monkeypatch.setattr(adapter, 'MAX_STATE_BYTES', 20)
    svc, ids = service(tmp_path), request_ids()
    with pytest.raises(AuthoringError, match='state_budget'):
        save(svc, ids, core())
    monkeypatch.setattr(adapter, 'MAX_STATE_BYTES', 16 * 1024 * 1024)
    with pytest.raises(AuthoringError, match='draft_not_found'):
        svc.read_draft('park-library', 'editor', 'core')


def test_review_and_publication_retries_return_same_results(tmp_path):
    svc, ids = service(tmp_path), request_ids()
    save(svc, ids, core())
    submit_id = next(ids)
    kwargs = {'module_id': 'core', 'expected_revision': 1}
    review = svc.submit('park-library', 'editor', submit_id, **kwargs)
    assert svc.submit('park-library', 'editor', submit_id, **kwargs) == review
    decision_id = next(ids)
    decision = dict(review_id=review['review_id'], decision='approved', reason='评审通过')
    result = svc.decide('park-library', 'reviewer', decision_id, **decision)
    assert svc.decide('park-library', 'reviewer', decision_id, **decision) == result
    publish_id = next(ids)
    kwargs = {'review_id': review['review_id'], 'expected_revision': 1}
    release = svc.publish('park-library', 'publisher', publish_id, **kwargs)
    assert svc.publish('park-library', 'publisher', publish_id, **kwargs) == release


@pytest.mark.parametrize('revision', [None, True, -1, '1'])
def test_invalid_revision_cannot_bypass_concurrency_gate(tmp_path, revision):
    svc = service(tmp_path)
    with pytest.raises(AuthoringError, match='invalid_revision'):
        svc.submit('park-library', 'editor', 'a' * 32, module_id='core', expected_revision=revision)
    with pytest.raises(AuthoringError, match='invalid_revision'):
        svc.publish('park-library', 'publisher', 'b' * 32, review_id='missing', expected_revision=revision)
