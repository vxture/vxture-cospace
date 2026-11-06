"""Revisioned display metadata, kept outside immutable input bindings."""
from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DescriptionConflict(ValueError):
    pass


class DescriptionUnavailable(RuntimeError):
    pass


class DescriptionChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    expected_revision: int = Field(ge=0)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=500)
    intended_use: str = Field(max_length=500)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('display_name', 'reason')
    @classmethod
    def required_text(cls, value):
        if not value.strip():
            raise ValueError('text_required')
        return value.strip()


class InputDescriptions:
    def __init__(self, catalog):
        self.catalog = catalog
        self.path = catalog.root / 'input-descriptions.sqlite3'

    def original(self, identity, space_id):
        original = self.catalog.read(identity)
        if not space_id or original.get('space_id') != space_id:
            raise PermissionError('input_not_in_space')
        return original

    def initial(self, original):
        return {'profile': 'cospace.input-description/0.1', 'space_id': original['space_id'],
                'input_id': original['id'], 'original_name': original['label'], 'revision': 0,
                'display_name': original['label'], 'description': '', 'intended_use': '', 'history': []}

    def decode(self, raw, original):
        value = json.loads(raw)
        if (value['profile'] != 'cospace.input-description/0.1'
                or value['space_id'] != original['space_id'] or value['input_id'] != original['id']
                or value['original_name'] != original['label']
                or type(value['revision']) is not int or value['revision'] < 1
                or not isinstance(value['history'], list) or len(value['history']) != value['revision']):
            raise ValueError('invalid_description_record')
        fields = {k: value[k] for k in ('display_name', 'description', 'intended_use')}
        DescriptionChange(space_id=original['space_id'], expected_revision=value['revision'],
                          reason='read', **fields)
        for number, event in enumerate(value['history'], 1):
            if (event['revision'] != number or not isinstance(event['actor'], str)
                    or not event['actor'] or not event['reason'] or not event['changed_at']
                    or (number > 1 and event['before'] != value['history'][number-2]['after'])):
                raise ValueError('invalid_description_history')
        if value['history'][-1]['after'] != fields:
            raise ValueError('invalid_description_history')
        return value

    def read(self, identity, space_id):
        original = self.original(identity, space_id)
        if not self.path.exists():
            return self.initial(original)
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                row = db.execute('SELECT record FROM descriptions WHERE space_id=? AND input_id=?',
                                 (space_id, identity)).fetchone()
                return self.decode(row[0], original) if row else self.initial(original)
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            raise DescriptionUnavailable('input_descriptions_unavailable') from exc

    def change(self, identity, change, actor):
        original = self.original(identity, change.space_id)
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS descriptions(space_id TEXT NOT NULL, input_id TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY(space_id,input_id))')
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT record FROM descriptions WHERE space_id=? AND input_id=?',
                                     (change.space_id, identity)).fetchone()
                    saved = self.decode(row[0], original) if row else self.initial(original)
                    if change.expected_revision != saved['revision']:
                        raise DescriptionConflict('input_description_revision_changed')
                    keys = ('display_name', 'description', 'intended_use')
                    before = {k: saved[k] for k in keys}
                    after = {k: getattr(change, k).strip() for k in keys}
                    if before == after:
                        return saved
                    event = {'revision': saved['revision']+1, 'before': before, 'after': after,
                             'actor': actor, 'reason': change.reason,
                             'changed_at': datetime.now(timezone.utc).isoformat()}
                    result = saved | after | {'revision': event['revision'], 'history': saved['history']+[event]}
                    db.execute('INSERT OR REPLACE INTO descriptions VALUES(?,?,?)',
                               (change.space_id, identity, json.dumps(result, ensure_ascii=False)))
                    return result
        except DescriptionConflict:
            raise
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            raise DescriptionUnavailable('input_descriptions_unavailable') from exc

    def presentation(self, record):
        saved = self.read(record['id'], record['space_id'])
        return {k: saved[k] for k in ('display_name', 'description', 'intended_use', 'revision')}
