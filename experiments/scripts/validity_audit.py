"""Bounded read-only observations of the experimental validity ledger; no recovery."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3

from experiments.scripts.trust_proof import MAX_TOKEN, ROLES, limited_json
from packages.data.imports import sha
from packages.infrastructure.files import safe_path


class AuditLimit(ValueError):
    pass


class ValidityAudit:
    def __init__(self, root):
        # Never initialize a ValidityStore or open its writable connection.
        self.root = Path(root)

    def scan(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('limit must be 1..200')
        findings, pending, retained = [], [], []
        complete = True
        fingerprint = None
        database_observed = False

        def finding(code, location):
            findings.append({'code': code, 'location': location})

        try:
            root = safe_path(self.root)
            path = safe_path(root / 'validity-test.sqlite3')
            if not path.is_file():
                raise ValueError('existing ledger required')
            # ro avoids creation/repair; query_only is an additional guard.
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                try:
                    db.execute('PRAGMA query_only=ON')
                    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_TOKEN * 4)
                    budget = [1000]
                    def progress():
                        budget[0] -= 1
                        return int(budget[0] <= 0)
                    db.set_progress_handler(progress, 1000)
                    db.execute('BEGIN')
                    config = db.execute('SELECT fingerprint FROM config LIMIT 2').fetchall()
                    if (len(config) != 1 or not isinstance(config[0][0], str)
                            or not re.fullmatch('[0-9a-f]{64}', config[0][0])):
                        raise ValueError('invalid context fingerprint')
                    fingerprint = config[0][0]
                    rows = db.execute('SELECT identity,content,status,grant_proof FROM states ORDER BY identity LIMIT ?', (limit + 1,)).fetchall()
                    if len(rows) > limit:
                        raise AuditLimit('row limit')
                    total = 0
                    for identity, *tokens in rows:
                        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
                            raise ValueError('invalid identity')
                        for kind, token in zip(('content_statement', 'status_snapshot', 'capability_grant'), tokens):
                            if token is None:
                                continue
                            if not isinstance(token, str) or len(token) > MAX_TOKEN:
                                raise AuditLimit('token size or type')
                            raw = token.encode('ascii')
                            total += len(raw)
                            if total > 4 * 1024 * 1024:
                                raise AuditLimit('total token bytes')
                            retained.append({'identity': identity, 'kind': kind, 'token_sha256': sha(raw)})
                    database_observed = True
                finally:
                    # Connection context managers do not close SQLite connections.
                    db.close()
        except (OSError, ValueError, sqlite3.Error, UnicodeError):
            complete = False
            retained.clear()
            finding('database_observation_incomplete', 'validity-test.sqlite3')

        try:
            area = safe_path(safe_path(self.root) / 'pending')
            if area.exists():
                with os.scandir(area) as entries:
                    for count, entry in enumerate(entries, 1):
                        if count > limit:
                            raise AuditLimit('entry limit')
                        item = {'path': 'pending/' + entry.name, 'classification': 'unresolved_entry',
                                'retained_token_matches': []}
                        pending.append(item)
                        try:
                            path = safe_path(entry.path)
                            if (not re.fullmatch('[0-9a-f]{32}\\.json', entry.name)
                                    or not entry.is_file(follow_symlinks=False)):
                                raise ValueError('unexpected name or type')
                            with path.open('rb') as stream:
                                raw = stream.read(1025)
                            if len(raw) > 1024:
                                raise AuditLimit('marker bytes')
                            doc = limited_json(raw)
                            if (not isinstance(doc, dict) or set(doc) != {'kind', 'token_sha256'}
                                    or not isinstance(doc['kind'], str) or doc['kind'] not in ROLES
                                    or not isinstance(doc['token_sha256'], str)
                                    or not re.fullmatch('[0-9a-f]{64}', doc['token_sha256'])):
                                raise ValueError('invalid marker')
                            item.update(kind=doc['kind'], token_sha256=doc['token_sha256'], marker_sha256=sha(raw))
                            item['retained_token_matches'] = [r['identity'] for r in retained
                                if r['kind'] == doc['kind'] and r['token_sha256'] == doc['token_sha256']]
                            item['classification'] = ('retained_digest_match' if item['retained_token_matches']
                                                      else 'not_in_retained_snapshot') if database_observed else 'database_unknown'
                        except (OSError, ValueError, UnicodeError):
                            complete = False
                            finding('unreadable_or_unexpected_entry', item['path'])
        except (OSError, ValueError):
            complete = False
            finding('pending_inventory_incomplete', 'pending')

        return {'schema_version': 'cospace.test-validity-audit/0.1', 'test_only': True,
                'complete': complete, 'needs_attention': bool(pending or findings),
                'database_observed': database_observed, 'context_fingerprint': fingerprint,
                'proofs_verified': False, 'cleanup_authorized': False, 'recovery_authorized': False,
                'authorized': False, 'robot_ready': False,
                'observation': 'database snapshot and separate filesystem observations; writer ownership unknown',
                'retained_proof_count': len(retained), 'pending': sorted(pending, key=lambda p: p['path']),
                'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    try:
        report = ValidityAudit(args.root).scan(args.limit)
    except ValueError as error:
        print(json.dumps({'error': str(error), 'recovery_authorized': False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] and not report['needs_attention'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
