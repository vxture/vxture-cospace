"""Validation of standalone identity configuration and trusted SQLite snapshots."""
from hashlib import sha256
import json
import secrets
import sqlite3

import pytest

from packages.ontology.kernel.local_host.identity import PROFILE, TokenIdentity
from packages.ontology.kernel.local_host.storage import FILENAME, initialize, snapshot


def test_local_identity_rejects_conflicting_configs(tmp_path):
    path = tmp_path / 'identity.json'
    first, second = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    principal = {'scope': 'park-a', 'actor': 'operator',
                 'token_sha256': sha256(first.encode()).hexdigest(), 'permissions': ['configure_groups']}

    def load(principals):
        path.write_text(json.dumps({'profile': PROFILE, 'principals': principals}), encoding='utf-8')
        return TokenIdentity.load(path)

    adapter = load([principal])
    identity = adapter('Bearer ' + first)
    assert identity.authorize('park-a', 'operator', 'configure_groups')
    assert not identity.authorize('park-b', 'operator', 'configure_groups')
    assert not identity.authorize('park-a', 'operator', 'publish')
    assert adapter('Bearer ' + second) is None
    for conflict in ({**principal, 'scope': 'park-b'},
                     {**principal, 'token_sha256': sha256(second.encode()).hexdigest()},
                     {**principal, 'permissions': ['owner']}):
        with pytest.raises(ValueError, match='invalid_identity_config'):
            load([principal, conflict])
    path.write_text('{"profile":"unexpected","profile":null}', encoding='utf-8')
    with pytest.raises(ValueError, match='invalid_identity_config'):
        TokenIdentity.load(path)


def test_snapshot_and_startup_refuse_foreign_databases(tmp_path):
    source = tmp_path / 'foreign'
    source.mkdir()
    with sqlite3.connect(source / FILENAME) as database:
        database.execute('CREATE TABLE foreign_store (id INTEGER PRIMARY KEY)')
    saved = (source / FILENAME).read_bytes()
    with pytest.raises(ValueError, match='invalid_host_database'):
        initialize(source)
    with pytest.raises(ValueError, match='invalid_host_database'):
        snapshot(source, tmp_path / 'copy')
    assert not (tmp_path / 'copy').exists()
    assert saved == (source / FILENAME).read_bytes()
