"""Business projects and scene associations; historical source ownership is immutable."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from packages.lifecycle.scene_initialization import checksum


class ProjectError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class ProjectUnavailable(RuntimeError):
    pass


ProjectId = Annotated[str, Field(pattern=r'^project-[a-f0-9]{16}$')]
SceneId = Annotated[str, Field(pattern=r'^space-[a-f0-9]{16}$')]


class Change(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError('text_required')
        return value.strip()


class ProjectCreate(Change):
    action: Literal['create']
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=500)

    @field_validator('name', 'description')
    @classmethod
    def trim_project_text(cls, value, info):
        value = value.strip()
        if info.field_name == 'name' and not value:
            raise ValueError('project_name_required')
        return value


class ProjectAdopt(ProjectCreate):
    action: Literal['adopt']
    legacy_project_id: ProjectId


class ProjectUpdate(ProjectCreate):
    action: Literal['update']
    project_id: ProjectId
    status: Literal['active', 'archived'] = 'active'


class ProjectAssociate(Change):
    action: Literal['associate']
    space_id: SceneId
    project_id: ProjectId | None


ProjectChange = TypeAdapter(Annotated[ProjectCreate | ProjectAdopt | ProjectUpdate | ProjectAssociate,
                                      Field(discriminator='action')])


class ProjectQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    view: Literal['projects', 'scenes', 'history'] = 'projects'
    project_id: ProjectId | None = None
    q: str = Field(default='', max_length=100)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class WorkspaceProjects:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory.root / 'business-projects.sqlite3'

    @staticmethod
    def scope(principal):
        return checksum({key: getattr(principal, key) for key in ('issuer', 'org_id', 'workspace_id')})

    @contextmanager
    def database(self, *, write=False):
        if not write and not self.path.exists():
            yield None
            return
        try:
            target = str(self.path) if write else self.path.resolve().as_uri() + '?mode=ro'
            with closing(sqlite3.connect(target, uri=not write, timeout=10)) as db:
                with db:
                    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                    if write:
                        db.execute('CREATE TABLE IF NOT EXISTS project_scopes(scope TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
                        db.execute('CREATE TABLE IF NOT EXISTS business_projects(scope TEXT, id TEXT, record TEXT NOT NULL, PRIMARY KEY(scope,id))')
                        db.execute('CREATE TABLE IF NOT EXISTS project_scene_links(scope TEXT, space_id TEXT, record TEXT NOT NULL, PRIMARY KEY(scope,space_id))')
                        db.execute('CREATE TABLE IF NOT EXISTS project_changes(scope TEXT, revision INTEGER, actor TEXT, request_id TEXT, spec TEXT, record TEXT NOT NULL, PRIMARY KEY(scope,revision), UNIQUE(scope,actor,request_id))')
                    yield db
        except PermissionError:
            raise
        except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
            raise ProjectUnavailable('business_projects_unavailable') from exc

    def state(self, db, scope):
        if db is None:
            return 0, {}, {}
        revision = db.execute('SELECT revision FROM project_scopes WHERE scope=?', (scope,)).fetchone()
        projects = {identity: json.loads(raw) for identity, raw in
                    db.execute('SELECT id,record FROM business_projects WHERE scope=?', (scope,))}
        links = {identity: json.loads(raw) for identity, raw in
                 db.execute('SELECT space_id,record FROM project_scene_links WHERE scope=?', (scope,))}
        return revision[0] if revision else 0, projects, links

    def scenes(self, principal, policy):
        return {s['id']: s for s in self.directory.list('space')
                if 'data.manage' in policy.capabilities(principal, s['id'])}

    def read(self, principal, policy, query):
        scope, scenes = self.scope(principal), self.scenes(principal, policy)
        manager = policy.workspace_manager(principal)
        with self.database() as db:
            revision, projects, links = self.state(db, scope)
            visible_ids = set(projects) if manager else {
                link['project_id'] for identity, link in links.items() if identity in scenes and link['project_id']}
            # A scene can move projects without transferring its resources. Keep
            # owners of that user's readable resources available in the picker.
            if not manager and db is not None and db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='data_resources'").fetchone():
                for row in db.execute('SELECT record FROM data_resources WHERE scope=?', (scope,)):
                    resource = json.loads(row[0])
                    if resource['space_id'] in scenes:
                        visible_ids.add(resource['owner_project_id'])
            if query.project_id and query.project_id not in visible_ids:
                raise PermissionError('business_project_access_denied')
            if query.view == 'history':
                if not manager:
                    raise PermissionError('business_project_access_denied')
                items = [json.loads(row[0]) for row in db.execute(
                    'SELECT record FROM project_changes WHERE scope=? ORDER BY revision DESC', (scope,))] if db else []
                items = [v for v in items if (not v.get('space_id') or v['space_id'] in scenes)
                         and (not query.project_id or v.get('project_id') == query.project_id
                              or (v.get('before') or {}).get('project_id') == query.project_id)]
            elif query.view == 'scenes':
                items = []
                for identity, scene in scenes.items():
                    link = links.get(identity, {})
                    project_id = link.get('project_id')
                    if query.project_id and project_id != query.project_id:
                        continue
                    items.append({'space_id': identity, 'name': scene['name'],
                                  'project_id': project_id, 'project_name': projects[project_id]['name'] if project_id else None,
                                  'association_state': 'associated' if project_id else 'unassigned',
                                  'origin_project_id': scene['project_id'],
                                  'can_manage': manager and 'space.manage' in policy.capabilities(principal, identity)})
            else:
                items = [record | {'scene_count': sum(identity in scenes and link['project_id'] == record['id']
                                                       for identity, link in links.items()),
                                   'scene_count_scope': 'authorized_scenes'}
                         for identity, record in projects.items() if identity in visible_ids
                         and (not query.project_id or identity == query.project_id)]
            q = query.q.strip().casefold()
            if q:
                items = [v for v in items if q in ' '.join(str(v.get(key) or '') for key in
                         ('name', 'id', 'space_id', 'project_id', 'reason')).casefold()]
            if query.view != 'history':
                items.sort(key=lambda v: (v['name'].casefold(), v.get('id', v.get('space_id'))))
            return {'profile': 'cospace.business-projects/0.1', 'workspace_id': principal.workspace_id,
                    'view': query.view, 'revision': revision, 'can_manage': manager,
                    'items': items[query.offset:query.offset + query.limit], 'total': len(items),
                    'offset': query.offset, 'limit': query.limit,
                    'next_offset': query.offset + query.limit if query.offset + query.limit < len(items) else None}

    def change(self, principal, policy, change):
        if not policy.workspace_manager(principal):
            raise PermissionError('business_project_management_denied')
        scope = self.scope(principal)
        scenes = self.scenes(principal, policy)
        if change.action == 'associate':
            policy.require(principal, change.space_id, 'data.manage')
            policy.require(principal, change.space_id, 'space.manage')
            if change.space_id not in scenes:
                raise PermissionError('business_project_management_denied')
        if change.action == 'adopt':
            technical = {'project-' + scope[:16],
                         'project-' + checksum({'workspace_scene_directory': {
                             key: getattr(principal, key) for key in ('issuer', 'org_id', 'workspace_id')}})[:16]}
            if change.legacy_project_id in technical:
                raise ProjectError('technical_project_requires_explicit_association')
            if change.legacy_project_id not in {s['project_id'] for s in scenes.values()}:
                raise PermissionError('business_project_management_denied')
            self.directory.read('project', change.legacy_project_id)
        spec = checksum(change.model_dump())
        with self.database(write=True) as db:
            revision, projects, links = self.state(db, scope)
            previous = db.execute('SELECT spec,record FROM project_changes WHERE scope=? AND actor=? AND request_id=?',
                                  (scope, principal.subject, change.request_id)).fetchone()
            if previous:
                if previous[0] != spec:
                    raise ProjectError('project_request_id_reused')
                return json.loads(previous[1]) | {'replayed': True}
            if revision != change.expected_revision:
                raise ProjectError('project_revision_changed')
            at = datetime.now(timezone.utc).isoformat()
            event = {'revision': revision + 1, 'action': change.action, 'actor': principal.subject,
                     'changed_at': at, 'reason': change.reason}
            if change.action == 'associate':
                project_id = change.project_id
                if project_id and (project_id not in projects or projects[project_id]['status'] != 'active'):
                    raise ProjectError('active_project_required')
                before = links.get(change.space_id, {'project_id': None})
                record = {'project_id': project_id, 'origin_project_id': scenes[change.space_id]['project_id'],
                          'revision': revision + 1, 'updated_at': at, 'updated_by': principal.subject}
                db.execute('INSERT OR REPLACE INTO project_scene_links VALUES(?,?,?)',
                           (scope, change.space_id, json.dumps(record)))
                event.update(space_id=change.space_id, project_id=project_id, before=before, after=record)
            else:
                if change.action == 'adopt':
                    identity = change.legacy_project_id
                elif change.action == 'update':
                    identity = change.project_id
                else:
                    identity = 'project-' + checksum({'scope': scope, 'actor': principal.subject,
                                                     'request_id': change.request_id})[:16]
                before = projects.get(identity)
                if change.action == 'update' and before is None:
                    raise ProjectError('business_project_not_found', 404)
                if change.action != 'update' and before is not None:
                    raise ProjectError('business_project_already_exists')
                status = change.status if change.action == 'update' else 'active'
                if status == 'archived' and any(link['project_id'] == identity for link in links.values()):
                    raise ProjectError('project_has_scene_associations')
                if status == 'archived' and db.execute("SELECT 1 FROM sqlite_master WHERE name='data_resources'").fetchone():
                    owned = db.execute('SELECT record FROM data_resources WHERE scope=?', (scope,))
                    if any(json.loads(row[0])['owner_project_id'] == identity for row in owned):
                        raise ProjectError('project_has_managed_resources')
                if status == 'archived' and db.execute("SELECT 1 FROM sqlite_master WHERE name='data_resource_uses'").fetchone():
                    uses = db.execute('SELECT record FROM data_resource_uses WHERE scope=?', (scope,))
                    if any((use := json.loads(row[0]))['project_id'] == identity and use['status'] == 'active' for row in uses):
                        raise ProjectError('project_has_resource_references')
                record = {'id': identity, 'name': change.name, 'description': change.description, 'status': status,
                          'created_at': before['created_at'] if before else at,
                          'created_by': before['created_by'] if before else principal.subject,
                          'updated_at': at, 'updated_by': principal.subject,
                          'legacy_project_id': before['legacy_project_id'] if before else
                          change.legacy_project_id if change.action == 'adopt' else None}
                db.execute('INSERT OR REPLACE INTO business_projects VALUES(?,?,?)', (scope, identity, json.dumps(record)))
                event.update(project_id=identity, before=before, after=record)
            db.execute('INSERT OR REPLACE INTO project_scopes VALUES(?,?)', (scope, revision + 1))
            db.execute('INSERT INTO project_changes VALUES(?,?,?,?,?,?)',
                       (scope, revision + 1, principal.subject, change.request_id, spec, json.dumps(event)))
            return event | {'replayed': False}
