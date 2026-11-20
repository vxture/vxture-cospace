"""Replaceable SQLite authoring adapter; no platform, scene or identity imports.

The portable authoring use cases depend only on transaction(scope), not SQLite.
This first bounded adapter stores one atomic state per injected scope. It is not
a large-catalog index or a production multitenant authorization boundary.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .kernel import canonical_bytes
from .kernel.authoring import AuthoringError

MAX_STATE_BYTES = 16 * 1024 * 1024


class SQLiteAuthoringPort:
    def __init__(self, root):
        self.path = Path(root) / 'ontology-authoring.sqlite3'

    @contextmanager
    def transaction(self, scope):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = sha256(scope.encode('utf-8')).hexdigest()
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS authoring_state (scope TEXT PRIMARY KEY, payload BLOB NOT NULL)')
            connection.commit()
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT payload FROM authoring_state WHERE scope=?', (key,)).fetchone()
            original = row[0] if row else None
            if original is not None and len(original) > MAX_STATE_BYTES:
                raise AuthoringError('state_budget')
            try:
                state = json.loads(original) if original else {}
                if type(state) is not dict or any(type(v) is not dict for v in state.values()):
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise AuthoringError('store_corrupt') from None
            yield state
            raw = canonical_bytes(state)
            if len(raw) > MAX_STATE_BYTES:
                raise AuthoringError('state_budget')
            if raw != original:
                connection.execute('INSERT INTO authoring_state(scope,payload) VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET payload=excluded.payload', (key, raw))
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise AuthoringError('store_unavailable') from None
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
