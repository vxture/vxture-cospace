"""Reproduce J2 prepare/apply faults in temporary synthetic stores; no private keys saved."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import tempfile
import uuid

from experiments.scripts.recovery_journal import JournalStore
from tests.test_validity_probe import gate, proofs, CAP
from tests.test_trust_proof import token


def main():
    output = Path('experiments/runs/p2-recovery-journal-001')
    output.mkdir(parents=True, exist_ok=True)
    scenarios = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture = gate.__wrapped__(root)
        trust, policy, binding = fixture['context'][2], fixture['policy'], fixture['binding']
        for stage in ('before_prepare_commit', 'after_prepare_commit', 'after_state_write',
                      'after_receipt_insert', 'after_apply_commit'):
            store = JournalStore.bootstrap(root / stage, trust, policy)
            initial = []
            status, grant = proofs(fixture)
            for kind, signed in [('content_statement', token(fixture['context'][0], fixture['content'])),
                                 ('status_snapshot', status), ('capability_grant', grant)]:
                initial.append(store.accept(binding, signed, kind, intent_id=str(uuid.uuid4())))
            intent_id = str(uuid.uuid4())
            signed = proofs(fixture, sequence=2, state='revoked')[0]
            def failure(current):
                if current == stage:
                    raise sqlite3.OperationalError('injected J2 boundary')
            store._barrier = failure
            try:
                store.accept(binding, signed, 'status_snapshot', intent_id=intent_id)
            except sqlite3.OperationalError:
                pass
            reopened = JournalStore(store.root, trust, policy)
            final = reopened.receipt(intent_id)
            decision = reopened.decide(binding, CAP, fixture['clock'])
            expected = 'synthetic_conditions_met' if stage == 'before_prepare_commit' else (
                'revoked' if stage == 'after_apply_commit' else 'recovery_required')
            assert decision['reason'] == expected
            exported = reopened.export_intent(intent_id) if stage != 'before_prepare_commit' else None
            scenarios.append({'stage': stage, 'initial_receipts': initial, 'intent': exported,
                              'receipt': final, 'reopened_decision': decision})
        (output / 'scenario.json').write_text(json.dumps({'test_only': True, 'scenarios': scenarios,
            'public_test_trust': fixture['context'][1], 'policy': vars(policy), 'binding': binding,
            'authorized': False, 'robot_ready': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    files = ['experiments/scripts/recovery_journal.py', 'experiments/scripts/recovery_journal_evidence.py',
             'experiments/scripts/recovery_lock_probe.py', 'experiments/scripts/validity_probe.py',
             'experiments/scripts/trust_proof.py', 'tests/test_recovery_journal.py',
             'contracts/schemas/recovery-journal-v0.1.schema.json']
    environment = {'python': platform.python_version(), 'platform': platform.platform(),
                   'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}}
    (output / 'environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
    print('5 synthetic transaction boundaries verified; no private seeds exported')


if __name__ == '__main__':
    main()
