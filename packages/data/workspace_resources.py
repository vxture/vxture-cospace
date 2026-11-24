"""Authorized resource directory with explicit, stable management ownership."""
from datetime import datetime, timezone
import json
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.data.workspace_catalog import catalog, CatalogQuery, metadata
from packages.data.scene_attachments import SceneAttachments
from packages.data.workspace_resource_sharing import ResourceSharing
from packages.data.resource_files import ResourceFiles
from packages.data.resource_governance import states, require_active
from packages.lifecycle.preview_scope import match
from packages.lifecycle.scene_initialization import checksum
from packages.lifecycle.workspace_projects import WorkspaceProjects, ProjectError, ProjectUnavailable


class ResourceQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Literal['all', 'base', 'acquisition', 'reference', 'result', 'process'] = 'all'
    project_id: str | None = Field(default=None, pattern=r'^project-[a-f0-9]{16}$')
    space_id: str | None = Field(default=None, pattern=r'^space-[a-f0-9]{16}$')
    search: str = Field(default='', max_length=100)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)
    placement: Literal['all', 'project', 'scene'] = 'all'
    ownership: Literal['all', 'owned', 'external', 'workspace'] = 'all'
    lifecycle: Literal['all', 'active', 'archived', 'disabled'] = 'all'


class ResourceChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    resource_id: str = Field(pattern=r'^resource-[a-f0-9]{32}$')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_revision: int = Field(ge=0)
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    owner_kind: Literal['project', 'workspace'] = 'project'
    owner_project_id: str | None = Field(default=None, pattern=r'^project-[a-f0-9]{16}$')
    is_base: bool = False
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def valid_owner(self):
        if (self.owner_kind == 'project') != bool(self.owner_project_id):
            raise ValueError('resource_owner_invalid')
        return self

    @field_validator('reason')
    @classmethod
    def required_reason(cls, value):
        if not value.strip():
            raise ValueError('reason_required')
        return value.strip()


class WorkspaceResources:
    def __init__(self, jobs, directory):
        self.jobs, self.directory = jobs, directory
        self.projects = WorkspaceProjects(directory)
        self.sharing = ResourceSharing(self)
        self.files = ResourceFiles(self)

    def source_version(self, item):
        kind, identity, space = item['kind'], item['record_id'], item['space_id']
        if kind == 'input':
            record = metadata(self.jobs.inputs.root, self.jobs.inputs.root / (identity + '.json'))
        elif kind == 'attachment':
            record = next(v for v in SceneAttachments(self.jobs.inputs).list(space) if v['id'] == identity)
        else:
            root = self.jobs.root / identity / 'output'
            record = metadata(self.jobs.root, root / 'model.json')
            if record.get('id') != identity:
                raise ValueError('model_identity_invalid')
            if kind in ('human_view', 'agent_view'):
                view = record.get(kind, {})
                member = record.get('members', {}).get(view.get('path'))
                if not member or not isinstance(member.get('sha256'), str):
                    raise ValueError('view_member_not_recorded')
        match(record, {'space_id': space, 'project_id': self.directory.read('space', space)['project_id']})
        # This fixes the source metadata, not a claim that payload bytes were revalidated.
        digest = checksum(record)
        created = record.get('created_at', record.get('registered_at'))
        if created is not None:
            if not isinstance(created, str) or len(created) > 80:
                raise ValueError('resource_date_invalid')
            datetime.fromisoformat(created)
        format_name, size = record.get('format'), record.get('bytes')
        if format_name is not None and (not isinstance(format_name, str) or len(format_name) > 100):
            raise ValueError('resource_format_invalid')
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError('resource_size_invalid')
        return {'version_id': digest, 'reference_kind': 'source_metadata',
                'created_at': created, 'format': format_name, 'bytes': size}

    def projection(self, principal, policy):
        report = catalog(self.jobs, self.directory, policy, principal, CatalogQuery(), all_metadata=True)
        scope = self.projects.scope(principal)
        issues = list(report['issues'])
        items = []
        for item in report['items']:
            if item['kind'] not in ('input', 'attachment', 'candidate', 'human_view', 'agent_view'):
                continue
            try:
                version = self.source_version(item)
            except (ValueError, OSError, KeyError, TypeError, StopIteration):
                issues.append({'space_id': item['space_id'], 'source': 'resource_metadata', 'code': 'metadata_unavailable'})
                continue
            identity = 'resource-' + checksum({'scope': scope, 'source': item['key']})[:32]
            items.append(item | {'resource_id': identity, 'source_version': version,
                                 'resource_type': 'acquisition' if item['kind'] == 'input' and version['format'] != 'ply_pointcloud' else
                                 'reference' if item['kind'] == 'attachment' else 'result'})
        return report, items, issues

    @staticmethod
    def records(db, scope):
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='data_resources'").fetchone():
            return {}
        return {identity: json.loads(raw) for identity, raw in db.execute(
            'SELECT id,record FROM data_resources WHERE scope=?', (scope,))}

    def read(self, principal, policy, query):
        report, items, issues = self.projection(principal, policy)
        scope = self.projects.scope(principal)
        manager = policy.workspace_manager(principal)
        if query.space_id:
            policy.require(principal, query.space_id, 'data.manage')
        with self.projects.database() as db:
            _, projects, links = self.projects.state(db, scope)
            registered = self.records(db, scope)
            visible_projects = set(projects) if manager else {
                link['project_id'] for identity, link in links.items()
                if identity in {s['id'] for s in report['spaces']} and link['project_id']}
            visible_resource_ids = {i['resource_id'] for i in items}
            visible_projects.update(v['owner_project_id'] for key, v in registered.items() if key in visible_resource_ids)
            if query.project_id and query.project_id not in visible_projects:
                raise PermissionError('business_project_access_denied')
            spaces = [s | {'project_id': links.get(s['id'], {}).get('project_id')}
                      for s in report['spaces']]
            if query.category == 'process':
                rows = [i | {'resource_id': None, 'project_id': links.get(i['space_id'], {}).get('project_id'),
                             'owner_project_id': None, 'owner_project_name': None, 'registered': False,
                             'is_base': False, 'revision': 0, 'version_count': 0, 'source_version': None,
                             'resource_type': 'process', 'can_manage': False}
                        for i in report['items'] if i['kind'] in ('job', 'preflight', 'batch')]
            else:
                rows = []
                grants = self.sharing.rows(db, scope, 'data_resource_grants')
                shared_ids = {g['resource_id'] for g in grants.values() if self.sharing.grant_status(g, projects) == 'active'}
                for item in items:
                    saved = registered.get(item['resource_id'])
                    owner = saved['owner_project_id'] if saved else None
                    project = projects.get(owner)
                    rows.append(item | {'project_id': links.get(item['space_id'], {}).get('project_id'),
                                        'owner_project_id': owner, 'owner_project_name': project['name'] if project else None,
                                        'registered': saved is not None, 'is_base': bool(saved and saved['is_base']),
                                        'revision': saved['revision'] if saved else 0,
                                        'version_count': len(saved['versions']) if saved else 0,
                                        'version_registered': bool(saved and item['source_version']['version_id'] in saved['versions']),
                                        'is_shared': item['resource_id'] in shared_ids,
                                        'can_manage': manager and 'space.manage' in policy.capabilities(principal, item['space_id'])})
                rows.extend(self.files.rows(principal, policy, db, scope, projects, links, registered))
                for row in rows:
                    row.setdefault('owner_kind', 'project' if row['registered'] else 'unassigned')
                    row['is_shared'] = row['resource_id'] in shared_ids
            rows = [r for r in rows if (not query.space_id or r['space_id'] == query.space_id) and
                    (not query.project_id or query.project_id in (r['project_id'], r['owner_project_id']))]
            def matches(row):
                return (row.get('external') or query.placement == 'all' or
                        query.placement == 'scene' and row['space_id'] is not None or
                        query.placement == 'project' and row['space_id'] is None) and (
                        query.ownership == 'all' or query.ownership == 'external' and row.get('external') or
                        query.ownership == 'workspace' and row.get('owner_kind') == 'workspace' or
                        query.ownership == 'owned' and not row.get('external') and row.get('owner_kind') == 'project')
            rows = [r for r in rows if matches(r)]
            if query.category != 'process':
                unique = {r['resource_id']: r for r in rows}
                for external in self.sharing.external_rows(principal, policy, db, scope, projects, links, query):
                    if not matches(external):
                        continue
                    if external['resource_id'] not in unique or query.project_id:
                        unique[external['resource_id']] = external
                rows = list(unique.values())
                saved_states = states(db, scope)
                scene_states = {}
                for row in rows:
                    if row.get('external'):
                        row['lifecycle_state'] = None
                    elif row['kind'] == 'resource_file':
                        row['lifecycle_state'] = saved_states.get(row['resource_id'], {}).get('state', 'active')
                    elif row['kind'] in ('input', 'candidate', 'human_view', 'agent_view'):
                        scene = row['space_id']
                        if scene not in scene_states:
                            try:
                                scene_states[scene] = {s['artifact']: s['lifecycle_state'] for s in self.jobs.controls.saved(scene)}
                            except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
                                raise ProjectUnavailable('resource_scene_lifecycle_unavailable') from exc
                        artifact = ('input:' if row['kind'] == 'input' else 'candidate:') + row['record_id']
                        row['lifecycle_state'] = scene_states[scene].get(artifact, 'active')
                    else:
                        row['lifecycle_state'] = None
            if query.lifecycle != 'all':
                rows = [r for r in rows if r.get('lifecycle_state') == query.lifecycle]
            q = query.search.strip().casefold()
            rows = [r for r in rows if
                    (query.category in ('all', 'process') or query.category == 'base' and r['is_base']
                     or r['resource_type'] == query.category) and
                    q in ' '.join(str(r.get(k) or '') for k in ('label', 'record_id', 'space_name', 'owner_project_name')).casefold()]
            rows.sort(key=lambda r: (r['label'].casefold(), r['key']))
            if query.project_id:
                relevant = {r['space_id'] for r in rows}
                spaces = [s for s in spaces if s['project_id'] == query.project_id or s['id'] in relevant]
            return {'profile': 'cospace.data-resources/0.1', 'workspace_id': principal.workspace_id,
                    'category': query.category, 'project_id': query.project_id, 'space_id': query.space_id,
                    'placement': query.placement, 'ownership': query.ownership, 'lifecycle': query.lifecycle,
                    'items': rows[query.offset:query.offset + query.limit], 'total': len(rows),
                    'spaces': spaces, 'can_manage': manager, 'status': 'partial' if issues else 'ready',
                    'issues': issues, 'offset': query.offset, 'limit': query.limit,
                    'next_offset': query.offset + query.limit if query.offset + query.limit < len(rows) else None,
                    'observed_at': report['observed_at'], 'source_files_rechecked': False}

    def managed_item(self, principal, policy, identity):
        _, items, _ = self.projection(principal, policy)
        item = next((v for v in items if v['resource_id'] == identity), None)
        if item is None:
            with self.projects.database() as db:
                scope = self.projects.scope(principal)
                _, projects, links = self.projects.state(db, scope)
                item = next((v for v in self.files.rows(principal, policy, db, scope, projects, links, self.records(db, scope))
                             if v['resource_id'] == identity), None)
        return item

    @staticmethod
    def require_owner(saved, change):
        if saved:
            previous = (saved.get('owner_kind', 'project'), saved['owner_project_id'])
            if previous != (change.owner_kind, change.owner_project_id):
                raise ProjectError('resource_owner_transfer_not_supported')
        elif change.owner_kind != 'project':
            raise ProjectError('resource_owner_transfer_not_supported')

    def change(self, principal, policy, change):
        if not policy.workspace_manager(principal):
            raise PermissionError('resource_management_denied')
        item = self.managed_item(principal, policy, change.resource_id)
        if item is None:
            raise PermissionError('resource_access_denied')
        if item['space_id']:
            policy.require(principal, item['space_id'], 'space.manage')
        scope, spec = self.projects.scope(principal), checksum(change.model_dump())
        with self.projects.database(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS data_resources(scope TEXT,id TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,id))')
            db.execute('CREATE TABLE IF NOT EXISTS resource_changes(scope TEXT,actor TEXT,request_id TEXT,spec TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,actor,request_id))')
            previous = db.execute('SELECT spec,record FROM resource_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, change.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('resource_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            _, projects, _ = self.projects.state(db, scope)
            require_active(db, scope, change.resource_id)
            project = projects.get(change.owner_project_id)
            if change.owner_kind == 'project' and (not project or project['status'] != 'active'):
                raise ProjectError('active_project_required')
            saved = self.records(db, scope).get(change.resource_id)
            if (saved['revision'] if saved else 0) != change.expected_revision:
                raise ProjectError('resource_revision_changed')
            if item['source_version']['version_id'] != change.expected_version:
                raise ProjectError('resource_source_changed')
            self.require_owner(saved, change)
            at = datetime.now(timezone.utc).isoformat()
            version = item['source_version'] | {'recorded_at': at}
            versions = dict(saved['versions']) if saved else {}
            versions.setdefault(version['version_id'], version)
            record = {'resource_id': change.resource_id, 'source_key': item['key'], 'space_id': item['space_id'],
                      'owner_kind': change.owner_kind, 'owner_project_id': change.owner_project_id, 'is_base': change.is_base,
                      'revision': change.expected_revision + 1, 'versions': versions}
            event = {'resource_id': change.resource_id, 'revision': record['revision'], 'actor': principal.subject,
                     'space_id': item['space_id'], 'changed_at': at, 'reason': change.reason,
                     'before': saved, 'after': record}
            db.execute('INSERT OR REPLACE INTO data_resources VALUES(?,?,?)', (scope, change.resource_id, json.dumps(record)))
            db.execute('INSERT INTO resource_changes VALUES(?,?,?,?,?)',
                       (scope, principal.subject, change.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}
