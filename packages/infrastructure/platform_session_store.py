"""Encrypted single-host RP storage; no application-defined login expiration.

SQLite transactions + per-session OS locks work across local server processes.
This adapter is not a distributed Redis store or a production HA deployment.
"""
from contextlib import contextmanager, closing
import hashlib
import json
from pathlib import Path
import sqlite3
from cryptography.fernet import Fernet, InvalidToken
from packages.infrastructure.platform_identity import IdentityUnavailable
from packages.lifecycle.preview_control_lock import mutation_guard


def key_of(value): return hashlib.sha256(value.encode()).hexdigest()


class LocalRpStore:
    def __init__(self, root, encryption_key):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root/'rp.sqlite3'
        self.cipher = Fernet(encryption_key.encode())
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, value BLOB NOT NULL, PRIMARY KEY(kind,key))')

    @contextmanager
    def db(self):
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                with db: yield db
        except (sqlite3.Error, InvalidToken) as exc:
            raise IdentityUnavailable('session_store_unavailable') from exc

    def get(self, kind, key):
        with self.db() as db:
            row = db.execute('SELECT value FROM records WHERE kind=? AND key=?', (kind, key_of(key))).fetchone()
            return json.loads(self.cipher.decrypt(row[0])) if row else None

    def put(self, kind, key, value):
        encrypted = self.cipher.encrypt(json.dumps(value).encode())
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)', (kind, key_of(key), encrypted))

    def delete(self, kind, key):
        with self.db() as db: db.execute('DELETE FROM records WHERE kind=? AND key=?', (kind, key_of(key)))

    def take_state(self, state, browser, now):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM records WHERE kind=? AND key=?', ('state', key_of(state))).fetchone()
            if not row: return None
            value = json.loads(self.cipher.decrypt(row[0]))
            if value['browser'] != key_of(browser): return None
            db.execute('DELETE FROM records WHERE kind=? AND key=?', ('state', key_of(state)))
            return value if value['expires_at'] > now else None

    def lock(self, session): return mutation_guard(self.root/'locks'/key_of(session))
