"""Workspace-scoped online scene creation; identity comes only from verified RP claims."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from packages.construction.preview_jobs import now
from packages.data.space_sources import SpaceSources
from packages.lifecycle.scene_initialization import WorkspaceScope, checksum
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.space_access import SpaceAccessPolicy


class WorkspaceScenesUnavailable(RuntimeError):
    pass


class WorkspaceScenesConflict(ValueError):
    pass


class Allocation(WorkspaceScope):
    allow_create: bool = False
    creator_subjects: list[str] = Field(default_factory=list, max_length=100)
    source_bindings: dict[str, str] = Field(default_factory=dict, max_length=100)

    @model_validator(mode='after')
    def valid(self):
        import re
        if (len(set(self.creator_subjects)) != len(self.creator_subjects)
                or any(not re.fullmatch(r'usr_[A-Za-z0-9_-]{1,150}', s) for s in self.creator_subjects)
                or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', s) or not re.fullmatch(r'[a-f0-9]{64}', h)
                       for s, h in self.source_bindings.items())):
            raise ValueError('invalid_workspace_allocation')
        return self


class WorkspaceSceneConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    profile: str = Field(pattern=r'^cospace.workspace-scenes/0\.1$')
    revision: int = Field(ge=1)
    workspaces: list[Allocation] = Field(max_length=10_000)

    @model_validator(mode='after')
    def unique(self):
        keys = [(v.issuer, v.org_id, v.workspace_id) for v in self.workspaces]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate_workspace_allocation')
        return self


class CreateScene(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    context_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=500)

    @field_validator('name', 'description')
    @classmethod
    def trim(cls, v, info):
        v = v.strip()
        if info.field_name == 'name' and not v:
            raise ValueError('scene_name_required')
        return v


class WorkspaceScenes:
    def __init__(self, directory, policies, sources, config=None, *, platform_access=False):
        self.directory, self.policies, self.sources = directory, policies, sources
        # Set only by the authenticated business assembly, behind its C2 gate.
        self.platform_access=platform_access
        self.runtime = directory.root.resolve().parent
        self.config = Path(config) if config else policies.path.parent/'workspace-scenes.json'
        self.required_marker = policies.path.parent/'.workspace-scenes-required'
        self.required = config is not None or self.config.exists() or self.required_marker.exists()
        original = Path('var/nyu').resolve()
        auth = policies.path.parent.resolve()
        if (self.runtime.is_relative_to(original) or original.is_relative_to(self.runtime)
                or auth.is_relative_to(self.runtime) or self.runtime.is_relative_to(auth)):
            raise ValueError('separate_workspace_scene_runtime_required')

    @staticmethod
    def scope(principal):
        return {k: getattr(principal, k) for k in ('issuer', 'org_id', 'workspace_id')}

    def allocation(self, principal):
        try:
            raw = self.config.read_bytes()
        except FileNotFoundError:
            if self.required:
                raise WorkspaceScenesUnavailable()
            return None, None
        except OSError as exc:
            raise WorkspaceScenesUnavailable() from exc
        try:
            config = WorkspaceSceneConfig.model_validate_json(raw)
            self.required = True
            try:
                with self.required_marker.open('x', encoding='utf-8') as marker:
                    marker.write('Workspace source allocation required; missing configuration must fail closed.\n')
            except FileExistsError:
                pass
            entry = next((v for v in config.workspaces if
                          {k: getattr(v, k) for k in self.scope(principal)} == self.scope(principal)), None)
            return config, entry
        except (ValueError,OSError) as exc:
            raise WorkspaceScenesUnavailable() from exc

    def context(self, principal):
        config, entry = self.allocation(principal)
        can_create = bool(self.platform_access and principal.workspace_owner or
                          entry and entry.allow_create and
                          (principal.workspace_owner or principal.subject in entry.creator_subjects))
        digest = checksum({'configuration': config.model_dump() if config else None,
                           'source_catalog': self.sources.fingerprints,
                           'scope': self.scope(principal), 'subject': principal.subject,
                           'platform_access':self.platform_access})
        return {'profile': 'cospace.workspace-scenes-context/0.1', 'enabled': config is not None or self.platform_access,
                'can_create': can_create, 'workspace_id': principal.workspace_id,
                'context_sha256': digest, 'configuration_revision': config.revision if config else 0}

    def scoped_sources(self, principal):
        config, entry = self.allocation(principal)
        # Absent config preserves explicitly installed legacy engineering deployments.
        # Once installed, an unlisted workspace has zero new source allocation.
        if config is None:
            return self.sources
        allowed = {k: self.sources.sources[k] for k, h in (entry.source_bindings.items() if entry else [])
                   if self.sources.fingerprints.get(k) == h}
        return SpaceSources(self.directory.root, allowed)

    @staticmethod
    def table(db):
        db.execute('CREATE TABLE IF NOT EXISTS workspace_scene_creations(id TEXT PRIMARY KEY,record TEXT NOT NULL)')

    def load(self, db, identity):
        self.table(db)
        row = db.execute('SELECT record FROM workspace_scene_creations WHERE id=?', (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def write_directory(self, records, identity):
        for kind, record in records.items():
            path = self.directory.root/kind/(record['id']+'.json')
            if path.exists():
                if json.loads(path.read_bytes()) != record:
                    raise WorkspaceScenesConflict('scene_directory_collision')
                continue
            pending = path.with_suffix('.'+identity+'.pending')
            with pending.open('w', encoding='utf-8') as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            pending.rename(path)

    def create(self, principal, request):
        with mutation_guard(self.policies.path.parent), mutation_guard(self.runtime):
            context = self.context(principal)
            if not context['can_create']:
                raise PermissionError('workspace_scene_creation_denied')
            if context['context_sha256'] != request.context_sha256:
                raise WorkspaceScenesConflict('workspace_scene_context_changed')
            scope = self.scope(principal)
            identity = 'create-'+checksum({'scope': scope, 'subject': principal.subject, 'request_id': request.request_id})[:32]
            space_id = 'space-'+identity[7:23]
            # Distinct namespace avoids replacing P5a's existing project record.
            project_id = 'project-'+checksum({'workspace_scene_directory': scope})[:16]
            spec = {'scope': scope, 'subject': principal.subject,
                    'request': request.model_dump(exclude={'context_sha256'}), 'runtime': str(self.runtime)}
            with closing(sqlite3.connect(self.policies.path, timeout=10)) as db:
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    saved = self.load(db, identity)
                    revision, policy = self.policies.load()
                    if saved:
                        if saved['spec'] != spec:
                            raise WorkspaceScenesConflict('scene_request_id_reused')
                        if saved['state'] == 'complete':
                            binding = next((b for b in policy.bindings if b.space_id == space_id), None)
                            grant = next((g for g in policy.grants if g.space_id == space_id and g.issuer == principal.issuer
                                          and g.subject == principal.subject and g.role == 'manager'), None)
                            if (binding is None or {k: getattr(binding, k) for k in scope} != scope or grant is None):
                                raise WorkspaceScenesConflict('created_scene_access_changed_no_repair')
                            self.write_directory_check(saved['records'])
                            return saved['receipt'] | {'created': False}
                    if not saved:
                        if any(b.space_id == space_id for b in policy.bindings):
                            raise WorkspaceScenesConflict('scene_binding_collision')
                        project_path = self.directory.root/'project'/(project_id+'.json')
                        project = (json.loads(project_path.read_bytes()) if project_path.exists() else
                                   {'profile': 'cospace.preview-project/0.1', 'id': project_id,
                                    'name': 'Workspace 场景目录', 'created_at': now()})
                        if project['id'] != project_id:
                            raise WorkspaceScenesConflict('scene_project_collision')
                        saved = {'id': identity, 'state': 'prepared', 'spec': spec,
                                 'records': {'project': project, 'space': {'profile': 'cospace.preview-space/0.1',
                                     'id': space_id, 'project_id': project_id, 'name': request.name,
                                     'description': request.description, 'created_at': now(),
                                     'publication_id': None, 'state': 'no_publication'}}, 'actor': principal.subject}
                        db.execute('INSERT INTO workspace_scene_creations VALUES(?,?)', (identity, json.dumps(saved)))
            # Intent survives a process exit. Partial files have no binding/grant.
            self.write_directory(saved['records'], identity)
            with closing(sqlite3.connect(self.policies.path, timeout=10)) as db:
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT revision,policy FROM policy WHERE id=1').fetchone()
                    revision, policy = row[0], SpaceAccessPolicy.model_validate_json(row[1])
                    if any(b.space_id == space_id for b in policy.bindings):
                        raise WorkspaceScenesConflict('scene_binding_collision')
                    # Recheck deployment allocation before committing ownership.
                    if self.context(principal) != context:
                        raise WorkspaceScenesConflict('workspace_scene_context_changed')
                    value = policy.model_dump()
                    value['bindings'].append(scope | {'space_id': space_id})
                    value['grants'].append({'issuer': principal.issuer, 'subject': principal.subject,
                                            'space_id': space_id, 'role': 'manager'})
                    revision = self.policies.write_transaction(db, SpaceAccessPolicy.model_validate(value),
                        expected_revision=revision, actor=principal.subject, reason='verified Workspace scene creation '+identity)
                    receipt = {'profile': 'cospace.workspace-scene-receipt/0.1', 'space_id': space_id,
                               'project_id': project_id, 'request_id': request.request_id, 'policy_revision': revision,
                               'workspace_id': principal.workspace_id, 'actor': principal.subject,
                               'created': True, 'quality': 'unverified', 'production_ready': False, 'robot_ready': False}
                    saved.update(state='complete', receipt=receipt)
                    db.execute('UPDATE workspace_scene_creations SET record=? WHERE id=?', (json.dumps(saved), identity))
            return receipt

    def write_directory_check(self, records):
        for kind, record in records.items():
            path = self.directory.root/kind/(record['id']+'.json')
            if not path.is_file() or json.loads(path.read_bytes()) != record:
                raise WorkspaceScenesConflict('created_scene_directory_changed_no_repair')
