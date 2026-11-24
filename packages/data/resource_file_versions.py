"""Append originals without rewriting historical bytes, grants or uses."""
from datetime import datetime, timezone
import hashlib
import json

from pydantic import Field, model_validator

from packages.data.resource_files import StoredFile, MAX_BYTES
from packages.data.resource_sharing_contract import ResourceId, VersionId
from packages.data.scene_attachments import reference_name
from packages.data.resource_storage_usage import record_scope
from packages.lifecycle.workspace_projects import Change, ProjectError, ProjectUnavailable
from packages.data.resource_lineage import ResourceLineage
from packages.data.resource_governance import require_active
from packages.lifecycle.scene_initialization import checksum


class FileAppend(Change):
    resource_id: ResourceId
    expected_version: VersionId
    name: str = Field(min_length=1, max_length=160)

    @model_validator(mode='after')
    def valid_append(self):
        reference_name(self.name)
        if self.expected_revision < 1:
            raise ValueError('registered_resource_required')
        return self


class ResourceFileVersions:
    def __init__(self, files):
        self.files, self.projects = files, files.projects

    def target(self, principal, policy, command, db):
        self.files.require_manager(principal, policy)
        scope = self.projects.scope(principal)
        current = self.files.get(db, scope, command.resource_id)
        if current is None:
            raise PermissionError('resource_access_denied')
        self.files.require_upload(principal, policy, StoredFile.model_validate(current), db)
        saved = ResourceLineage(self.files.resources).registration(db, scope, command.resource_id)
        if (saved['space_id'] is not None or saved['owner_kind'] != current['owner_kind'] or
                saved['owner_project_id'] != current['owner_project_id'] or current['version_id'] not in saved['versions']):
            raise ProjectUnavailable('resource_file_registration_invalid')
        return current, saved

    def check_upload(self, principal, policy, command):
        with self.projects.database() as db:
            self.target(principal, policy, command, db)

    def upload(self, principal, policy, command, payload):
        self.files.require_manager(principal, policy)
        if not 0 < len(payload) <= MAX_BYTES:
            raise ProjectError('resource_file_size_budget', 413)
        scope = self.projects.scope(principal)
        spec = checksum(command.model_dump() | {'sha256': hashlib.sha256(payload).hexdigest()})
        with self.projects.database(write=True) as db:
            self.files.initialize(db)
            current, saved = self.target(principal, policy, command, db)
            previous = db.execute('SELECT spec,record FROM resource_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, command.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('resource_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            require_active(db, scope, command.resource_id)
            if saved['revision'] != command.expected_revision:
                raise ProjectError('resource_revision_changed')
            if current['version_id'] != command.expected_version:
                raise ProjectError('resource_source_changed')
            self.files.check_budget(db, scope, len(payload))
            original = self.files.payload(db, scope, current)
            at = datetime.now(timezone.utc).isoformat()
            new = current | {'name': command.name, 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'created_at': at}
            del new['version_id']
            new['version_id'] = checksum(new)
            StoredFile.model_validate(new)
            version = self.files.version(new) | {'recorded_at': at}
            record = saved | {'revision': saved['revision'] + 1, 'versions': saved['versions'] | {new['version_id']: version}}
            event = {'resource_id': command.resource_id, 'revision': record['revision'], 'actor': principal.subject,
                     'space_id': None, 'changed_at': at, 'reason': command.reason, 'before': saved, 'after': record}
            record_scope(db, principal)
            db.execute('INSERT INTO data_resource_file_history VALUES(?,?,?,?,?)', (scope, command.resource_id, current['version_id'], json.dumps(current), original))
            db.execute('UPDATE data_resource_files SET record=?,payload=? WHERE scope=? AND id=?', (json.dumps(new), payload, scope, command.resource_id))
            db.execute('UPDATE data_resources SET record=? WHERE scope=? AND id=?', (json.dumps(record), scope, command.resource_id))
            db.execute('INSERT INTO resource_changes VALUES(?,?,?,?,?)', (scope, principal.subject, command.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}
