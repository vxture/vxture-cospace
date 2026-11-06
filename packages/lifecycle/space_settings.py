"""Revisioned directory display metadata; never changes geometry or releases."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettingsUnavailable(RuntimeError):
    pass


class SettingsConflict(ValueError):
    pass


class SpaceSettingsChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=500)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('name', 'reason')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('text_required')
        return value.strip()


class SpaceSettings:
    def __init__(self, root):
        self.path = Path(root) / 'space-settings.sqlite3'

    def read(self, space_id):
        if not self.path.exists():
            return {'revision': 0, 'history': []}
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                row = db.execute('SELECT record FROM settings WHERE space_id=?', (space_id,)).fetchone()
                return json.loads(row[0]) if row else {'revision': 0, 'history': []}
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise SettingsUnavailable('space_settings_unavailable') from exc

    def change(self, change: SpaceSettingsChange, actor, original):
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS settings(space_id TEXT PRIMARY KEY, record TEXT NOT NULL)')
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT record FROM settings WHERE space_id=?', (change.space_id,)).fetchone()
                    saved = json.loads(row[0]) if row else {'revision': 0, 'history': []}
                    if saved['revision'] != change.expected_revision:
                        raise SettingsConflict('space_settings_revision_changed')
                    before = {k: saved.get(k, original[k]) for k in ('name', 'description')}
                    after = {'name': change.name, 'description': change.description.strip()}
                    if before == after:
                        return saved
                    event = {'revision': saved['revision']+1, 'actor': actor,
                             'changed_at': datetime.now(timezone.utc).isoformat(),
                             'reason': change.reason, 'before': before, 'after': after}
                    record = after | {'revision': event['revision'], 'history': saved['history']+[event]}
                    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',
                               (change.space_id, json.dumps(record, ensure_ascii=False)))
                    return record
        except (OSError, sqlite3.Error) as exc:
            raise SettingsUnavailable('space_settings_unavailable') from exc
