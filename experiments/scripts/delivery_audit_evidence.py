"""Unified read-only diagnostic evidence over temporary synthetic stores."""
import hashlib
import json
from pathlib import Path
import platform
import tempfile

from experiments.scripts.delivery_audit import DeliveryAudit
from tests.test_recovery_session import consumer
from tests.test_recovery_state import recovery, pending, plan
from tests.test_validity_probe import gate, proofs


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='experiments/runs/p2-delivery-audit-001')
    output = Path(parser.parse_args().output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixture = consumer.__wrapped__(recovery.__wrapped__(gate.__wrapped__(root), root), root)
        auditor = DeliveryAudit(fixture['files'].root, fixture['journal'].root)
        def scan():
            return auditor.scan(fixture['binding'])
        clean = scan()
        assert clean['complete'] and not clean['needs_attention']
        pending(fixture, proofs(fixture, sequence=2)[0])
        interrupted = scan()
        _, proposed = plan(fixture)
        planned = scan()
        fixture['journal'].commit_recovery(proposed)
        recovered = scan()
        assert 'proof_fields_missing' in {f['code'] for f in recovered['findings']}
        result = {'test_only': True, 'scenarios': {'clean': clean, 'pending': interrupted,
            'planned': planned, 'reconciled_missing_grant': recovered}, 'authorized': False, 'robot_ready': False}
        (output / 'scenario.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    files = ['experiments/scripts/delivery_audit.py', 'experiments/scripts/delivery_audit_evidence.py',
             'experiments/scripts/recovery_audit.py', 'packages/infrastructure/agent_audit.py',
             'tests/test_delivery_audit.py', 'packages/data/delivery_report.py',
             'packages/service/delivery.py', 'tests/test_delivery_context.py',
             'tests/test_delivery_reading.py',
             'contracts/schemas/delivery-generation-v0.1.schema.json']
    (output / 'environment.json').write_text(json.dumps({'python': platform.python_version(),
        'platform': platform.platform(), 'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in files}}, indent=2), encoding='utf-8')
    print('4 unified diagnostic observations verified; validity not evaluated; no repair authority')


if __name__ == '__main__':
    main()
