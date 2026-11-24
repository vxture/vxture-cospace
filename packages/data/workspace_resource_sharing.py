"""Version-scoped sharing; grants never give access to a source scene."""
from datetime import datetime, timezone
import hashlib
import json
from pydantic import ValidationError

from packages.data.scene_attachments import SceneAttachments, MAX_BYTES
from packages.lifecycle.scene_initialization import checksum
from packages.lifecycle.workspace_projects import ProjectError, ProjectUnavailable
from packages.data.resource_sharing_contract import StoredGrant, StoredUse, StoredSnapshot
from packages.data.resource_storage_usage import record_scope


class ResourceSharing:
    def __init__(self, resources, *, now=None):
        self.resources, self.projects = resources, resources.projects
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def rows(db, scope, table):
        if table not in ('data_resource_grants', 'data_resource_uses'):
            raise ValueError('sharing_table_invalid')
        if db is None or not db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
            return {}
        rows = db.execute(f'SELECT id,record FROM {table} WHERE scope=?', (scope,)).fetchmany(10001)
        if len(rows) > 10000:
            raise ProjectError('resource_sharing_budget_exceeded', 503)
        result = {}
        model = StoredGrant if table == 'data_resource_grants' else StoredUse
        for identity, raw in rows:
            try:
                record = model.model_validate_json(raw).model_dump()
            except ValidationError as exc:
                raise ProjectUnavailable('resource_sharing_storage_invalid') from exc
            if record['id'] != identity:
                raise ProjectUnavailable('resource_sharing_storage_invalid')
            result[identity] = record
        return result

    @staticmethod
    def initialize(db):
        for table in ('data_resource_grants', 'data_resource_uses'):
            db.execute(f'CREATE TABLE IF NOT EXISTS {table}(scope TEXT,id TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,id))')
        db.execute('CREATE TABLE IF NOT EXISTS data_shared_versions(scope TEXT,resource_id TEXT,version_id TEXT,record TEXT NOT NULL,payload BLOB,PRIMARY KEY(scope,resource_id,version_id))')
        db.execute('CREATE TABLE IF NOT EXISTS data_sharing_changes(scope TEXT,actor TEXT,request_id TEXT,spec TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,actor,request_id))')

    def target_projects(self, principal, policy, projects, links):
        if policy.workspace_manager(principal):
            return set(projects)
        scenes = self.projects.scenes(principal, policy)
        return {v['project_id'] for identity, v in links.items() if identity in scenes and v['project_id']}

    def require_target(self, principal, policy, identity, projects, links, space=None, *, historical=False):
        if identity not in self.target_projects(principal, policy, projects, links):
            raise PermissionError('resource_target_project_denied')
        if identity not in projects or not historical and projects[identity]['status'] != 'active':
            raise ProjectError('active_project_required')
        if space:
            policy.require(principal, space, 'data.manage')
            if links.get(space, {}).get('project_id') != identity:
                raise ProjectError('resource_target_scene_mismatch')

    def require_source(self, principal, policy, resource):
        if not policy.workspace_manager(principal):
            raise PermissionError('resource_sharing_denied')
        if resource['space_id']:
            policy.require(principal, resource['space_id'], 'data.manage')
            policy.require(principal, resource['space_id'], 'space.manage')

    def grant_status(self, grant, projects):
        if grant['status'] != 'active':
            return 'revoked'
        if grant['expires_at'] and datetime.fromisoformat(grant['expires_at']) <= self.now():
            return 'expired'
        if grant['target_project_id'] and projects.get(grant['target_project_id'], {}).get('status') != 'active':
            return 'project_archived'
        return 'active'

    def authorize_grant(self, principal, policy, grant, project, projects, links):
        self.require_target(principal, policy, project, projects, links)
        if grant['target_kind'] != 'workspace' and grant['target_project_id'] != project:
            raise PermissionError('resource_grant_denied')
        if self.grant_status(grant, projects) != 'active':
            raise PermissionError('resource_grant_inactive')

    @staticmethod
    def snapshot(db, scope, resource, version, *, payload=False):
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='data_shared_versions'").fetchone():
            return None
        row = db.execute('SELECT record' + (f',CASE WHEN LENGTH(payload)<={MAX_BYTES} THEN payload END' if payload else '') +
                         ' FROM data_shared_versions WHERE scope=? AND resource_id=? AND version_id=?',
                         (scope, resource, version)).fetchone()
        if row is None:
            return None
        try:
            record = StoredSnapshot.model_validate_json(row[0]).model_dump()
        except ValidationError as exc:
            raise ProjectUnavailable('resource_snapshot_invalid') from exc
        if record['source_version']['version_id'] != version:
            raise ProjectUnavailable('resource_snapshot_invalid')
        return (record, row[1]) if payload else record

    def capture(self, principal, policy, command, resource, db):
        if resource['space_id'] is None:
            scope = self.projects.scope(principal)
            file = self.resources.files.get(db, scope, command.resource_id, command.version_id)
            if file is None or file['version_id'] != command.version_id:
                raise ProjectError('resource_version_unavailable')
            record = {'label': file['name'], 'kind': 'resource_file', 'resource_type': 'reference',
                      'source_version': self.resources.files.version(file), 'is_base': resource['is_base'],
                      'payload_available': True, 'filename': file['name'], 'bytes': file['bytes'], 'sha256': file['sha256']}
            return record, self.resources.files.payload(db, scope, file)
        # Only newly shared versions are materialized. Old D02 hashes without a
        # complete snapshot cannot be reconstructed after their source changes.
        _, items, _ = self.resources.projection(principal, policy)
        item = next((i for i in items if i['resource_id'] == command.resource_id and
                     i['source_version']['version_id'] == command.version_id), None)
        if item is None:
            raise ProjectError('resource_version_unavailable')
        record = {key: item[key] for key in ('label', 'kind', 'resource_type', 'source_version')}
        record['is_base'] = resource['is_base']
        payload = None
        if item['kind'] == 'attachment':
            attachment, payload = SceneAttachments(self.resources.jobs.inputs).download(item['space_id'], item['record_id'])
            if checksum(attachment) != command.version_id:
                raise ProjectError('resource_source_changed')
            record.update(filename=attachment['name'], bytes=len(payload), sha256=attachment['sha256'])
        record['payload_available'] = payload is not None
        return record, payload

    def change(self, principal, policy, command):
        if command.action == 'upgrade':
            from packages.data.resource_reference_upgrades import ReferenceUpgrades
            return ReferenceUpgrades(self).change(principal, policy, command)
        scope = self.projects.scope(principal)
        spec = checksum(command.model_dump(mode='json'))
        # No grant/use mutation writes original inputs, scene links or models.
        with self.projects.database(write=True) as db:
            self.initialize(db)
            _, projects, links = self.projects.state(db, scope)
            resources = self.resources.records(db, scope)
            grants = self.rows(db, scope, 'data_resource_grants')
            uses = self.rows(db, scope, 'data_resource_uses')
            if command.action == 'grant':
                resource = resources.get(command.resource_id)
                if resource is None:
                    raise PermissionError('resource_sharing_denied')
                self.require_source(principal, policy, resource)
            elif command.action == 'revoke':
                grant = grants.get(command.grant_id)
                if grant is None or grant['resource_id'] not in resources:
                    raise PermissionError('resource_sharing_denied')
                resource = resources[grant['resource_id']]
                self.require_source(principal, policy, resource)
            elif command.action == 'use':
                grant = grants.get(command.grant_id)
                if grant is None:
                    raise PermissionError('resource_grant_denied')
                self.authorize_grant(principal, policy, grant, command.project_id, projects, links)
                if grant['revision'] != command.expected_grant_revision:
                    raise ProjectError('resource_sharing_revision_changed')
                self.require_target(principal, policy, command.project_id, projects, links, command.space_id)
            else:
                use = uses.get(command.use_id)
                if use is None:
                    raise PermissionError('resource_use_denied')
                self.require_target(principal, policy, use['project_id'], projects, links)
                if use['space_id']:
                    policy.require(principal, use['space_id'], 'data.manage')
            previous = db.execute('SELECT spec,record FROM data_sharing_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, command.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('resource_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            if command.action in ('grant', 'use'):
                from packages.data.resource_governance import require_active
                require_active(db, scope, command.resource_id if command.action == 'grant' else grant['resource_id'])
            at = self.now().isoformat()
            if command.action == 'grant':
                if resource['revision'] != command.expected_resource_revision:
                    raise ProjectError('resource_revision_changed')
                if resource.get('owner_kind', 'project') == 'project' and projects.get(resource['owner_project_id'], {}).get('status') != 'active':
                    raise ProjectError('active_project_required')
                if command.target_project_id:
                    if projects.get(command.target_project_id, {}).get('status') != 'active':
                        raise ProjectError('active_project_required')
                    if command.target_project_id == resource['owner_project_id']:
                        raise ProjectError('resource_already_owned')
                if command.version_id not in resource['versions']:
                    raise ProjectError('resource_version_not_registered')
                if command.expires_at and command.expires_at <= self.now():
                    raise ProjectError('resource_expiry_in_past')
                identity = 'grant-' + checksum({'resource': command.resource_id, 'version': command.version_id,
                                               'target': command.target_kind, 'project': command.target_project_id})[:32]
                before = grants.get(identity)
                snap = self.snapshot(db, scope, command.resource_id, command.version_id)
                if snap is None:
                    snap, payload = self.capture(principal, policy, command, resource, db)
                    used_bytes = db.execute('SELECT COALESCE(SUM(LENGTH(payload)),0) FROM data_shared_versions WHERE scope=?', (scope,)).fetchone()[0]
                    if used_bytes + len(payload or b'') > 512 * 1024 * 1024:
                        raise ProjectError('resource_shared_storage_budget', 409)
                    db.execute('INSERT INTO data_shared_versions VALUES(?,?,?,?,?)',
                               (scope, command.resource_id, command.version_id, json.dumps(snap), payload))
                if command.allow_download and not snap['payload_available']:
                    raise ProjectError('resource_download_not_supported')
                record = {'id': identity, 'resource_id': command.resource_id, 'version_id': command.version_id,
                          'target_kind': command.target_kind, 'target_project_id': command.target_project_id,
                          'allow_download': command.allow_download,
                          'expires_at': command.expires_at.isoformat() if command.expires_at else None,
                          'status': 'active', 'updated_at': at}
                table = 'data_resource_grants'
            elif command.action == 'revoke':
                identity, before, table = grant['id'], grant, 'data_resource_grants'
                record = grant | {'status': 'revoked', 'updated_at': at}
            elif command.action == 'use':
                if command.use_mode != 'reference':
                    raise ProjectError('resource_spatial_application_requires_verification')
                if resources[grant['resource_id']]['owner_project_id'] == command.project_id:
                    raise ProjectError('resource_already_owned')
                identity = 'use-' + checksum({'resource': grant['resource_id'], 'project': command.project_id,
                                             'space': command.space_id})[:32]
                before = uses.get(identity)
                if before and before['status'] == 'active' and self.use_status(before, grants, projects) == 'active':
                    raise ProjectError('resource_already_referenced')
                record = {'id': identity, 'resource_id': grant['resource_id'], 'version_id': grant['version_id'],
                          'grant_id': grant['id'], 'grant_revision': grant['revision'],
                          'project_id': command.project_id, 'space_id': command.space_id,
                          'purpose': command.purpose.strip(), 'status': 'active', 'updated_at': at,
                          'use_mode': 'reference', 'coordinate_status': 'not_applied'}
                table = 'data_resource_uses'
            else:
                identity, before, table = use['id'], use, 'data_resource_uses'
                record = use | {'status': 'unlinked', 'updated_at': at}
            if (before['revision'] if before else 0) != command.expected_revision:
                raise ProjectError('resource_sharing_revision_changed')
            if before is None and len(grants if table=='data_resource_grants' else uses) >= 10000:
                raise ProjectError('resource_sharing_budget_exceeded', 503)
            record['revision'] = command.expected_revision + 1
            event = {'action': command.action, 'actor': principal.subject, 'reason': command.reason,
                     'changed_at': at, 'before': before, 'after': record}
            record_scope(db, principal)
            db.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?)', (scope, identity, json.dumps(record)))
            db.execute('INSERT INTO data_sharing_changes VALUES(?,?,?,?,?)',
                       (scope, principal.subject, command.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}

    def use_status(self, use, grants, projects):
        if use['status'] != 'active':
            return 'unlinked'
        grant = grants.get(use['grant_id'])
        if grant is None:
            return 'revoked'
        if (grant['resource_id'], grant['version_id']) != (use['resource_id'], use['version_id']):
            return 'grant_changed'
        status = self.grant_status(grant, projects)
        if status != 'active':
            return status
        return 'active' if grant['revision'] == use['grant_revision'] else 'grant_changed'

    def visible_uses(self, principal, policy, db, scope, projects, links, *, project=None, resource=None):
        targets = self.target_projects(principal, policy, projects, links)
        grants = self.rows(db, scope, 'data_resource_grants')
        rows = []
        for use in self.rows(db, scope, 'data_resource_uses').values():
            if (use['project_id'] not in targets or project and use['project_id'] != project
                    or resource and use['resource_id'] != resource):
                continue
            if use['space_id'] and 'data.manage' not in policy.capabilities(principal, use['space_id']):
                continue
            snap = self.snapshot(db, scope, use['resource_id'], use['version_id'])
            if snap is None:
                raise ProjectError('resource_snapshot_unavailable', 503)
            access = self.use_status(use, grants, projects)
            rows.append(use | {'access_status': access, 'snapshot': snap,
                               'allow_download': access == 'active' and grants[use['grant_id']]['allow_download'],
                               'project_name': projects[use['project_id']]['name'],
                               'space_name': self.resources.directory.read('space', use['space_id'])['name'] if use['space_id'] else None})
        return rows

    def external_rows(self, principal, policy, db, scope, projects, links, query):
        uses = self.visible_uses(principal, policy, db, scope, projects, links, project=query.project_id)
        resources = self.resources.records(db, scope)
        grouped = {}
        for use in uses:
            if use['status'] != 'active' or query.space_id and use['space_id'] != query.space_id:
                continue
            if query.placement == 'project' and use['space_id'] is not None or query.placement == 'scene' and use['space_id'] is None:
                continue
            grouped.setdefault(use['resource_id'], []).append(use)
        result = []
        for identity, references in grouped.items():
            resource = resources[identity]
            snap = references[0]['snapshot']
            result.append({'key': identity, 'record_id': identity, 'space_id': None, 'space_name': None,
                           'kind': snap['kind'], 'label': snap['label'], 'state': 'referenced', 'href': None,
                           'resource_id': identity, 'resource_type': snap['resource_type'],
                           'source_version': snap['source_version'], 'project_id': query.project_id,
                           'owner_project_id': resource['owner_project_id'],
                           'owner_project_name': projects[resource['owner_project_id']]['name'] if resource['owner_project_id'] else None,
                           'owner_kind': resource.get('owner_kind', 'project'),
                           'registered': True, 'is_base': snap['is_base'], 'revision': resource['revision'],
                           'version_count': len({u['version_id'] for u in references}), 'version_registered': True,
                           'can_manage': False, 'external': True, 'uses': references, 'is_shared': False})
        return result

    def available(self, principal, policy, db, scope, query, projects, links):
        if not query.project_id:
            raise ProjectError('resource_target_project_required', 422)
        self.require_target(principal, policy, query.project_id, projects, links)
        resources = self.resources.records(db, scope)
        uses = self.rows(db, scope, 'data_resource_uses')
        grants = self.rows(db, scope, 'data_resource_grants')
        result = []
        for grant in grants.values():
            if (self.grant_status(grant, projects) != 'active' or
                    query.resource_id and grant['resource_id'] != query.resource_id or
                    grant['target_kind'] == 'project' and grant['target_project_id'] != query.project_id):
                continue
            resource = resources[grant['resource_id']]
            if resource['owner_project_id'] == query.project_id:
                continue
            snap = self.snapshot(db, scope, grant['resource_id'], grant['version_id'])
            if snap is None:
                raise ProjectError('resource_snapshot_unavailable', 503)
            target = 'use-' + checksum({'resource': grant['resource_id'], 'project': query.project_id, 'space': None})[:32]
            use = uses.get(target)
            result.append({'grant': grant, 'snapshot': snap,
                           'owner_kind': resource.get('owner_kind', 'project'),
                           'owner_project_name': projects[resource['owner_project_id']]['name'] if resource['owner_project_id'] else None,
                           'reference_revision': use['revision'] if use else 0,
                           'reference_status': self.use_status(use, grants, projects) if use else None})
        return result

    def read(self, principal, policy, query):
        scope = self.projects.scope(principal)
        with self.projects.database() as db:
            _, projects, links = self.projects.state(db, scope)
            if query.view == 'available':
                items = self.available(principal, policy, db, scope, query, projects, links)
                items = [i for i in items if query.search.casefold() in
                         (i['snapshot']['label'] + ' ' + (i['owner_project_name'] or '工作区共用')).casefold()]
            elif query.view == 'uses':
                if not query.project_id:
                    raise ProjectError('resource_target_project_required', 422)
                self.require_target(principal, policy, query.project_id, projects, links, historical=True)
                items = self.visible_uses(principal, policy, db, scope, projects, links,
                                          project=query.project_id, resource=query.resource_id)
                items = [i for i in items if query.search.strip().casefold() in
                         (i['snapshot']['label']+' '+i['purpose']+' '+(i['space_name'] or '')).casefold()]
            else:
                resources = self.resources.records(db, scope)
                if query.resource_id not in resources:
                    raise PermissionError('resource_sharing_denied')
                self.require_source(principal, policy, resources[query.resource_id])
                items = [g | {'access_status': self.grant_status(g, projects),
                              'target_project_name': projects[g['target_project_id']]['name'] if g['target_project_id'] else None}
                         for g in self.rows(db, scope, 'data_resource_grants').values()
                         if g['resource_id'] == query.resource_id]
            items.sort(key=lambda i: i.get('id', i.get('grant', {}).get('id', '')))
            return {'profile': 'cospace.resource-sharing/0.1', 'workspace_id': principal.workspace_id,
                    'view': query.view, 'project_id': query.project_id, 'resource_id': query.resource_id,
                    'items': items[query.offset:query.offset + query.limit], 'total': len(items),
                    'next_offset': query.offset + query.limit if query.offset + query.limit < len(items) else None}

    def download(self, principal, policy, command):
        scope = self.projects.scope(principal)
        with self.projects.database() as db:
            _, projects, links = self.projects.state(db, scope)
            grant = self.rows(db, scope, 'data_resource_grants').get(command.grant_id)
            if grant is None:
                raise PermissionError('resource_grant_denied')
            self.authorize_grant(principal, policy, grant, command.project_id, projects, links)
            if not grant['allow_download'] or grant['revision'] != command.grant_revision:
                raise PermissionError('resource_download_denied')
            snap = self.snapshot(db, scope, grant['resource_id'], grant['version_id'], payload=True)
            if snap is None or snap[1] is None or len(snap[1]) > MAX_BYTES or len(snap[1]) != snap[0]['bytes'] or hashlib.sha256(snap[1]).hexdigest() != snap[0]['sha256']:
                raise ProjectError('resource_snapshot_unavailable', 503)
            return snap
