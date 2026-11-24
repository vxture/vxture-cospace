"""Explicit authorized version upgrades, preserving reference identity and audit."""
import json

from pydantic import BaseModel, ConfigDict, Field

from packages.data.resource_sharing_contract import UseId, SharingQuery
from packages.lifecycle.scene_initialization import checksum
from packages.lifecycle.workspace_projects import ProjectError, ProjectUnavailable
from packages.data.resource_storage_usage import record_scope


class UpgradeQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    use_id: UseId
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)


class ReferenceUpgrades:
    def __init__(self, sharing):
        self.sharing, self.projects = sharing, sharing.projects

    def target(self, principal, policy, identity, db, scope, projects, links):
        use = self.sharing.rows(db, scope, 'data_resource_uses').get(identity)
        if use is None:
            raise PermissionError('resource_use_denied')
        self.sharing.require_target(principal, policy, use['project_id'], projects, links, use['space_id'])
        return use

    def read(self, principal, policy, query):
        scope = self.projects.scope(principal)
        with self.projects.database() as db:
            _, projects, links = self.projects.state(db, scope)
            use = self.target(principal, policy, query.use_id, db, scope, projects, links)
            if use['status'] != 'active':
                raise ProjectError('resource_use_inactive')
            current = self.sharing.snapshot(db, scope, use['resource_id'], use['version_id'])
            if current is None:
                raise ProjectUnavailable('resource_snapshot_unavailable')
            available = SharingQuery(project_id=use['project_id'], resource_id=use['resource_id'])
            candidates = self.sharing.available(principal, policy, db, scope, available, projects, links)
            candidates = [v for v in candidates if v['grant']['version_id'] != use['version_id']]
            candidates.sort(key=lambda v: (v['snapshot']['source_version']['created_at'] or '', v['grant']['id']), reverse=True)
            return {'profile': 'cospace.reference-upgrade/0.1', 'workspace_id': principal.workspace_id,
                    'use': use, 'current': current, 'candidates': candidates[query.offset:query.offset+query.limit],
                    'total': len(candidates), 'offset': query.offset, 'limit': query.limit,
                    'next_offset': query.offset+query.limit if query.offset+query.limit < len(candidates) else None}

    def change(self, principal, policy, command):
        scope = self.projects.scope(principal)
        spec = checksum(command.model_dump(mode='json'))
        with self.projects.database(write=True) as db:
            self.sharing.initialize(db)
            _, projects, links = self.projects.state(db, scope)
            use = self.target(principal, policy, command.use_id, db, scope, projects, links)
            grant = self.sharing.rows(db, scope, 'data_resource_grants').get(command.grant_id)
            if grant is None or grant['resource_id'] != use['resource_id']:
                raise PermissionError('resource_grant_denied')
            self.sharing.authorize_grant(principal, policy, grant, use['project_id'], projects, links)
            if grant['revision'] != command.expected_grant_revision:
                raise ProjectError('resource_sharing_revision_changed')
            previous = db.execute('SELECT spec,record FROM data_sharing_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, command.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('resource_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            from packages.data.resource_governance import require_active
            require_active(db, scope, use['resource_id'])
            if use['status'] != 'active':
                raise ProjectError('resource_use_inactive')
            if use['revision'] != command.expected_revision or use['version_id'] != command.expected_version:
                raise ProjectError('resource_sharing_revision_changed')
            if grant['version_id'] == use['version_id']:
                raise ProjectError('resource_version_unchanged')
            from packages.data.resource_lineage import ResourceLineage
            resource = ResourceLineage(self.sharing.resources).registration(db, scope, use['resource_id'])
            if grant['version_id'] not in resource['versions']:
                raise ProjectUnavailable('resource_version_not_registered')
            if self.sharing.snapshot(db, scope, use['resource_id'], grant['version_id']) is None:
                raise ProjectUnavailable('resource_snapshot_unavailable')
            at = self.sharing.now().isoformat()
            record = use | {'version_id': grant['version_id'], 'grant_id': grant['id'],
                            'grant_revision': grant['revision'], 'revision': use['revision']+1, 'updated_at': at}
            event = {'action': 'upgrade', 'actor': principal.subject, 'reason': command.reason,
                     'changed_at': at, 'before': use, 'after': record}
            record_scope(db, principal)
            db.execute('UPDATE data_resource_uses SET record=? WHERE scope=? AND id=?', (json.dumps(record), scope, use['id']))
            db.execute('INSERT INTO data_sharing_changes VALUES(?,?,?,?,?)',
                       (scope, principal.subject, command.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}
