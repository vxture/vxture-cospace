"""J4 bounded read-only journal metadata observations; no trust or recovery authority."""
import argparse
from contextlib import closing
import json
import re
from pathlib import Path
import sqlite3

from experiments.scripts.recovery_journal import APP_ID
from packages.infrastructure.files import safe_path


class RecoveryAudit:
    def __init__(self, root):
        self.root = Path(root)

    def scan(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('limit must be 1..200')
        report = {'schema_version': 'cospace.test-recovery-audit/0.1', 'test_only': True,
            'complete': False, 'needs_attention': True, 'control': None, 'pending': [],
            'runs': [], 'counts': {}, 'findings': [], 'proofs_verified': False,
            'history_verified': False, 'recovery_authorized': False, 'authorized': False,
            'robot_ready': False, 'observation': 'single read-only metadata snapshot; no lock ownership or validity decision'}
        try:
            path = safe_path(safe_path(self.root) / 'journal-test.sqlite3')
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA query_only=ON')
                db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 256 * 1024)
                budget = [1000]
                def progress():
                    budget[0] -= 1
                    return int(budget[0] <= 0)
                db.set_progress_handler(progress, 1000)
                db.execute('BEGIN')
                if (db.execute('PRAGMA application_id').fetchone()[0] != APP_ID
                        or db.execute('PRAGMA user_version').fetchone()[0] != 3):
                    raise ValueError('unsupported_store')
                controls = db.execute('SELECT store_id,context,generation,mode,revision,state_sha256 FROM control LIMIT 2').fetchall()
                if len(controls) != 1:
                    raise ValueError('invalid_control')
                report['control'] = dict(controls[0])
                control = report['control']
                if (not isinstance(control['store_id'], str) or not re.fullmatch('[0-9a-f-]{36}', control['store_id'])
                        or any(not isinstance(control[k], str) or not re.fullmatch('[0-9a-f]{64}', control[k]) for k in ('context', 'state_sha256'))
                        or type(control['generation']) is not int or not 1 <= control['generation'] <= 9007199254740991
                        or type(control['revision']) is not int or not 0 <= control['revision'] <= 9007199254740991):
                    raise ValueError('invalid_control')
                for table in ('messages', 'intents', 'receipts', 'states', 'recovery_runs', 'recovery_plans'):
                    count = db.execute(f'SELECT count(*) FROM (SELECT 1 FROM {table} LIMIT ?)', (limit + 1,)).fetchone()[0]
                    if count > limit:
                        raise ValueError('audit_limit')
                    report['counts'][table] = count
                pending = db.execute('SELECT i.intent_id,i.message_sha256,i.generation,i.prepared_revision,m.kind,m.identity FROM intents i LEFT JOIN messages m ON m.digest=i.message_sha256 LEFT JOIN receipts r USING(intent_id) WHERE r.intent_id IS NULL ORDER BY i.intent_id LIMIT ?', (limit + 1,)).fetchall()
                report['pending'] = [dict(r) for r in pending]
                report['runs'] = [dict(r) for r in db.execute('SELECT recovery_id,generation,phase FROM recovery_runs ORDER BY recovery_id LIMIT ?', (limit + 1,))]
                if any(r['phase'] not in ('blocked', 'planned', 'reconciled') or type(r['generation']) is not int
                       or not 1 <= r['generation'] <= control['generation'] for r in report['runs']):
                    raise ValueError('invalid_recovery_run')
                if db.execute('SELECT 1 FROM intents i LEFT JOIN messages m ON m.digest=i.message_sha256 WHERE m.digest IS NULL LIMIT 1').fetchone():
                    raise ValueError('message_reference_missing')
                if db.execute('SELECT 1 FROM receipts r LEFT JOIN intents i USING(intent_id) WHERE i.intent_id IS NULL LIMIT 1').fetchone():
                    raise ValueError('intent_reference_missing')
                mode = report['control']['mode']
                active = [r for r in report['runs'] if r['phase'] != 'reconciled']
                if (mode not in ('normal', 'recovering') or len(active) != int(mode == 'recovering')
                        or (active and active[0]['generation'] != report['control']['generation'])):
                    raise ValueError('recovery_control_inconsistent')
                report['complete'] = True
                report['needs_attention'] = bool(pending or active)
        except (OSError, ValueError, sqlite3.Error) as error:
            # Partial counts are observations, never a cleanup list.
            report['findings'].append({'code': str(error) if isinstance(error, ValueError) else 'store_unreadable'})
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    try:
        report = RecoveryAudit(args.root).scan(args.limit)
    except ValueError as error:
        print(json.dumps({'error': str(error), 'recovery_authorized': False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] and not report['needs_attention'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
