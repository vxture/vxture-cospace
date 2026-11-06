"""J4 synthetic file-session and journal-audit evidence; no private seeds exported."""
import hashlib
import json
from pathlib import Path
import platform
import tempfile

from experiments.scripts.recovery_audit import RecoveryAudit
from experiments.scripts.recovery_session import RecoverySession
from experiments.scripts.validity_probe import GateError, IntervalClock
from tests.test_recovery_state import recovery, pending, plan, reopen
from tests.test_validity_probe import gate, proofs
from packages.infrastructure.agent_files import FilePackages


def main():
    output = Path('experiments/runs/p2-recovery-session-001')
    output.mkdir(parents=True, exist_ok=True)
    scenarios = []
    for kind in ('duplicate', 'revocation'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = recovery.__wrapped__(gate.__wrapped__(root), root)
            files = FilePackages(root / 'files')
            installed = files.install('examples/agent-runtime', 'examples/indoor-spatial')
            scene = fixture['binding']['scene_id']
            files.activate(scene, installed['package_sha256'], 0)
            old = RecoverySession(files, scene, fixture['journal'], fixture['binding'], fixture['clock'])
            before = old.query([1, 0, 1])
            clean = RecoveryAudit(fixture['journal'].root).scan()
            pending(fixture, proofs(fixture)[0] if kind == 'duplicate' else None)
            pending_report = RecoveryAudit(fixture['journal'].root).scan()
            rid, proposed = plan(fixture)
            planned_report = RecoveryAudit(fixture['journal'].root).scan()
            result = fixture['journal'].commit_recovery(proposed)
            try:
                old.query([1, 0, 1])
            except GateError as error:
                old_reason = error.code
            else:
                raise AssertionError('old session survived recovery')
            assert old_reason == 'stale_generation'
            fixture['journal'] = reopen(fixture)
            clock = IntervalClock(lambda: ('new-boot', 0), ('new-boot', 0, 110, 110))
            try:
                fresh = RecoverySession(files, scene, fixture['journal'], fixture['binding'], clock)
            except GateError as error:
                assert kind == 'revocation'
                after = {'open_denied': error.code}
            else:
                assert kind == 'duplicate'
                after = fresh.query([1, 0, 1])
                assert after['source'] == before['source'] and after['gate']['deadline'] == before['gate']['deadline']
                fresh.close()
            final = RecoveryAudit(fixture['journal'].root).scan()
            assert clean['complete'] and final['complete'] and not final['needs_attention']
            old.close()
            scenarios.append({'kind': kind, 'binding': fixture['binding'], 'before': before,
                'audit_clean': clean, 'audit_pending': pending_report, 'audit_planned': planned_report,
                'recovery_result': result, 'old_session_denied': old_reason, 'after': after, 'audit_final': final})
    (output / 'scenario.json').write_text(json.dumps({'test_only': True, 'authorized': False,
        'robot_ready': False, 'scenarios': scenarios}, ensure_ascii=False, indent=2), encoding='utf-8')
    paths = ['experiments/scripts/recovery_session.py', 'experiments/scripts/recovery_audit.py',
             'experiments/scripts/recovery_session_evidence.py', 'experiments/scripts/recovery_state.py',
             'experiments/scripts/recovery_journal.py', 'experiments/scripts/validity_probe.py',
             'tests/test_recovery_session.py']
    (output / 'environment.json').write_text(json.dumps({'python': platform.python_version(),
        'platform': platform.platform(), 'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in paths}}, indent=2), encoding='utf-8')
    print('2 integrated file-session scenarios verified; old sessions fenced; metadata audit read-only')


if __name__ == '__main__':
    main()
