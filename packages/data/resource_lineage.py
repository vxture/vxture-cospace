"""Read-only, permission-scoped resource/version/reference trace.

Only persisted registration and use edges are reported. Reference consumers
never receive source locations, unseen versions or other projects' uses.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from packages.data.resource_sharing_contract import ResourceId, VersionId, SharedSourceVersion
from packages.lifecycle.workspace_projects import ProjectId, SceneId, ProjectUnavailable


class LineageQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resource_id: ResourceId
    project_id: ProjectId | None = None
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)


class RegisteredVersion(SharedSourceVersion):
    recorded_at: str


class RegisteredResource(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    resource_id: ResourceId
    source_key: str = Field(min_length=1, max_length=512)
    space_id: SceneId | None
    owner_kind: str = 'project'
    owner_project_id: ProjectId | None
    is_base: bool
    revision: int = Field(ge=1)
    versions: dict[VersionId, RegisteredVersion] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def valid_record(self):
        if self.owner_kind not in ('project', 'workspace') or (self.owner_kind == 'project') != bool(self.owner_project_id):
            raise ValueError('resource_owner_invalid')
        for identity, version in self.versions.items():
            if identity != version.version_id or datetime.fromisoformat(version.recorded_at).tzinfo is None:
                raise ValueError('resource_version_invalid')
        return self


class ResourceLineage:
    def __init__(self, resources):
        self.resources, self.projects, self.sharing = resources, resources.projects, resources.sharing

    def registration(self, db, scope, identity):
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='data_resources'").fetchone():
            raise PermissionError('resource_trace_denied')
        row = db.execute('SELECT CASE WHEN LENGTH(record)<=1048576 THEN record END FROM data_resources WHERE scope=? AND id=?',
                         (scope, identity)).fetchone()
        if row is None:
            raise PermissionError('resource_trace_denied')
        try:
            value = RegisteredResource.model_validate_json(row[0]).model_dump()
        except ValidationError as exc:
            raise ProjectUnavailable('resource_registration_invalid') from exc
        if value['resource_id'] != identity:
            raise ProjectUnavailable('resource_registration_invalid')
        return value

    @staticmethod
    def owner(resource, projects):
        if resource['owner_kind'] == 'workspace':
            return '工作区共用'
        project = projects.get(resource['owner_project_id'])
        if project is None:
            raise ProjectUnavailable('resource_owner_invalid')
        return project['name']

    def source(self, principal, policy, db, scope, resource, projects):
        self.sharing.require_source(principal, policy, resource)
        item = self.resources.managed_item(principal, policy, resource['resource_id'])
        current = item['source_version']['version_id'] if item else None
        versions = []
        for version in resource['versions'].values():
            snapshot = self.sharing.snapshot(db, scope, resource['resource_id'], version['version_id'])
            versions.append(version | {'current': version['version_id'] == current if current else None,
                                       'snapshot_saved': snapshot is not None})
        label = item['label'] if item else resource['resource_id']
        kind = item['kind'] if item else None
        source = {'state': 'current' if item else 'unavailable', 'version_id': current,
                  'space_name': item['space_name'] if item else None, 'href': item['href'] if item else None}
        return {'label': label, 'kind': kind, 'owner': self.owner(resource, projects)}, source, versions

    def reference(self, resource, projects, uses):
        versions = {}
        for use in uses:
            version = use['snapshot']['source_version']
            versions[version['version_id']] = version | {'recorded_at': None, 'current': None, 'snapshot_saved': True}
        first = uses[0]['snapshot']
        source = {'state': 'restricted', 'version_id': None, 'space_name': None, 'href': None}
        return {'label': first['label'], 'kind': first['kind'], 'owner': self.owner(resource, projects)}, source, list(versions.values())

    @staticmethod
    def summary(uses):
        current = [use for use in uses if use['status'] == 'active']
        return {'linked_references': len(current), 'effective_references': sum(u['access_status'] == 'active' for u in current),
                'historical_references': len(uses) - len(current),
                'projects': len({use['project_id'] for use in current}), 'scope': 'visible_only'}

    def read(self, principal, policy, query):
        scope = self.projects.scope(principal)
        with self.projects.database() as db:
            _, projects, links = self.projects.state(db, scope)
            # Check the caller's entry scope before collecting relationship data.
            if query.project_id:
                self.sharing.require_target(principal, policy, query.project_id, projects, links, historical=True)
            resource = self.registration(db, scope, query.resource_id)
            if not query.project_id:
                self.sharing.require_source(principal, policy, resource)
            uses = self.sharing.visible_uses(principal, policy, db, scope, projects, links,
                                            project=query.project_id, resource=query.resource_id)
            if query.project_id:
                if not uses:
                    raise PermissionError('resource_trace_denied')
                info, source, versions = self.reference(resource, projects, uses)
            else:
                info, source, versions = self.source(principal, policy, db, scope, resource, projects)
            versions.sort(key=lambda v: (v['created_at'] or '', v['version_id']), reverse=True)
            uses.sort(key=lambda u: (u['updated_at'], u['id']), reverse=True)
            summary = self.summary(uses)
            return {'profile': 'cospace.resource-lineage/0.1', 'workspace_id': principal.workspace_id,
                    'resource_id': query.resource_id, 'project_id': query.project_id,
                    'view': 'reference' if query.project_id else 'source', 'resource': info, 'source': source,
                    'versions': versions, 'references': uses[query.offset:query.offset + query.limit],
                    'summary': summary, 'total': len(uses), 'offset': query.offset, 'limit': query.limit,
                    'next_offset': query.offset + query.limit if query.offset + query.limit < len(uses) else None,
                    'impact': {'scope': 'visible_only', 'retention_required': summary['linked_references'] > 0,
                               'global_assessment': 'not_assessed', 'physical_delete_supported': False},
                    'status': 'partial' if source['state'] == 'unavailable' else 'ready',
                    'observed_at': datetime.now(timezone.utc).isoformat(), 'source_files_rechecked': False}
