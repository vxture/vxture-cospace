"""Workspace-scoped registration only; never grants device or service access."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RecipientConflict(ValueError):
    pass


class RecipientsUnavailable(RuntimeError):
    pass


class Relation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    purposes: list[Literal['collect', 'use']] = Field(min_length=1, max_length=2)
    usage_modes: list[Literal['online', 'offline']] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def valid(self):
        if len(set(self.purposes)) != len(self.purposes) or len(set(self.usage_modes)) != len(self.usage_modes):
            raise ValueError('duplicate_recipient_option')
        if 'use' not in self.purposes and self.usage_modes:
            raise ValueError('usage_mode_requires_use')
        self.purposes.sort()
        self.usage_modes.sort()
        return self


class RecipientChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=100)
    morphology: Literal['aerial', 'quadruped', 'wheeled', 'tracked', 'humanoid', 'other']
    morphology_note: str = Field(default='', max_length=200)
    manufacturer: str = Field(default='', max_length=100)
    model: str = Field(default='', max_length=100)
    external_id: str = Field(default='', max_length=160)
    contact: str = Field(default='', max_length=100)
    relations: list[Relation] = Field(default_factory=list, max_length=100)

    @field_validator('name', 'morphology_note', 'manufacturer', 'model', 'external_id', 'contact')
    @classmethod
    def trim(cls, value, info):
        value = value.strip()
        if info.field_name == 'name' and not value:
            raise ValueError('recipient_name_required')
        return value

    @model_validator(mode='after')
    def valid(self):
        if self.morphology == 'other' and not self.morphology_note:
            raise ValueError('morphology_note_required')
        if len({r.space_id for r in self.relations}) != len(self.relations):
            raise ValueError('duplicate_recipient_space')
        self.relations.sort(key=lambda r: r.space_id)
        return self


class ServiceRecipients:
    def __init__(self, root):
        self.path = Path(root) / 'service-recipients.sqlite3'

    @staticmethod
    def scope(principal):
        return json.dumps([principal.issuer, principal.org_id, principal.workspace_id], separators=(',', ':'))

    @staticmethod
    def permissions(principal, policy, spaces):
        visible = {s['id'] for s in spaces if 'recipient.read' in policy.capabilities(principal, s['id'])}
        managed = {s['id'] for s in spaces if 'recipient.manage' in policy.capabilities(principal, s['id'])}
        return visible, managed

    @staticmethod
    def access(record, principal, visible, managed):
        links = {r['space_id'] for r in record['relations']}
        unassigned = not links and (principal.workspace_owner or record['created_by'] == principal.subject and bool(managed))
        return bool(links & visible) or unassigned, bool(managed or principal.workspace_owner) and (links <= managed if links else unassigned)

    @staticmethod
    def decode(raw):
        try:
            record = json.loads(raw)
            if set(record) != set(RecipientChange.model_fields) | {'id','revision','created_by','created_at','updated_at'}:
                raise ValueError('record_fields_invalid')
            RecipientChange.model_validate({k: record[k] for k in RecipientChange.model_fields})
            if type(record['revision']) is not int or record['revision'] < 1:
                raise ValueError('revision_invalid')
            for key in ('id', 'created_by', 'created_at', 'updated_at'):
                if not isinstance(record[key], str):
                    raise ValueError('record_invalid')
            if not re.fullmatch(r'agent-[a-f0-9]{32}', record['id']):
                raise ValueError('record_identity_invalid')
            for key in ('created_at','updated_at'):
                if datetime.fromisoformat(record[key]).tzinfo is None:
                    raise ValueError('record_time_invalid')
            return record
        except (ValueError, KeyError, TypeError) as exc:
            raise RecipientsUnavailable() from exc

    def list(self, principal, policy, spaces, *, space_id=None, offset=0, limit=50, query='', morphology='', purpose=''):
        visible, managed = self.permissions(principal, policy, spaces)
        if space_id and space_id not in visible:
            raise PermissionError()
        records = []
        try:
            if self.path.exists():
                with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                    rows = db.execute('SELECT record FROM recipients WHERE scope=? ORDER BY updated DESC, id', (self.scope(principal),))
                    for row in rows:
                        record = self.decode(row[0])
                        allowed, can_manage = self.access(record, principal, visible, managed)
                        if not allowed or space_id and not any(r['space_id'] == space_id for r in record['relations']):
                            continue
                        if morphology and record['morphology'] != morphology:
                            continue
                        public_relations = [r for r in record['relations'] if r['space_id'] in visible]
                        if purpose and not any(purpose in r['purposes'] for r in public_relations if not space_id or r['space_id'] == space_id):
                            continue
                        if query.strip().casefold() not in ' '.join(record[k] for k in ('name','id','external_id','manufacturer','model')).casefold():
                            continue
                        records.append({k: v for k, v in record.items() if k not in ('request_id', 'expected_revision', 'created_by')} | {
                            'relations': public_relations,
                            'can_manage': can_manage, 'integration_state': 'pending', 'external_identity_verified': False})
        except PermissionError:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise RecipientsUnavailable() from exc
        return {'profile': 'cospace.service-recipients/0.1', 'recipients': records[offset:offset+limit],
                'total': len(records), 'offset': offset, 'limit': limit,
                'can_create': principal.workspace_owner or bool(managed),
                'spaces': [{'id': s['id'], 'name': s['name'], 'can_manage': s['id'] in managed}
                           for s in spaces if s['id'] in visible]}

    def save(self, principal, policy, spaces, change, identity=None):
        visible, managed = self.permissions(principal, policy, spaces)
        if not (principal.workspace_owner or managed) or any(r.space_id not in managed for r in change.relations):
            raise PermissionError()
        scope = self.scope(principal)
        digest = hashlib.sha256(json.dumps({'id': identity, 'body': change.model_dump()}, sort_keys=True).encode()).hexdigest()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS recipients (scope TEXT, id TEXT, record TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(scope,id))')
                db.execute('CREATE TABLE IF NOT EXISTS recipient_requests (scope TEXT, actor TEXT, request TEXT, digest TEXT, result TEXT, PRIMARY KEY(scope,actor,request))')
                db.execute('CREATE TABLE IF NOT EXISTS recipient_history (scope TEXT, id TEXT, revision INTEGER, actor TEXT, changed_at TEXT, before_record TEXT, after_record TEXT, PRIMARY KEY(scope,id,revision))')
                db.execute('BEGIN IMMEDIATE')
                previous_request = db.execute('SELECT digest,result FROM recipient_requests WHERE scope=? AND actor=? AND request=?', (scope, principal.subject, change.request_id)).fetchone()
                if previous_request:
                    if previous_request[0] != digest:
                        raise RecipientConflict('recipient_request_reused')
                    result = self.decode(previous_request[1])
                    if not self.access(result, principal, visible, managed)[1]:
                        raise PermissionError()
                    return result
                previous = None
                if identity:
                    row = db.execute('SELECT record FROM recipients WHERE scope=? AND id=?', (scope, identity)).fetchone()
                    if not row:
                        raise PermissionError()
                    previous = self.decode(row[0])
                    if not self.access(previous, principal, visible, managed)[1]:
                        raise PermissionError()
                if change.expected_revision != (previous['revision'] if previous else 0):
                    raise RecipientConflict('recipient_revision_changed')
                if not previous and db.execute('SELECT COUNT(*) FROM recipients WHERE scope=?', (scope,)).fetchone()[0] >= 10000:
                    raise RecipientsUnavailable()
                now = datetime.now(timezone.utc).isoformat()
                result = change.model_dump() | {'id': identity or 'agent-'+uuid4().hex,
                    'revision': (previous['revision'] if previous else 0)+1,
                    'created_by': previous['created_by'] if previous else principal.subject,
                    'created_at': previous['created_at'] if previous else now, 'updated_at': now}
                raw = json.dumps(result, ensure_ascii=False)
                db.execute('INSERT OR REPLACE INTO recipients VALUES (?,?,?,?)', (scope, result['id'], raw, now))
                db.execute('INSERT INTO recipient_requests VALUES (?,?,?,?,?)', (scope, principal.subject, change.request_id, digest, raw))
                db.execute('INSERT INTO recipient_history VALUES (?,?,?,?,?,?,?)',
                           (scope, result['id'], result['revision'], principal.subject, now, json.dumps(previous), raw))
                return result
        except PermissionError:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise RecipientsUnavailable() from exc
