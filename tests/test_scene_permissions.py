"""End-to-end membership bootstrap, scope isolation and revisioned grant changes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3
import pytest
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from packages.service.scene_permissions import GrantChange, PermissionConflict


@pytest.fixture
def shared_workbench(secured, tmp_path):
    """Exercise the real product assembly, which enables the shared viewer baseline."""
    from fastapi.testclient import TestClient
    from experiments.scripts.serve_platform_workbench import assemble
    import shutil
    rp, _, _, _, jobs, directory, _, policies, *_ = secured
    config = tmp_path/'empty-sources.json'
    config.write_text('{"profile":"cospace.preview-sources/0.1","sources":[]}', encoding='utf-8')
    sample = tmp_path/'shared-product'
    sample.mkdir()
    for source, name in ((directory.root, 'preview-directory'), (jobs.root, 'preview-builds'), (jobs.inputs.root, 'preview-inputs')):
        shutil.copytree(source, sample/name)
    app = assemble(rp, policies, sample, sources_config=config)
    with TestClient(app, base_url=rp.config.origin, follow_redirects=False) as client:
        value = list(secured)
        value[1] = client
        yield tuple(value)


def test_product_members_see_all_workspace_scenes_without_request_or_saved_grant(shared_workbench):
    _, c, _, _, _, _, spaces, policies, *_ = shared_workbench
    before = policies.load()
    sign_in(shared_workbench, 'usr_colleague')
    report = c.get('/api/spaces').json()
    assert {s['id'] for s in report['spaces']} == {s['id'] for s in spaces}
    for scene in report['spaces']:
        assert set(scene['capabilities']) == {'space.preview', 'space.query', 'recipient.read'}
        assert c.get('/api/spaces/'+scene['id']).status_code == 200
    permissions = c.get('/api/scene-permissions').json()
    assert permissions['default_role'] == 'viewer' and not permissions['requested']
    assert not permissions['can_manage']
    assert policies.load() == before  # Viewing never manufactures individual grants.


@pytest.mark.parametrize('subject', ['usr_colleague', 'usr_local_test', 'usr_engineer', 'usr_manager'])
def test_shared_visibility_does_not_grant_other_scene_operations(shared_workbench, subject):
    _, c, _, _, _, _, spaces, _, _, new = shared_workbench
    headers, _ = sign_in(shared_workbench, subject)
    assert len(c.get('/api/spaces').json()['spaces']) == len(spaces)
    assert c.get('/api/source-settings', params={'space_id': spaces[1]['id']}).status_code == 403
    if subject in ('usr_colleague', 'usr_local_test'):
        assert c.get('/publications/'+new['id']+'/offline.zip').status_code == 403
    assert c.post('/api/scene-permissions/grants', json=body(c.get('/api/scene-permissions').json(), spaces[0]['id']), headers=headers).status_code == 403  # Unknown target is never granted.


def test_shared_scene_role_changes_and_removing_extra_permissions_keeps_viewing(shared_workbench):
    _, c, accounts, _, _, _, spaces, *_ = shared_workbench
    request_access(shared_workbench)
    for role in ('engineer', 'manager', None):
        headers, data = owner(shared_workbench)
        assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], role=role), headers=headers).status_code == 200
        accounts.roles = ['workspace:member']
        sign_in(shared_workbench, 'usr_colleague')
        scenes = c.get('/api/spaces').json()['spaces']
        assert len(scenes) == len(spaces)
        first = next(s for s in scenes if s['id'] == spaces[0]['id'])
        assert ('data.manage' in first['capabilities']) == (role is not None)
        assert c.get('/api/source-settings', params={'space_id': spaces[0]['id']}).status_code == (200 if role else 403)


def test_shared_visibility_never_crosses_workspaces_or_bypasses_platform_gate(shared_workbench):
    from packages.infrastructure.platform_subscription import ApplicationAccessDenied
    from packages.service.platform_business_http import BusinessAccess
    _, c, accounts, _, _, _, spaces, *_ = shared_workbench
    accounts.workspace = 'ws_foreign'
    sign_in(shared_workbench, 'usr_colleague')
    assert c.get('/api/spaces').json()['spaces'] == []
    assert c.get('/api/spaces/'+spaces[0]['id']).status_code == 403
    accounts.workspace = 'ws_mock'
    sign_in(shared_workbench, 'usr_colleague')
    access = next(m.kwargs['dispatch'].__self__ for m in c.app.user_middleware
                  if isinstance(getattr(m.kwargs.get('dispatch'), '__self__', None), BusinessAccess))
    class Denied:
        def require(self, *args, **kwargs):
            raise ApplicationAccessDenied()
    access.subscriptions = Denied()
    assert c.get('/api/spaces').status_code == 403
    assert c.get('/api/spaces/'+spaces[0]['id']).status_code == 403


@pytest.mark.parametrize('changes', [{'issuer': 'https://foreign.invalid'}, {'org_id': 'org_other'}, {'workspace_id': 'ws_other'}])
def test_shared_policy_requires_exact_scene_tenant_binding(changes):
    from test_space_access import policy, principal, A, B
    from packages.service.space_access import WorkspaceSceneAccessPolicy
    shared = WorkspaceSceneAccessPolicy.model_validate(policy().model_dump())
    member = principal(subject='usr_colleague')
    assert shared.visible(member, [{'id': A}, {'id': B}]) == [{'id': A}, {'id': B}]
    assert shared.visible(replace(member, **changes), [{'id': A}, {'id': B}]) == []
    assert shared.capabilities(member, 'space-'+'f'*16) == frozenset()


@pytest.mark.parametrize('subject,role', [('usr_engineer', 'engineer'), ('usr_manager', 'manager')])
def test_product_engineer_and_manager_create_scenes_without_role_escalation(shared_workbench, subject, role):
    _, c, _, _, _, _, _, policies, *_ = shared_workbench
    headers, _ = sign_in(shared_workbench, subject)
    context = c.get('/api/workspace-scenes').json()
    assert context['can_create']
    request = {'request_id': 'd'*32, 'name': 'Role-created scene', 'context_sha256': context['context_sha256']}
    saved = c.post('/api/workspace-scenes', json=request, headers=headers)
    assert saved.status_code == 201, saved.text
    space = saved.json()['space_id']
    _, policy = policies.load()
    assert next(g.role for g in policy.grants if g.subject == subject and g.space_id == space) == role
    permissions = c.get('/api/scene-permissions').json()
    assert permissions['can_manage'] == (role == 'manager')
    assert c.get('/api/ontology-authoring').json()['can_edit'] == (role == 'manager')
    replay = c.post('/api/workspace-scenes', json=request, headers=headers)
    assert replay.status_code in (200, 201), replay.text


def test_manager_manages_only_assigned_scene_and_revocation_is_live(shared_workbench):
    _, c, accounts, _, _, _, spaces, policies, *_ = shared_workbench
    request_access(shared_workbench)
    headers, _ = sign_in(shared_workbench, 'usr_manager')
    data = c.get('/api/scene-permissions').json()
    assert data['can_manage']
    assert [s['id'] for s in data['scenes']] == [spaces[0]['id']]
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[1]['id'], role='engineer'), headers=headers).status_code == 403
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], role='engineer'), headers=headers).status_code == 200
    revision, policy = policies.load()
    value = policy.model_dump()
    for grant in value['grants']:
        if grant['subject'] == 'usr_manager':
            grant['role'] = 'engineer'
    from packages.service.space_access import SpaceAccessPolicy
    policies.replace(SpaceAccessPolicy.model_validate(value), expected_revision=revision, actor='owner', reason='Revoke member administration')
    assert c.get('/api/scene-permissions').json()['can_manage'] is False
    assert c.get('/api/ontology-authoring').json()['can_edit'] is False
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], role='manager'), headers=headers).status_code == 403


def request_access(secured, subject='usr_colleague'):
    _, client, *_ = secured
    headers, _ = sign_in(secured, subject)
    assert client.post('/api/scene-permissions/requests', json={}, headers=headers).status_code == 200
    return headers


def owner(secured):
    _, client, accounts, *_ = secured
    accounts.roles = ['workspace:owner']
    headers, _ = sign_in(secured, 'usr_owner')
    return headers, client.get('/api/scene-permissions').json()


def body(data, space_id, **changes):
    return {'expected_revision': data['revision'], 'subject': 'usr_colleague', 'space_id': space_id,
            'role': 'viewer', 'reason': 'Project collaboration'} | changes


def test_request_grant_change_and_revoke_visible_scene(secured):
    _, c, accounts, _, _, _, spaces, policies, *_ = secured
    sign_in(secured, 'usr_colleague')
    assert c.get('/api/spaces').json()['spaces'] == []
    mine = c.get('/api/scene-permissions').json()
    assert not mine['can_manage'] and not mine['requested']
    assert not {'members', 'grants', 'scenes', 'history'} & mine.keys()
    headers = request_access(secured)
    revision = policies.load()[0]
    assert c.post('/api/scene-permissions/requests', json={}, headers=headers).status_code == 200
    assert policies.load()[0] == revision
    assert c.get('/api/spaces').json()['spaces'] == []
    headers, data = owner(secured)
    assert len([m for m in data['members'] if m['subject'] == 'usr_colleague']) == 1
    assert {s['id'] for s in data['scenes']} == {s['id'] for s in spaces}
    for role in ('viewer', 'engineer', 'manager', None):
        change = body(data, spaces[0]['id'], role=role)
        saved = c.post('/api/scene-permissions/grants', json=change, headers=headers)
        assert saved.status_code == 200, saved.text
        data = c.get('/api/scene-permissions').json()
        assert data['revision'] == saved.json()['revision']
        assert data['history'][0]['role'] == role
        assert data['history'][0]['actor'] == 'usr_owner'
        # Verify the actual business directory, rather than just saved grant JSON.
        accounts.roles = ['workspace:member']
        sign_in(secured, 'usr_colleague')
        visible = c.get('/api/spaces').json()['spaces']
        assert [s['id'] for s in visible] == ([spaces[0]['id']] if role else [])
        direct = c.get('/api/spaces/'+spaces[0]['id'])
        assert direct.status_code == (200 if role else 403)
        headers, data = owner(secured)
    assert len(data['history']) == 4


@pytest.mark.parametrize('user', ['usr_colleague', 'usr_local_test', 'usr_engineer'])
def test_engineer_and_viewer_cannot_manage_members(secured, user):
    _, c, _, _, _, _, spaces, *_ = secured
    headers, _ = sign_in(secured, user)
    data = c.get('/api/scene-permissions').json()
    assert data['can_manage'] is False
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id']), headers=headers).status_code == 403


def test_csrf_forged_identity_unknown_member_and_invalid_fields(secured):
    _, c, _, _, _, _, spaces, policies, *_ = secured
    headers, _ = sign_in(secured, 'usr_colleague')
    assert c.post('/api/scene-permissions/requests', json={}).status_code == 403
    assert c.post('/api/scene-permissions/requests', json={'subject': 'usr_victim'}, headers=headers).status_code == 422
    assert c.post('/api/scene-permissions/requests', json={}, headers=headers | {'Origin': 'https://other.invalid'}).status_code == 403
    headers, data = owner(secured)
    original = policies.load()
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id']), headers=headers).status_code == 403
    for changes in ({'role': 'owner'}, {'subject': '../alice'}, {'reason': '  '}, {'expected_revision': True}, {'all_spaces': True}):
        assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], **changes), headers=headers).status_code == 422
    assert policies.load() == original


def test_scope_isolation_including_shared_subject_and_owner_baseline(secured):
    _, c, accounts, _, _, _, spaces, policies, *_ = secured
    request_access(secured)
    headers, data = owner(secured)
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id']), headers=headers).status_code == 200
    accounts.workspace = 'ws_other'
    request_access(secured)
    headers, foreign = owner(secured)
    assert foreign['scenes'] == [] and foreign['grants'] == [] and foreign['history'] == []
    assert [m['subject'] for m in foreign['members']] == ['usr_colleague']
    assert c.post('/api/scene-permissions/grants', json=body(foreign, spaces[0]['id']), headers=headers).status_code == 403
    accounts.workspace = 'ws_mock'
    headers, data = owner(secured)
    # Existing explicit grants remain manageable without a new request.
    saved = c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], subject='usr_local_test', role=None), headers=headers)
    assert saved.status_code == 200
    assert len(c.get('/api/spaces').json()['spaces']) == len(spaces)
    assert c.get('/api/scene-permissions?workspace_id=ws_other').status_code == 422


def test_stale_revision_noop_and_atomic_audit(secured):
    _, c, _, _, _, _, spaces, policies, *_ = secured
    request_access(secured)
    headers, data = owner(secured)
    change = body(data, spaces[0]['id'])
    assert c.post('/api/scene-permissions/grants', json=change, headers=headers).status_code == 200
    before = policies.load()
    assert c.post('/api/scene-permissions/grants', json=change | {'role': 'manager'}, headers=headers).status_code == 409
    assert policies.load() == before
    current = c.get('/api/scene-permissions').json()
    saved = c.post('/api/scene-permissions/grants', json=change | {'expected_revision': current['revision']}, headers=headers)
    assert saved.json() == {'revision': current['revision'], 'changed': False}
    assert len(c.get('/api/scene-permissions').json()['history']) == 1


def test_concurrent_grant_changes_only_one_wins(secured):
    rp, c, _, _, _, directory, spaces, policies, *_ = secured
    from packages.service.scene_permissions import ScenePermissions
    request_access(secured)
    headers, data = owner(secured)
    # Resolve an actual verified principal for the service-level race.
    session, _ = rp.resolve(c.cookies.get(rp.config.cookie_name), active=False, require_access=True)
    principal = rp.verifier.verify(session['access_token'])
    service = ScenePermissions(policies, directory)
    def write(role):
        try:
            return service.change(principal, GrantChange.model_validate(body(data, spaces[0]['id'], role=role)))['changed']
        except PermissionConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ['viewer', 'engineer']))
    assert results.count(True) == results.count('conflict') == 1
    report = service.read(principal)
    assert len(report['history']) == 1
    # Changing only the org/issuer cannot reuse workspace requests or grants.
    for changed in ({'org_id': 'org_other'}, {'issuer': 'https://foreign.invalid'}):
        foreign = replace(principal, **changed)
        assert service.read(foreign)['members'] == []
        with pytest.raises(PermissionError):
            service.change(foreign, GrantChange.model_validate(body(report, spaces[0]['id'])))


def test_audit_failure_rolls_back_grant_and_policy_history(secured):
    _, c, _, _, _, _, spaces, policies, *_ = secured
    request_access(secured)
    headers, data = owner(secured)
    before = policies.load()
    with sqlite3.connect(policies.path) as db:
        db.execute("CREATE TRIGGER fail_access_audit BEFORE INSERT ON scene_access_events BEGIN SELECT RAISE(ABORT, 'failed'); END")
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id']), headers=headers).status_code == 503
    assert policies.load() == before
    assert c.get('/api/scene-permissions').json()['history'] == []


def test_permission_summary_returns_only_self_roles_without_admin_lists(shared_workbench):
    _, c, accounts, *_ = shared_workbench
    owner(shared_workbench)
    summary = c.get('/api/scene-permissions?summary=true').json()
    assert summary['self_roles'] == ['owner']
    assert not {'members', 'scenes', 'grants', 'history'} & summary.keys()
    accounts.roles = ['workspace:member']
    sign_in(shared_workbench, 'usr_engineer')
    assert set(c.get('/api/scene-permissions?summary=true').json()['self_roles']) == {'engineer', 'viewer'}
    accounts.workspace = 'ws_foreign'
    sign_in(shared_workbench, 'usr_engineer')
    assert c.get('/api/scene-permissions?summary=true').json()['self_roles'] == ['viewer']


def test_permission_pages_search_and_selected_role_do_not_depend_on_grant_page(secured):
    _, c, *_ = secured
    owner(secured)
    all_data = c.get('/api/scene-permissions').json()
    first = c.get('/api/scene-permissions?limit=1').json()
    second = c.get('/api/scene-permissions?limit=1&scene_offset=1&member_offset=1').json()
    assert len(first['scenes']) == len(second['scenes']) == 1
    assert first['scenes'][0] != second['scenes'][0]
    assert first['scene_total'] == len(all_data['scenes'])
    grant = all_data['grants'][0]
    selected = c.get('/api/scene-permissions', params={'limit': 1, 'grant_offset': 100,
        'subject': grant['subject'], 'space': grant['space_id']}).json()
    assert selected['grants'] == [] and selected['selected_role'] == grant['role']
    filtered = c.get('/api/scene-permissions', params={'scenes_q': first['scenes'][0]['name']}).json()
    assert first['scenes'][0] in filtered['scenes']
    assert c.get('/api/scene-permissions?members_q=not-a-member').json()['members'] == []
    assert all(m['display_name'] != m['subject'] for m in all_data['members'])


@pytest.mark.parametrize('query', ['limit=51', 'member_offset=-1', 'unknown=1', 'limit=1&limit=2', 'summary=invalid'])
def test_permission_query_rejects_invalid_or_ambiguous_paging(secured, query):
    _, c, *_ = secured
    owner(secured)
    assert c.get('/api/scene-permissions?'+query).status_code == (403 if query == 'limit=1&limit=2' else 422)


def test_product_visit_registers_known_member_without_request_and_allows_scoped_role(shared_workbench):
    _, c, accounts, _, _, _, spaces, policies, *_ = shared_workbench
    before = policies.load()
    sign_in(shared_workbench, 'usr_colleague')
    assert c.get('/api/spaces').status_code == 200
    assert policies.load() == before
    assert not c.get('/api/scene-permissions').json()['requested']
    headers, data = owner(shared_workbench)
    assert data['directory_complete'] is False and data['directory_source'] == 'product_records'
    member = next(m for m in data['members'] if m['subject'] == 'usr_colleague')
    assert member['last_seen'] and member['roles'] == ['viewer'] and member['scene_count'] == 0
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], role='engineer'), headers=headers).status_code == 200
    engineers = c.get('/api/scene-permissions?role=engineer').json()
    member = next(m for m in engineers['members'] if m['subject'] == 'usr_colleague')
    assert member['roles'] == ['engineer'] and member['scene_count'] == 1
    assert all('engineer' in m['roles'] for m in engineers['members'])
    assert engineers['role_counts']['engineer'] == engineers['member_total']
    data = c.get('/api/scene-permissions').json()
    assert c.post('/api/scene-permissions/grants', json=body(data, spaces[0]['id'], role=None), headers=headers).status_code == 200
    member = next(m for m in c.get('/api/scene-permissions?role=viewer').json()['members'] if m['subject'] == 'usr_colleague')
    assert member['roles'] == ['viewer'] and member['scene_count'] == 0


def test_known_visits_isolate_workspace_and_role_projection(shared_workbench):
    _, c, accounts, *_ = shared_workbench
    accounts.workspace = 'ws_foreign'
    sign_in(shared_workbench, 'usr_foreign_visitor')
    assert c.get('/api/spaces').status_code == 200
    accounts.workspace = 'ws_mock'
    owner(shared_workbench)
    assert not any(m['subject'] == 'usr_foreign_visitor' for m in c.get('/api/scene-permissions').json()['members'])
    accounts.roles = ['workspace:member']
    sign_in(shared_workbench, 'usr_manager')
    data = c.get('/api/scene-permissions?role=engineer').json()
    assert all(m['scene_count'] <= 1 for m in data['members'])
    assert c.get('/api/scene-permissions?role=owner').status_code == 422


def test_platform_access_denial_does_not_register_a_product_visit(shared_workbench):
    from packages.infrastructure.platform_subscription import ApplicationAccessDenied
    from packages.service.platform_business_http import BusinessAccess
    _, c, _, _, _, _, _, policies, *_ = shared_workbench
    sign_in(shared_workbench, 'usr_denied_visitor')
    access = next(m.kwargs['dispatch'].__self__ for m in c.app.user_middleware
        if isinstance(getattr(m.kwargs.get('dispatch'), '__self__', None), BusinessAccess))
    class Denied:
        def require(self, *args, **kwargs):
            raise ApplicationAccessDenied()
    access.subscriptions = Denied()
    assert c.get('/api/spaces').status_code == 403
    with sqlite3.connect(policies.path) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='product_member_visits'").fetchone()
        assert not exists or not db.execute('SELECT 1 FROM product_member_visits WHERE subject=?', ('usr_denied_visitor',)).fetchone()


def test_visit_directory_pages_and_trusted_display_updates(shared_workbench):
    from packages.service.scene_permissions import ScenePermissions, PermissionQuery
    rp, c, _, _, _, directory, _, policies, *_ = shared_workbench
    owner(shared_workbench)
    session, _ = rp.resolve(c.cookies.get(rp.config.cookie_name), active=False, require_access=True)
    principal = rp.verifier.verify(session['access_token'])
    service = ScenePermissions(policies, directory, workspace_scene_visibility=True)
    before = policies.load()
    for index in range(35):
        service.observe(replace(principal, subject=f'usr_paged_{index}', display_name=f'访客{index}', governance_roles=('workspace:member',)))
    service.observe(replace(principal, subject='usr_paged_0', display_name='访客已更新', governance_roles=('workspace:member',)))
    first = service.read(principal, PermissionQuery(members_q='访客', role='viewer'))
    second = service.read(principal, PermissionQuery(members_q='访客', member_offset=25, role='viewer'))
    assert first['member_total'] == second['member_total'] == 35
    assert len(first['members']) == 25 and len(second['members']) == 10
    assert not {m['subject'] for m in first['members']} & {m['subject'] for m in second['members']}
    assert sum(m['display_name'] == '访客已更新' for m in first['members']+second['members']) == 1
    assert policies.load() == before
