"""Immutable project/workspace reference originals, independent of scenes.

Metadata, original bytes, registration and audit commit in the project database
transaction. Listing never reads blobs; uploads do not become construction inputs.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.data.scene_attachments import MAX_BYTES, reference_name
from packages.lifecycle.scene_initialization import checksum
from packages.lifecycle.workspace_projects import Change, ProjectId, ProjectError, ProjectUnavailable
from packages.data.resource_sharing_contract import ResourceId, VersionId
from packages.data.resource_storage_usage import record_scope

MAX_FILES = 1000
MAX_STORED_BYTES = 512 * 1024 * 1024


class FileUpload(Change):
    owner_kind: Literal['project', 'workspace']
    owner_project_id: ProjectId | None = None
    name: str = Field(min_length=1, max_length=160)
    is_base: bool = False

    @model_validator(mode='after')
    def valid_file(self):
        if (self.owner_kind == 'project') != bool(self.owner_project_id):
            raise ValueError('resource_owner_invalid')
        if self.expected_revision != 0:
            raise ValueError('new_file_revision_required')
        # Reuse the established opaque reference-file format/name contract.
        reference_name(self.name)
        return self


class FileDownload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resource_id: ResourceId
    version_id: VersionId


class StoredFile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    resource_id: ResourceId
    owner_kind: Literal['project', 'workspace']
    owner_project_id: ProjectId | None
    name: str
    sha256: VersionId
    bytes: int = Field(gt=0, le=MAX_BYTES)
    created_at: str
    version_id: VersionId

    @model_validator(mode='after')
    def valid_record(self):
        reference_name(self.name)
        if (self.owner_kind == 'project') != bool(self.owner_project_id):
            raise ValueError('resource_owner_invalid')
        if datetime.fromisoformat(self.created_at).tzinfo is None:
            raise ValueError('timestamp_timezone_required')
        if checksum(self.model_dump(exclude={'version_id'})) != self.version_id:
            raise ValueError('resource_file_version_invalid')
        return self


class ResourceFiles:
    def __init__(self, resources):
        self.resources, self.projects = resources, resources.projects

    @staticmethod
    def initialize(db):
        db.execute('CREATE TABLE IF NOT EXISTS data_resource_files(scope TEXT,id TEXT,record TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(scope,id))')
        db.execute('CREATE TABLE IF NOT EXISTS data_resources(scope TEXT,id TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,id))')
        db.execute('CREATE TABLE IF NOT EXISTS resource_changes(scope TEXT,actor TEXT,request_id TEXT,spec TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,actor,request_id))')

    @staticmethod
    def records(db, scope):
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='data_resource_files'").fetchone():
            return {}
        rows = db.execute('SELECT id,record FROM data_resource_files WHERE scope=?', (scope,)).fetchmany(MAX_FILES + 1)
        if len(rows) > MAX_FILES:
            raise ProjectUnavailable('resource_file_storage_invalid')
        result = {}
        for identity, raw in rows:
            try:
                value = StoredFile.model_validate_json(raw).model_dump()
                if identity != value['resource_id']:
                    raise ValueError('resource_file_identity_invalid')
            except (ValueError, TypeError) as exc:
                raise ProjectUnavailable('resource_file_storage_invalid') from exc
            result[identity] = value
        return result

    @staticmethod
    def version(record):
        return {'version_id': record['version_id'], 'reference_kind': 'source_metadata',
                'created_at': record['created_at'], 'format': Path(record['name']).suffix.lower()[1:],
                'bytes': record['bytes']}

    @staticmethod
    def require_manager(principal, policy):
        if not policy.workspace_manager(principal):
            raise PermissionError('resource_management_denied')

    def require_upload(self, principal, policy, command, db):
        self.require_manager(principal, policy)
        _, projects, _ = self.projects.state(db, self.projects.scope(principal))
        if command.owner_kind == 'project' and projects.get(command.owner_project_id, {}).get('status') != 'active':
            raise ProjectError('active_project_required')

    def upload(self, principal, policy, command, payload):
        self.require_manager(principal, policy)
        if not 0 < len(payload) <= MAX_BYTES:
            raise ProjectError('resource_file_size_budget', 413)
        scope = self.projects.scope(principal)
        spec = checksum(command.model_dump() | {'sha256': hashlib.sha256(payload).hexdigest()})
        with self.projects.database(write=True) as db:
            self.initialize(db)
            self.require_upload(principal, policy, command, db)
            previous = db.execute('SELECT spec,record FROM resource_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, command.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('resource_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            count, stored = db.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(payload)),0) FROM data_resource_files WHERE scope=?', (scope,)).fetchone()
            if count >= MAX_FILES or stored + len(payload) > MAX_STORED_BYTES:
                raise ProjectError('resource_file_storage_budget')
            identity = 'resource-' + checksum({'scope': scope, 'actor': principal.subject, 'request': command.request_id})[:32]
            at = datetime.now(timezone.utc).isoformat()
            file = {'resource_id': identity, 'owner_kind': command.owner_kind, 'owner_project_id': command.owner_project_id,
                    'name': command.name, 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'created_at': at}
            file['version_id'] = checksum(file)
            StoredFile.model_validate(file)
            version = self.version(file) | {'recorded_at': at}
            record = {'resource_id': identity, 'source_key': identity, 'space_id': None,
                      'owner_kind': command.owner_kind, 'owner_project_id': command.owner_project_id,
                      'is_base': command.is_base, 'revision': 1, 'versions': {version['version_id']: version}}
            event = {'resource_id': identity, 'revision': 1, 'actor': principal.subject, 'space_id': None,
                     'changed_at': at, 'reason': command.reason, 'before': None, 'after': record}
            record_scope(db, principal)
            db.execute('INSERT INTO data_resource_files VALUES(?,?,?,?)', (scope, identity, json.dumps(file), payload))
            db.execute('INSERT INTO data_resources VALUES(?,?,?)', (scope, identity, json.dumps(record)))
            db.execute('INSERT INTO resource_changes VALUES(?,?,?,?,?)', (scope, principal.subject, command.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}

    def payload(self, db, scope, record):
        row = db.execute('SELECT CASE WHEN LENGTH(payload)<=? THEN payload END FROM data_resource_files WHERE scope=? AND id=?',
                         (MAX_BYTES, scope, record['resource_id'])).fetchone()
        if row is None or row[0] is None or len(row[0]) != record['bytes'] or hashlib.sha256(row[0]).hexdigest() != record['sha256']:
            raise ProjectUnavailable('resource_file_content_invalid')
        return row[0]

    def download(self, principal, policy, command):
        scope = self.projects.scope(principal)
        with self.projects.database() as db:
            record = self.records(db, scope).get(command.resource_id)
            if record is None:
                raise PermissionError('resource_access_denied')
            _, projects, links = self.projects.state(db, scope)
            if not policy.workspace_manager(principal):
                if record['owner_kind'] != 'project' or record['owner_project_id'] not in self.resources.sharing.target_projects(principal, policy, projects, links):
                    raise PermissionError('resource_access_denied')
            if record['version_id'] != command.version_id:
                raise ProjectError('resource_source_changed')
            return record, self.payload(db, scope, record)

    def rows(self, principal, policy, db, scope, projects, links, registered):
        manager = policy.workspace_manager(principal)
        targets = self.resources.sharing.target_projects(principal, policy, projects, links)
        result = []
        for identity, record in self.records(db, scope).items():
            if not manager and (record['owner_kind'] != 'project' or record['owner_project_id'] not in targets):
                continue
            saved = registered.get(identity)
            if not saved or saved.get('space_id') is not None or saved.get('owner_kind') != record['owner_kind'] or saved['owner_project_id'] != record['owner_project_id'] or record['version_id'] not in saved['versions']:
                raise ProjectUnavailable('resource_file_registration_invalid')
            owner = projects.get(record['owner_project_id'])
            if record['owner_kind'] == 'project' and owner is None:
                raise ProjectUnavailable('resource_file_owner_invalid')
            result.append({'key': identity, 'record_id': identity, 'resource_id': identity, 'space_id': None,
                           'space_name': None, 'kind': 'resource_file', 'resource_type': 'reference', 'label': record['name'],
                           'state': 'stored_original', 'href': None, 'source_version': self.version(record),
                           'project_id': record['owner_project_id'], 'owner_kind': record['owner_kind'],
                           'owner_project_id': record['owner_project_id'], 'owner_project_name': owner['name'] if owner else None,
                           'registered': True, 'is_base': saved['is_base'], 'revision': saved['revision'],
                           'version_count': len(saved['versions']), 'version_registered': True, 'can_manage': manager})
        return result
