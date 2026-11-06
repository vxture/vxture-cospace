"""J3 reproducible synthetic recovery records; random private seeds never exported."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import tempfile
import uuid

from experiments.scripts.recovery_state import RecoveryStore
from tests.test_validity_probe import gate, proofs, CAP
from tests.test_trust_proof import token


def main():
    output = Path('experiments/runs/p2-recovery-state-001')
    output.mkdir(parents=True, exist_ok=True)
    scenarios = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture = gate.__wrapped__(root)
        def opened(folder):
            return RecoveryStore(folder, fixture['context'][2], fixture['policy'])
        for name in ('revocation', 'expired_duplicate', 'atomic_failure'):
            folder = root / name
            store = RecoveryStore.bootstrap(folder, fixture['context'][2], fixture['policy'])
            status, grant = proofs(fixture)
            for kind, signed in [('content_statement', token(fixture['context'][0], fixture['content'])),
                                 ('status_snapshot', status), ('capability_grant', grant)]:
                store.accept(fixture['binding'], signed, kind, intent_id=str(uuid.uuid4()))
            intent_id = str(uuid.uuid4())
            signed = status if name == 'expired_duplicate' else proofs(fixture, sequence=2, state='revoked')[0]
            def interrupt(stage):
                if stage == 'after_prepare_commit':
                    raise sqlite3.OperationalError('prepared interruption')
            store._barrier = interrupt
            try:
                store.accept(fixture['binding'], signed, 'status_snapshot', intent_id=intent_id)
            except sqlite3.OperationalError:
                pass
            before = opened(folder)
            recovery_id = str(uuid.uuid4())
            started = before.begin_recovery(recovery_id)
            owner = opened(folder)
            old_plan = owner.plan_recovery(recovery_id)
            resumed = owner.resume_recovery(recovery_id)
            owner = opened(folder)
            plan = owner.plan_recovery(recovery_id)
            if name == 'atomic_failure':
                def fail(stage):
                    if stage == 'before_recovery_finish_commit':
                        raise sqlite3.OperationalError('finish rollback')
                owner._barrier = fail
                try:
                    owner.commit_recovery(plan)
                except sqlite3.OperationalError:
                    pass
                after = opened(folder)
                assert after.receipt(intent_id) is None
            else:
                owner.commit_recovery(plan)
                after = opened(folder)
            fixture['tick'][1] = 50.0 if name == 'expired_duplicate' else 10.0
            decision = after.decide(fixture['binding'], CAP, fixture['clock'])
            expected = {'revocation': 'revoked', 'expired_duplicate': 'expired', 'atomic_failure': 'recovery_required'}[name]
            assert decision['reason'] == expected
            scenarios.append({'name': name, 'begin': started, 'resume': resumed,
                'superseded_plan': old_plan, 'plan': plan, 'result': after.recovery_result(recovery_id),
                'receipt': after.receipt(intent_id), 'decision': decision,
                'old_object_decision': before.decide(fixture['binding'], CAP, fixture['clock'])})
            # Independent fixture clock is reset rather than regress an existing counter.
            from experiments.scripts.validity_probe import IntervalClock
            fixture['tick'][1] = 10.0
            fixture['clock'] = IntervalClock(lambda: tuple(fixture['tick']), ('boot-a', 10.0, 110, 110))
        (output / 'scenario.json').write_text(json.dumps({'test_only': True, 'scenarios': scenarios,
            'public_test_trust': fixture['context'][1], 'authorized': False, 'robot_ready': False},
            ensure_ascii=False, indent=2), encoding='utf-8')
    files = ['experiments/scripts/recovery_state.py', 'experiments/scripts/recovery_state_evidence.py',
             'experiments/scripts/recovery_journal.py', 'experiments/scripts/recovery_lock_probe.py',
             'experiments/scripts/validity_probe.py', 'experiments/scripts/trust_proof.py',
             'tests/test_recovery_state.py', 'contracts/schemas/recovery-journal-v0.1.schema.json']
    (output / 'environment.json').write_text(json.dumps({'python': platform.python_version(),
        'platform': platform.platform(), 'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in files}}, indent=2), encoding='utf-8')
    print('3 recovery scenarios verified: revocation, expired duplicate, atomic rollback; no private seeds exported')


if __name__ == '__main__':
    main()
