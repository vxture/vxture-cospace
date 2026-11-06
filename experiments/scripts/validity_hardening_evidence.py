"""Reproduce the synthetic delegation/fault scenario; never export private seeds."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import tempfile

from experiments.scripts.validity_probe import ValidityStore
from tests.test_validity_probe import gate, proofs, CAP
from tests.test_validity_hardening import delegated, install_proofs


def main():
    output = Path('experiments/runs/p2-validity-hardening-001')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = gate.__wrapped__(root)
        trust, certificate, public = delegated(fixture, root)
        store = ValidityStore(root / 'delegated', trust, fixture['policy'], bootstrap=True)
        install_proofs(fixture, store)
        allowed = store.decide(fixture['binding'], CAP, fixture['clock'])
        def fail():
            raise sqlite3.OperationalError('injected commit failure')
        store._before_commit = fail
        revoked, _ = proofs(fixture, sequence=2, state='revoked')
        try:
            store.accept(fixture['binding'], revoked, 'status_snapshot')
        except sqlite3.OperationalError:
            pass
        reopened = ValidityStore(store.root, trust, fixture['policy'])
        denied = reopened.decide(fixture['binding'], CAP, fixture['clock'])
        assert allowed['simulated_allowed'] and allowed['deadline'] == 125
        assert denied['reason'] == 'storage_error'
        result = {'test_only': True, 'root_public_key_hex': public.hex(),
                  'delegation_jws': certificate, 'expected_deployment': 'test-deployment',
                  'expected_version': 1, 'policy': asdict(fixture['policy']),
                  'allowed': allowed, 'reopened_after_failed_commit': denied,
                  'pending_count': len(list(store.pending.iterdir())),
                  'authorized': False, 'robot_ready': False}
        (output / 'scenario.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    sources = ['experiments/scripts/trust_proof.py', 'experiments/scripts/validity_probe.py',
               'experiments/scripts/delegation_probe.py', 'experiments/scripts/validity_hardening_evidence.py',
               'contracts/schemas/test-delegation-v0.1.schema.json',
               'tests/test_validity_probe.py', 'tests/test_validity_hardening.py']
    environment = {'python': platform.python_version(), 'platform': platform.platform(),
                   'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                   'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}}
    (output / 'environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
    print('synthetic deadline=125; reopened gate=storage_error; private seeds not exported')


if __name__ == '__main__':
    main()
