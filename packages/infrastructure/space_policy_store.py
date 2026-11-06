"""Single-host, revisioned space policy. Trusted administrative CLI only."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from packages.service.space_access import SpaceAccessPolicy
from packages.infrastructure.platform_identity import IdentityUnavailable


class SpacePolicyStore:
    def __init__(self, root):
        self.path = Path(root).resolve()/'space-policy.sqlite3'

    def load(self):
        try:
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)) as db:
                row = db.execute('SELECT revision,policy FROM policy WHERE id=1').fetchone()
                if not row: raise ValueError('policy_missing')
                return row[0], SpaceAccessPolicy.model_validate_json(row[1])
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise IdentityUnavailable('space_policy_unavailable') from exc

    def replace(self, policy, *, expected_revision, actor, reason):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            with db:
                db.execute('BEGIN IMMEDIATE')
                return self.write_transaction(db,policy,expected_revision=expected_revision,actor=actor,reason=reason)

    @staticmethod
    def write_transaction(db, policy, *, expected_revision, actor, reason):
        """Write inside the caller's transaction; permits atomic initialization receipt + binding.

        Caller owns BEGIN/COMMIT. This does not authorize a browser operation.
        """
        if not isinstance(policy, SpaceAccessPolicy) or type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('invalid_policy_change')
        if not isinstance(actor,str) or not 1 <= len(actor.strip()) <= 200 or not isinstance(reason,str) or not 1 <= len(reason.strip()) <= 500:
            raise ValueError('administrative_actor_and_reason_required')
        db.execute('CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY, revision INTEGER,policy TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS history(revision INTEGER PRIMARY KEY,record TEXT)')
        current=db.execute('SELECT revision FROM policy WHERE id=1').fetchone()
        revision=current[0] if current else 0
        if expected_revision != revision: raise ValueError('policy_revision_changed')
        revision+=1
        record={'revision':revision,'actor':actor.strip(),'reason':reason.strip(),
            'changed_at':datetime.now(timezone.utc).isoformat(),'policy':policy.model_dump()}
        db.execute('INSERT OR REPLACE INTO policy VALUES(1,?,?)',(revision,policy.model_dump_json()))
        db.execute('INSERT INTO history VALUES(?,?)',(revision,json.dumps(record,ensure_ascii=False)))
        return revision
