"""Workspace owner manages scene grants; members introduce themselves with verified claims."""
from contextlib import closing
import json
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator
from packages.construction.preview_jobs import now
from packages.infrastructure.platform_identity import IdentityUnavailable
from packages.service.space_access import SpaceAccessPolicy


class PermissionConflict(ValueError):
    pass


class GrantChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: int = Field(ge=1)
    subject: str = Field(pattern=r'^usr_[A-Za-z0-9_-]{1,150}$')
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    role: str | None = Field(pattern=r'^(viewer|engineer|manager)$')
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError('reason_required')
        return value.strip()


class PermissionQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: bool = False
    members_q: str = Field(default='', max_length=100)
    scenes_q: str = Field(default='', max_length=100)
    member_offset: int = Field(default=0, ge=0, le=1_000_000)
    scene_offset: int = Field(default=0, ge=0, le=1_000_000)
    grant_offset: int = Field(default=0, ge=0, le=1_000_000)
    subject: str = Field(default='', max_length=160)
    space: str = Field(default='', max_length=160)
    limit: int = Field(default=25, ge=1, le=50)


def page_items(items, query, offset, limit, label):
    matching = [item for item in items if query.casefold() in item[label].casefold()]
    return matching[offset:offset+limit], len(matching)


class ScenePermissions:
    def __init__(self, policies, directory, *, workspace_scene_visibility=False):
        self.policies, self.directory = policies, directory
        self.workspace_scene_visibility = workspace_scene_visibility

    @staticmethod
    def scope(principal):
        return principal.issuer, principal.org_id, principal.workspace_id

    @staticmethod
    def tables(db):
        db.execute('''CREATE TABLE IF NOT EXISTS scene_access_requests(
            issuer TEXT,org_id TEXT,workspace_id TEXT,subject TEXT,display_name TEXT,requested_at TEXT,
            PRIMARY KEY(issuer,org_id,workspace_id,subject))''')
        db.execute('''CREATE TABLE IF NOT EXISTS scene_access_events(
            revision INTEGER PRIMARY KEY,issuer TEXT,org_id TEXT,workspace_id TEXT,record TEXT)''')

    @staticmethod
    def exists(db, name):
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()

    def request(self, principal):
        # Subject, display name and scope are never accepted from a browser body.
        try:
            with closing(sqlite3.connect(self.policies.path, timeout=10)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                self.tables(db)
                db.execute('''INSERT INTO scene_access_requests VALUES(?,?,?,?,?,?)
                    ON CONFLICT(issuer,org_id,workspace_id,subject) DO UPDATE SET display_name=excluded.display_name''',
                    (*self.scope(principal), principal.subject, principal.display_name, now()))
        except sqlite3.Error as exc:
            raise IdentityUnavailable('scene_permissions_unavailable') from exc
        return {'requested': True}

    def read(self, principal, query=None):
        query = query or PermissionQuery()
        try:
            with closing(sqlite3.connect(self.policies.path.as_uri()+'?mode=ro', uri=True)) as db:
                # A single read snapshot keeps members, grants and revision consistent.
                db.execute('BEGIN')
                revision, raw = db.execute('SELECT revision,policy FROM policy WHERE id=1').fetchone()
                policy = SpaceAccessPolicy.model_validate_json(raw)
                scope = self.scope(principal)
                requests = db.execute('''SELECT subject,display_name,requested_at FROM scene_access_requests
                    WHERE issuer=? AND org_id=? AND workspace_id=? ORDER BY requested_at,subject''', scope).fetchall() if self.exists(db, 'scene_access_requests') else []
                requested = any(row[0] == principal.subject for row in requests)
                bound_ids = {b.space_id for b in policy.bindings if (b.issuer, b.org_id, b.workspace_id) == scope}
                can_manage = policy.workspace_manager(principal)
                result = {'workspace_id': principal.workspace_id, 'can_manage': can_manage,
                          'revision': revision, 'requested': requested,
                          'self_roles': ['owner'] if principal.workspace_owner else sorted({
                              g.role for g in policy.grants if g.issuer == principal.issuer
                              and g.subject == principal.subject and g.space_id in bound_ids} | ({'viewer'} if self.workspace_scene_visibility else set())),
                          'default_role': 'viewer' if self.workspace_scene_visibility else None}
                if not can_manage or query.summary:
                    return result
                return result | self.management_view(db, principal, policy, scope, query, requests)

        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise IdentityUnavailable('scene_permissions_unavailable') from exc

    def management_view(self, db, principal, policy, scope, query, requests):
        ids = policy.role_spaces(principal, {'manager'})
        scenes = [{'id': s['id'], 'name': s['name']} for s in self.directory.list('space') if s['id'] in ids]
        grants = [g.model_dump(include={'subject', 'space_id', 'role'}) for g in policy.grants
                  if g.issuer == principal.issuer and g.space_id in ids]
        members = {s: {'subject': s, 'display_name': n, 'requested_at': t} for s, n, t in requests}
        for grant in grants:
            members.setdefault(grant['subject'], {'subject': grant['subject'], 'display_name': '成员名称待补全', 'requested_at': None})
        events = [json.loads(row[0]) for row in db.execute('''SELECT record FROM scene_access_events
            WHERE issuer=? AND org_id=? AND workspace_id=? ORDER BY revision DESC LIMIT 50''', scope)] if self.exists(db, 'scene_access_events') else []
        member_page, member_total = page_items(list(members.values()), query.members_q, query.member_offset, query.limit, 'display_name')
        scene_page, scene_total = page_items(scenes, query.scenes_q, query.scene_offset, query.limit, 'name')
        selected_role = next((g['role'] for g in grants if g['subject'] == query.subject and g['space_id'] == query.space), None)
        visible_grants = [g for g in grants if not query.subject or g['subject'] == query.subject]
        names = {subject: member['display_name'] for subject, member in members.items()}
        scene_names = {scene['id']: scene['name'] for scene in scenes}
        def labeled(record):
            return record | {'display_name': names.get(record['subject'], '成员名称待补全'),
                             'scene_name': scene_names.get(record['space_id'], '场景名称待补全')}
        return {'members': member_page, 'scenes': scene_page,
                         'grants': [labeled(g) for g in visible_grants[query.grant_offset:query.grant_offset+query.limit]],
                         'member_total': member_total, 'scene_total': scene_total, 'grant_total': len(visible_grants),
                         'selected_role': selected_role,
                         'history': [labeled(e) | {'actor_name': names.get(e['actor'], '操作人名称待补全')}
                                     for e in events if e['space_id'] in ids]}

    def change(self, principal, change):
        try:
            with closing(sqlite3.connect(self.policies.path, timeout=10)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                revision, raw = db.execute('SELECT revision,policy FROM policy WHERE id=1').fetchone()
                policy = SpaceAccessPolicy.model_validate_json(raw)
                if change.space_id not in policy.role_spaces(principal, {'manager'}):
                    raise PermissionError('scene_permissions_denied')
                # Recheck ownership and revision inside the write transaction.
                binding = next((b for b in policy.bindings if b.space_id == change.space_id), None)
                if binding is None or (binding.issuer, binding.org_id, binding.workspace_id) != self.scope(principal):
                    raise PermissionError('scene_permissions_denied')
                if revision != change.expected_revision:
                    raise PermissionConflict('scene_permissions_changed')
                self.tables(db)
                known = db.execute('''SELECT 1 FROM scene_access_requests
                    WHERE issuer=? AND org_id=? AND workspace_id=? AND subject=?''', (*self.scope(principal), change.subject)).fetchone()
                ids = {b.space_id for b in policy.bindings if (b.issuer, b.org_id, b.workspace_id) == self.scope(principal)}
                if not known and not any(g.issuer == principal.issuer and g.space_id in ids and g.subject == change.subject for g in policy.grants):
                    raise PermissionError('scene_member_not_registered')
                value = policy.model_dump()
                previous = next((g for g in value['grants'] if (g['issuer'], g['subject'], g['space_id']) ==
                                 (principal.issuer, change.subject, change.space_id)), None)
                old_role = previous['role'] if previous else None
                if old_role == change.role:
                    return {'revision': revision, 'changed': False}
                value['grants'] = [g for g in value['grants'] if g is not previous]
                if change.role is not None:
                    value['grants'].append({'issuer': principal.issuer, 'subject': change.subject,
                                            'space_id': change.space_id, 'role': change.role})
                revision = self.policies.write_transaction(db, SpaceAccessPolicy.model_validate(value),
                    expected_revision=revision, actor=principal.subject, reason=change.reason)
                event = {'revision': revision, 'actor': principal.subject, 'subject': change.subject,
                         'space_id': change.space_id, 'previous_role': old_role, 'role': change.role,
                         'reason': change.reason, 'changed_at': now()}
                db.execute('INSERT INTO scene_access_events VALUES(?,?,?,?,?)',
                           (revision, *self.scope(principal), json.dumps(event, ensure_ascii=False)))
                return {'revision': revision, 'changed': True}
        except sqlite3.Error as exc:
            raise IdentityUnavailable('scene_permissions_unavailable') from exc
