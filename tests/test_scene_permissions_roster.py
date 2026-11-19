"""HTTP integration: current platform roster supplies targets, never extra authority."""
import pytest

from packages.infrastructure.platform_roster import RosterSnapshot, ProductRosterUnavailable
from packages.service.platform_business_http import BusinessAccess
from test_scene_permissions import shared_workbench, secured, runtime, owner
from test_platform_business import sign_in


NEW_MEMBER = 'usr_00000000-0000-4000-a000-000000000777'


def access_of(client):
    return next(m.kwargs['dispatch'].__self__ for m in client.app.user_middleware
                if isinstance(getattr(m.kwargs.get('dispatch'), '__self__', None), BusinessAccess))


@pytest.fixture
def roster_workbench(shared_workbench):
    _, client, *_ = shared_workbench
    state = {'names': {'usr_owner': 'Owner', NEW_MEMBER: 'New Member'}, 'calls': []}
    def read(principal):
        state['calls'].append(principal)
        return RosterSnapshot(dict(state['names']), 'current-version')
    access_of(client).scene_permissions.roster = read
    return shared_workbench, state


def test_platform_member_is_listed_before_first_product_visit_and_can_be_assigned(roster_workbench):
    runtime, state = roster_workbench
    _, client, _, _, _, _, spaces, policies, *_ = runtime
    before = policies.load()
    headers, data = owner(runtime)
    assert data['directory_complete'] and data['directory_source'] == 'platform_roster'
    assert data['directory_version'] == 'current-version'
    member = next(m for m in data['members'] if m['subject'] == NEW_MEMBER)
    assert member['roles'] == ['viewer'] and member['scene_count'] == 0
    assert policies.load() == before  # The roster never manufactures grants or visit records.
    assert client.post('/api/scene-permissions/grants', headers=headers, json={
        'expected_revision': data['revision'], 'subject': NEW_MEMBER, 'space_id': spaces[0]['id'],
        'role': 'engineer', 'reason': 'Project work'}).status_code == 200
    filtered = client.get('/api/scene-permissions?members_q=New&role=engineer').json()
    assert filtered['member_total'] == 1 and filtered['members'][0]['subject'] == NEW_MEMBER
    assert filtered['members'][0]['scene_count'] == 1 and len(state['calls']) == 3


def test_save_rechecks_platform_revocation_and_retains_local_grants(roster_workbench):
    runtime, state = roster_workbench
    _, client, _, _, _, _, spaces, policies, *_ = runtime
    state['names']['usr_engineer'] = 'Engineer'
    headers, data = owner(runtime)
    before = policies.load()
    del state['names']['usr_engineer']
    for path, fields in [('/grants', {'space_id': spaces[0]['id'], 'role': 'manager'}),
                         ('/scopes', {'space_ids': []})]:
        response = client.post('/api/scene-permissions'+path, headers=headers, json={
            'expected_revision': data['revision'], 'subject': 'usr_engineer', 'reason': 'Change', **fields})
        assert response.status_code == 403
    assert policies.load() == before
    report = client.get('/api/scene-permissions').json()
    assert 'usr_engineer' not in {m['subject'] for m in report['members']}


def test_scope_can_be_set_for_platform_member_without_local_records(roster_workbench):
    runtime, _ = roster_workbench
    _, client, *_ = runtime
    headers, data = owner(runtime)
    result = client.post('/api/scene-permissions/scopes', headers=headers, json={
        'expected_revision': data['revision'], 'subject': NEW_MEMBER, 'space_ids': [], 'reason': 'Prepare access'})
    assert result.status_code == 200
    member = client.get('/api/scene-permissions', params={'subject': NEW_MEMBER}).json()['selected_member']
    assert member['data_scope'] == 'selected' and member['scope_scene_ids'] == []
    assert member['roles'] == ['viewer']  # Restricting data never removes the default role.


def test_null_platform_name_does_not_fall_back_to_contact_or_old_visit(roster_workbench):
    runtime, state = roster_workbench
    _, client, *_ = runtime
    sign_in(runtime, 'usr_colleague')
    client.get('/api/spaces')
    state['names']['usr_colleague'] = None
    _, data = owner(runtime)
    member = next(m for m in data['members'] if m['subject'] == 'usr_colleague')
    assert member['display_name'] == '成员名称待补全'
    assert {m['subject'] for m in data['members']} == set(state['names'])


def test_members_paging_and_selected_target_are_joined_over_complete_roster(roster_workbench):
    runtime, state = roster_workbench
    _, client, *_ = runtime
    state['names'].update({f'usr_member_{n}': f'Member {n:03}' for n in range(60)})
    owner(runtime)
    report = client.get('/api/scene-permissions', params={'member_offset': 50, 'subject': NEW_MEMBER}).json()
    assert report['member_total'] == 62 and len(report['members']) == 12
    assert report['selected_member']['subject'] == NEW_MEMBER


def test_viewer_cannot_enumerate_roster_and_summary_does_not_read_it(roster_workbench):
    runtime, state = roster_workbench
    _, client, *_ = runtime
    sign_in(runtime, NEW_MEMBER)
    result = client.get('/api/scene-permissions').json()
    assert not result['can_manage'] and 'members' not in result and not state['calls']
    owner(runtime)
    state['calls'].clear()
    assert client.get('/api/scene-permissions?summary=true').status_code == 200
    assert not state['calls']


def test_upstream_failure_is_an_explicit_error_and_never_uses_product_records(roster_workbench):
    runtime, _ = roster_workbench
    _, client, _, _, _, _, spaces, policies, *_ = runtime
    headers, data = owner(runtime)
    before = policies.load()
    def fail(_):
        raise ProductRosterUnavailable('private-upstream-detail')
    access_of(client).scene_permissions.roster = fail
    response = client.get('/api/scene-permissions')
    assert response.status_code == 503 and 'private-upstream-detail' not in response.text
    assert 'members' not in response.json()
    response = client.post('/api/scene-permissions/grants', headers=headers, json={
        'expected_revision': data['revision'], 'subject': NEW_MEMBER, 'space_id': spaces[0]['id'],
        'role': 'engineer', 'reason': 'Project work'})
    assert response.status_code == 503 and policies.load() == before


def test_manager_stays_scene_bounded_and_grant_read_never_grants_platform_admin(roster_workbench):
    runtime, state = roster_workbench
    _, client, _, _, _, _, spaces, policies, *_ = runtime
    headers, _ = sign_in(runtime, 'usr_manager')
    data = client.get('/api/scene-permissions').json()
    assert data['can_manage'] and not data['can_manage_scope']
    assert [s['id'] for s in data['scenes']] == [spaces[0]['id']]
    before = policies.load()
    assert client.post('/api/scene-permissions/grants', headers=headers, json={
        'expected_revision': data['revision'], 'subject': NEW_MEMBER, 'space_id': spaces[1]['id'],
        'role': 'engineer', 'reason': 'Other scene'}).status_code == 403
    assert client.post('/api/scene-permissions/scopes', headers=headers, json={
        'expected_revision': data['revision'], 'subject': NEW_MEMBER, 'space_ids': [], 'reason': 'Outside role'}).status_code == 403
    assert policies.load() == before and all(p.governance_roles == ('workspace:member',) for p in state['calls'])


@pytest.mark.parametrize('write', [False, True])
def test_operator_revocation_during_roster_read_is_rechecked(roster_workbench, write):
    from packages.service.space_access import SpaceAccessPolicy
    runtime, state = roster_workbench
    _, client, _, _, _, _, spaces, policies, *_ = runtime
    headers, _ = sign_in(runtime, 'usr_manager')
    revision, policy = policies.load()
    def revoke(_):
        value = policy.model_dump()
        value['grants'] = [g for g in value['grants'] if g['subject'] != 'usr_manager']
        policies.replace(SpaceAccessPolicy.model_validate(value), expected_revision=revision,
                         actor='owner', reason='Revoke member management during platform read')
        return RosterSnapshot(dict(state['names']), 'current-version')
    access_of(client).scene_permissions.roster = revoke
    if write:
        response = client.post('/api/scene-permissions/grants', headers=headers, json={
            'expected_revision': revision, 'subject': NEW_MEMBER, 'space_id': spaces[0]['id'],
            'role': 'engineer', 'reason': 'Project work'})
        assert response.status_code == 403
    else:
        response = client.get('/api/scene-permissions')
        assert response.status_code == 200 and response.json()['can_manage'] is False
        assert 'members' not in response.json()
    assert all(g.subject != NEW_MEMBER for g in policies.load()[1].grants)


def test_production_assembly_wires_workspace_roster_to_member_directory(shared_workbench, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from packages.infrastructure.platform_subscription import PlatformSubscriptions
    from packages.service.platform_auth_http import create_auth_app
    from packages.service import platform_business_http as module
    from experiments.scripts.serve_nyu_flow_preview import create_app
    from test_platform_subscription import production_client, config, facts, authorized_access
    rp, _, accounts, _, jobs, directory, _, policies, *_ = shared_workbench
    production_client(rp, accounts)
    calls = []
    class Roster:
        def __init__(self, client, settings):
            assert client is rp and settings.api_base == 'https://internal.example'
        def read(self, principal):
            calls.append(principal)
            return RosterSnapshot({NEW_MEMBER: 'New Member'}, 'production-wiring')
    monkeypatch.setattr(module, 'ProductRoster', Roster)
    subscriptions = PlatformSubscriptions(rp, config(), tmp_path/'platform-gate',
        fetch=lambda *_: facts(), fetch_access=authorized_access)
    access = BusinessAccess(rp, policies, directory, jobs, subscriptions=subscriptions, workspace_scene_visibility=True)
    app = create_auth_app(rp, business=create_app(None, jobs, space_directory=directory, platform_origin=rp.config.origin),
                          access=access, subscriptions=subscriptions)
    with TestClient(app, base_url=rp.config.origin, follow_redirects=False) as client:
        context = list(shared_workbench)
        context[1] = client
        _, report = owner(tuple(context))
        assert report['directory_complete'] and report['directory_version'] == 'production-wiring'
        assert [m['subject'] for m in report['members']] == [NEW_MEMBER]
        assert report['members'][0]['roles'] == ['viewer']
        assert len(calls) == 1 and calls[0].workspace_id == 'ws_mock'
