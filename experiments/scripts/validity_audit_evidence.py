"""Save synthetic read-only audit observations, without private keys or test stores."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import tempfile

from experiments.scripts.validity_audit import ValidityAudit
from packages.data.imports import canonical, sha
from tests.test_validity_probe import gate, proofs


def main():
    output = Path('experiments/runs/p2-validity-audit-001')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        fixture = gate.__wrapped__(Path(temporary))
        store = fixture['store']
        clean = ValidityAudit(store.root).scan()
        status, _ = proofs(fixture)
        matched = store.pending / ('a' * 32 + '.json')
        matched.write_bytes(canonical({'kind': 'status_snapshot', 'token_sha256': sha(status.encode('ascii'))}))
        def fail():
            raise sqlite3.OperationalError('injected commit failure')
        store._before_commit = fail
        revoked, _ = proofs(fixture, sequence=2, state='revoked')
        try:
            store.accept(fixture['binding'], revoked, 'status_snapshot')
        except sqlite3.OperationalError:
            pass
        before = {p.name: p.read_bytes() for p in store.pending.iterdir()}
        report = ValidityAudit(store.root).scan()
        assert before == {p.name: p.read_bytes() for p in store.pending.iterdir()}
        assert {p['classification'] for p in report['pending']} == {'retained_digest_match', 'not_in_retained_snapshot'}
        (output / 'scenario.json').write_text(json.dumps({'clean': clean, 'pending': report,
            'marker_bytes_unchanged': True}, ensure_ascii=False, indent=2), encoding='utf-8')
    sources = ['experiments/scripts/validity_audit.py', 'experiments/scripts/validity_probe.py',
               'experiments/scripts/validity_audit_evidence.py', 'tests/test_validity_audit.py']
    environment = {'python': platform.python_version(), 'platform': platform.platform(),
                   'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}}
    (output / 'environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
    print('read-only audit: retained digest match and absent digest; markers unchanged; no recovery authorization')


if __name__ == '__main__':
    main()
