"""Bounded tenant-scoped observations, never credentials or spatial payloads."""
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import math
import sqlite3
import time

RETENTION = 7 * 86400
MAX_EVENTS = 100000
WINDOW = 86400


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class ServiceMonitor:
    def __init__(self, root, *, now=time.time):
        self.path = Path(root) / 'service-observations.sqlite3'
        self.now = now
        self.write_failed_at = None

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=0.2)
        try:
            with db:
                self.initialize(db)
                yield db
        finally:
            db.close()

    def initialize(self, db):
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value REAL NOT NULL)')
        db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('started_at', self.now()))
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
            issuer TEXT NOT NULL, org TEXT NOT NULL, workspace TEXT NOT NULL,
            space TEXT NOT NULL, caller TEXT NOT NULL, publication TEXT NOT NULL,
            outcome TEXT NOT NULL, http_status INTEGER NOT NULL, duration_ms REAL NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS scoped_events ON events(issuer,org,workspace,space,at)')
        db.execute('CREATE INDEX IF NOT EXISTS event_time ON events(at)')

    def prune(self, db, now):
        db.execute('DELETE FROM events WHERE at < ?', (now - RETENTION,))
        cutoff = db.execute('SELECT MAX(id)-? FROM events', (MAX_EVENTS,)).fetchone()[0]
        if cutoff is not None and cutoff > 0:
            discarded = db.execute('SELECT MAX(at) FROM events WHERE id<=?', (cutoff,)).fetchone()[0]
            if discarded is not None:
                db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('truncated_before', discarded))
                db.execute('DELETE FROM events WHERE id<=?', (cutoff,))

    def record(self, scope, publication, outcome, http_status, duration_ms):
        now = self.now()
        try:
            with self.connect() as db:
                db.execute('INSERT INTO events(at,issuer,org,workspace,space,caller,publication,outcome,http_status,duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (now, *scope, publication, outcome, http_status, round(duration_ms, 2)))
                self.prune(db, now)
        except (OSError, sqlite3.Error):
            # Telemetry failure must not change the authorization or query result.
            self.write_failed_at = now

    def snapshot(self, principal, space):
        now = self.now()
        scope = (principal.issuer, principal.org_id, principal.workspace_id, space)
        with self.connect() as db:
            self.prune(db, now)
            meta = dict(db.execute('SELECT key,value FROM metadata').fetchall())
            rows = db.execute('SELECT at,caller,publication,outcome,http_status,duration_ms FROM events WHERE issuer=? AND org=? AND workspace=? AND space=? AND at>=? AND at<=? ORDER BY at DESC,id DESC',
                              (*scope, now - WINDOW, now)).fetchall()
        counts = {'historical_result': 0, 'refused': 0, 'rejected': 0, 'failed': 0}
        versions = {}
        outcomes = {}
        callers = {}
        for row in rows:
            outcome = row['outcome']
            counts['historical_result' if outcome == 'historical_result' else 'refused' if outcome == 'observation_time_unverified' else 'failed' if row['http_status'] >= 500 else 'rejected'] += 1
            versions[row['publication']] = versions.get(row['publication'], 0) + 1
            key = (outcome, row['http_status'])
            item = outcomes.setdefault(key, {'outcome': outcome, 'http_status': row['http_status'], 'requests': 0, 'last_at': utc(row['at'])})
            item['requests'] += 1
            caller = callers.setdefault(row['caller'], {'caller': row['caller'], 'requests': 0, 'last_at': utc(row['at']), 'last_outcome': outcome})
            caller['requests'] += 1
        durations = sorted(row['duration_ms'] for row in rows)
        return {
            'profile': 'cospace.service-monitor/0.1', 'space_id': space, 'generated_at': utc(now),
            'window': {'from': utc(now-WINDOW), 'to': utc(now)},
            'coverage': {'started_at': utc(meta['started_at']), 'truncated_before': utc(meta.get('truncated_before')),
                         'partial': meta['started_at'] > now-WINDOW or meta.get('truncated_before', 0) >= now-WINDOW or self.write_failed_at is not None,
                         'write_failed_at': utc(self.write_failed_at), 'retention_days': 7, 'max_events': MAX_EVENTS},
            'request_count': len(rows), 'counts': counts,
            'last_request_at': utc(rows[0]['at']) if rows else None,
            'p95_ms': durations[math.ceil(len(durations)*.95)-1] if durations else None,
            'versions': [{'publication_id': key, 'requests': value} for key, value in sorted(versions.items(), key=lambda item: (-item[1],item[0]))[:10]],
            'recent': [dict(row) | {'at': utc(row['at'])} for row in rows[:20]],
            'outcomes': sorted(outcomes.values(), key=lambda item: (-item['requests'], item['outcome'])),
            'callers': sorted(callers.values(), key=lambda item: (-item['requests'], item['caller']))[:100],
        }
