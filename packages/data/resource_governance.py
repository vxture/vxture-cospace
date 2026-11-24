"""Recoverable reference-file archive, serialized with grants, uses and versions."""
from datetime import datetime, timezone
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.data.resource_lineage import ResourceLineage
from packages.data.resource_sharing_contract import ResourceId, VersionId
from packages.lifecycle.scene_initialization import checksum
from packages.lifecycle.workspace_projects import Change, ProjectError, ProjectUnavailable


class GovernanceQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resource_id: ResourceId


class GovernanceChange(Change):
    resource_id: ResourceId
    action: Literal['archive', 'restore']
    expected_snapshot: VersionId


class StoredState(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    resource_id: ResourceId
    state: Literal['active', 'archived']
    revision: int = Field(ge=1)
    updated_at: str
    actor: str
    reason: str = Field(min_length=1, max_length=500)


def states(db, scope):
    if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='data_resource_states'").fetchone():
        return {}
    rows = db.execute('SELECT id,record FROM data_resource_states WHERE scope=?', (scope,)).fetchmany(10001)
    if len(rows) > 10000:
        raise ProjectUnavailable('resource_governance_budget')
    result = {}
    for identity, raw in rows:
        try:
            record = StoredState.model_validate_json(raw).model_dump()
            if record['resource_id'] != identity or datetime.fromisoformat(record['updated_at']).tzinfo is None:
                raise ValueError('state_invalid')
        except (ValueError, TypeError) as exc:
            raise ProjectUnavailable('resource_governance_invalid') from exc
        result[identity] = record
    return result


def require_active(db, scope, identity):
    if states(db, scope).get(identity, {}).get('state') == 'archived':
        raise ProjectError('resource_archived')


class ResourceGovernance:
    def __init__(self, resources):
        self.resources, self.projects, self.sharing = resources, resources.projects, resources.sharing

    def target(self, principal, policy, db, scope, identity):
        resource = ResourceLineage(self.resources).registration(db, scope, identity)
        self.sharing.require_source(principal, policy, resource)
        if resource['space_id'] is not None:
            raise ProjectError('resource_scene_lifecycle_required')
        current = self.resources.files.get(db, scope, identity)
        if (current is None or current['version_id'] not in resource['versions'] or
                (current['owner_kind'], current['owner_project_id']) != (resource['owner_kind'], resource['owner_project_id'])):
            raise ProjectUnavailable('resource_file_registration_invalid')
        return resource

    def report(self, principal, policy, db, scope, identity):
        resource = self.target(principal, policy, db, scope, identity)
        _, projects, _ = self.projects.state(db, scope)
        current = states(db, scope).get(identity)
        # Inspect every record in the trusted workspace, not visible-use counts.
        uses = [u for u in self.sharing.rows(db, scope, 'data_resource_uses').values()
                if u['resource_id'] == identity and u['status'] == 'active']
        grants = [g for g in self.sharing.rows(db, scope, 'data_resource_grants').values()
                  if g['resource_id'] == identity and self.sharing.grant_status(g, projects) == 'active']
        state, revision = (current['state'], current['revision']) if current else ('active', 0)
        snapshot = checksum({'resource': resource, 'state': current,
                             'uses': sorted(uses, key=lambda v: v['id']), 'grants': sorted(grants, key=lambda v: v['id'])})
        blockers = []
        if uses:
            blockers.append('resource_has_references')
        if grants:
            blockers.append('resource_has_active_grants')
        return {'profile': 'cospace.resource-governance/0.1', 'workspace_id': principal.workspace_id,
                'resource_id': identity, 'state': state, 'revision': revision, 'snapshot': snapshot,
                'impact': {'scope': 'workspace', 'has_linked_references': bool(uses), 'has_active_grants': bool(grants)},
                'actions': [{'action': 'archive', 'allowed': state == 'active' and not blockers, 'blockers': blockers},
                            {'action': 'restore', 'allowed': state == 'archived', 'blockers': []}],
                'last_change': current, 'physical_delete_supported': False}

    def read(self, principal, policy, query):
        with self.projects.database() as db:
            return self.report(principal, policy, db, self.projects.scope(principal), query.resource_id)

    def change(self, principal, policy, command):
        scope, spec = self.projects.scope(principal), checksum(command.model_dump())
        with self.projects.database(write=True) as db:
            self.target(principal, policy, db, scope, command.resource_id)
            db.execute('CREATE TABLE IF NOT EXISTS data_resource_states(scope TEXT,id TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,id))')
            db.execute('CREATE TABLE IF NOT EXISTS data_governance_changes(scope TEXT,actor TEXT,request_id TEXT,spec TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,actor,request_id))')
            previous = db.execute('SELECT spec,record FROM data_governance_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, command.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('resource_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            report = self.report(principal, policy, db, scope, command.resource_id)
            if report['revision'] != command.expected_revision or report['snapshot'] != command.expected_snapshot:
                raise ProjectError('resource_governance_changed')
            action = next(a for a in report['actions'] if a['action'] == command.action)
            if not action['allowed']:
                raise ProjectError(action['blockers'][0] if action['blockers'] else 'resource_governance_changed')
            record = {'resource_id': command.resource_id, 'state': 'archived' if command.action == 'archive' else 'active',
                      'revision': report['revision'] + 1, 'updated_at': datetime.now(timezone.utc).isoformat(),
                      'actor': principal.subject, 'reason': command.reason}
            event = {'resource_id': command.resource_id, 'action': command.action, 'before': report['last_change'], 'after': record}
            db.execute('INSERT OR REPLACE INTO data_resource_states VALUES(?,?,?)', (scope, command.resource_id, json.dumps(record)))
            db.execute('INSERT INTO data_governance_changes VALUES(?,?,?,?,?)', (scope, principal.subject, command.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}
