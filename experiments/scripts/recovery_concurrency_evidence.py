"""Reproduce cross-process in-flight query and recovery ordering; synthetic only."""
import hashlib
import json
from pathlib import Path
import platform
import tempfile

from experiments.scripts.recovery_concurrency import SessionChild
from tests.test_recovery_session import consumer
from tests.test_recovery_state import recovery, pending, plan
from tests.test_validity_probe import gate, proofs
from tests.test_recovery_concurrency import request


def main():
    output = Path('experiments/runs/p2-recovery-concurrency-001')
    output.mkdir(parents=True, exist_ok=True)
    scenarios = []
    for revoked in (False, True):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = consumer.__wrapped__(recovery.__wrapped__(gate.__wrapped__(root), root), root)
            with SessionChild(request(fixture, root)) as child:
                opened = child.receive()
                child.send('query_after_gate')
                barrier = child.receive()
                assert barrier['barrier'] == 'gate_passed'
                pending(fixture, None if revoked else proofs(fixture)[0])
                _, proposed = plan(fixture)
                result = fixture['journal'].commit_recovery(proposed)
                child.send('release')
                inflight = child.receive()
                child.send('query')
                denied = child.receive()
                assert denied['error'] == 'stale_generation'
                assert inflight['query']['session_generation'] == 1
                child.send('fresh_query')
                fresh = child.receive()
                assert (fresh.get('error') == 'session_not_allowed') if revoked else fresh['query']['session_generation'] == 3
                child.send('exit')
                assert child.process.wait(timeout=10) == 0
                scenarios.append({'revoked': revoked, 'opened': opened, 'barrier': barrier,
                    'recovery': result, 'late_reply': inflight, 'subsequent_old_query': denied, 'fresh': fresh})
    (output / 'scenario.json').write_text(json.dumps({'test_only': True, 'scenarios': scenarios,
        'authorized': False, 'robot_ready': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    files = ['experiments/scripts/recovery_concurrency.py', 'experiments/scripts/recovery_concurrency_evidence.py',
             'tests/test_recovery_concurrency.py', 'experiments/scripts/recovery_session.py',
             'experiments/scripts/recovery_state.py', 'experiments/scripts/recovery_journal.py',
             'experiments/scripts/validity_probe.py']
    (output / 'environment.json').write_text(json.dumps({'python': platform.python_version(),
        'platform': platform.platform(), 'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in files}}, indent=2), encoding='utf-8')
    print('2 cross-process in-flight scenarios verified; late reply allowed, subsequent old query denied')


if __name__ == '__main__':
    main()
