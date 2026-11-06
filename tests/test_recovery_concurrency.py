"""Cross-process file session/recovery barriers, including allowed in-flight replies."""
import os
import uuid

import pytest

from experiments.scripts.recovery_concurrency import SessionChild
from experiments.scripts.recovery_lock_probe import LockError
from experiments.scripts.recovery_audit import RecoveryAudit
from packages.data.imports import canonical
from tests.test_recovery_session import consumer
from tests.test_recovery_state import recovery, pending, plan, reopen
from tests.test_validity_probe import gate, proofs

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows process/lock integration')


def request(fixture, tmp_path):
    path = tmp_path / 'child-request.json'
    path.write_bytes(canonical({'journal': str(fixture['journal'].root), 'files': str(fixture['files'].root),
        'trust': fixture['context'][1], 'policy': vars(fixture['policy']), 'binding': fixture['binding']}))
    return path


def test_gate_lock_excludes_recovery_and_process_death_releases(consumer, tmp_path):
    controller = reopen(consumer)
    controller.timeout = .1
    with SessionChild(request(consumer, tmp_path)) as child:
        assert child.receive()['opened']
        child.send('query_locked')
        assert child.receive()['barrier'] == 'decision_locked'
        # begin cannot even inspect pending/control while query owns the OS lock.
        with pytest.raises(LockError, match='busy'):
            controller.begin_recovery(str(uuid.uuid4()))
        report = RecoveryAudit(controller.root).scan()
        assert report['complete'] and not report['recovery_authorized']
        child.process.kill()
        child.process.wait(timeout=10)
    # No pending exists: lock acquisition now succeeds and reaches semantic rejection.
    from experiments.scripts.validity_probe import GateError
    with pytest.raises(GateError, match='no_pending_intent'):
        controller.begin_recovery(str(uuid.uuid4()))


def test_locked_query_completes_before_later_recovery(consumer, tmp_path):
    with SessionChild(request(consumer, tmp_path)) as child:
        child.receive()
        child.send('query_locked')
        assert child.receive()['barrier'] == 'decision_locked'
        child.send('release')
        before = child.receive()['query']
        assert before['state'] == 'observed_free'
        pending(consumer, proofs(consumer)[0])
        _, proposed = plan(consumer)
        consumer['journal'].commit_recovery(proposed)
        child.send('query')
        assert child.receive()['error'] == 'stale_generation'
        child.send('fresh_query')
        after = child.receive()['query']
        assert after['session_generation'] == 3 and after['source'] == before['source']
        child.send('exit')
        assert child.process.wait(timeout=10) == 0


@pytest.mark.parametrize('revoked', [False, True])
def test_reply_already_past_gate_can_return_after_recovery(consumer, tmp_path, revoked):
    with SessionChild(request(consumer, tmp_path)) as child:
        opened = child.receive()
        child.send('query_after_gate')
        assert child.receive()['barrier'] == 'gate_passed'
        pending(consumer, None if revoked else proofs(consumer)[0])
        _, proposed = plan(consumer)
        consumer['journal'].commit_recovery(proposed)
        child.send('release')
        inflight = child.receive()['query']
        assert inflight['state'] == 'observed_free'
        assert inflight['session_generation'] == opened['generation'] == 1
        assert not inflight['authorized'] and not inflight['robot_ready']
        child.send('query')
        assert child.receive()['error'] == 'stale_generation'
        child.send('fresh_query')
        fresh = child.receive()
        if revoked:
            assert fresh['error'] == 'session_not_allowed'
        else:
            assert fresh['query']['session_generation'] == 3
        child.send('exit')
        assert child.process.wait(timeout=10) == 0


def test_resume_fences_existing_cross_process_session(consumer, tmp_path):
    with SessionChild(request(consumer, tmp_path)) as child:
        child.receive()
        pending(consumer, proofs(consumer)[0])
        rid, old_plan = plan(consumer)
        consumer['journal'].resume_recovery(rid)
        consumer['journal'] = reopen(consumer)
        child.send('query')
        assert child.receive()['error'] == 'stale_generation'
        proposed = consumer['journal'].plan_recovery(rid)
        assert proposed['generation'] == old_plan['generation'] + 1
        consumer['journal'].commit_recovery(proposed)
        child.send('fresh_query')
        assert child.receive()['query']['session_generation'] == 4
        child.send('exit')
        assert child.process.wait(timeout=10) == 0
