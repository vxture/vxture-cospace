from test_platform_subscription import authorized_access
"""Platform authority: no product-side seat ledger or commercial quantity gate."""
from dataclasses import replace
import sqlite3
from fastapi.testclient import TestClient
import pytest

from packages.infrastructure.platform_subscription import PlatformSubscriptions
from packages.service.platform_business_http import BusinessAccess
from packages.service.platform_auth_http import create_auth_app
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_workspace_scenes import online
from test_platform_business import secured
from test_platform_login import runtime, login
from test_platform_subscription import production_client, facts, config, NOW, signed_event


@pytest.fixture
def authority_http(online, tmp_path):
    secured, scenes, user, _ = online
    rp, _, accounts, clock, jobs, directory, spaces, policies, *_ = secured
    production_client(rp, accounts)
    value = [facts()]
    subscriptions = PlatformSubscriptions(rp, config(cache_seconds=0), tmp_path/'subscription',
        fetch_access=authorized_access,fetch=lambda *_: value[0], now=lambda: clock[0], wall=lambda: NOW)
    access = BusinessAccess(rp, policies, directory, jobs, subscriptions=subscriptions)
    app = create_auth_app(rp, business=create_app(None, jobs, space_directory=directory, platform_origin=rp.config.origin),
                          access=access, subscriptions=subscriptions)
    with TestClient(app, base_url=rp.config.origin, follow_redirects=False) as client:
        def signin(subject, owner=False):
            accounts.subject = subject
            accounts.roles = ['workspace:owner' if owner else 'workspace:member']
            login(rp, client, accounts)
            return {'Origin': rp.config.origin, 'X-CoSpace-CSRF': client.get('/api/auth/session').json()['csrf']}
        yield client, signin, value, access, accounts, spaces, subscriptions


@pytest.mark.parametrize('limits', [{}, {'member.max':0,'scene.max':0},
    {'member.max':-1,'scene.max':-1}, {'member.max':1,'scene.max':1}])
def test_platform_authorized_members_are_not_subject_to_local_seat_gate(authority_http, limits):
    client, signin, value, access, _, spaces, _ = authority_http
    value[0] = facts(limits=limits)
    signin('usr_owner', True)
    assert client.get('/api/spaces').status_code == 200
    signin('usr_local_test')
    assert client.get('/api/spaces').status_code == 200
    assert client.get('/api/spaces/'+spaces[1]['id']).status_code == 403
    assert not (access.policies.path.parent/'product-seats.sqlite3').exists()


@pytest.mark.parametrize('limit', [0, 1, -1])
def test_scene_creation_executes_function_without_local_commercial_cap(authority_http, limit):
    client, signin, value, access, *_ = authority_http
    headers = signin('usr_manager')
    value[0] = facts(limits={'scene.max':limit})
    context = client.get('/api/workspace-scenes').json()
    body = {'name':'Platform authorized scene','request_id':'d'*32,'context_sha256':context['context_sha256']}
    assert client.post('/api/workspace-scenes',json=body,headers=headers).status_code == 201
    assert client.post('/api/workspace-scenes',json=body,headers=headers).status_code == 200
    assert client.post('/api/workspace-scenes',json=body|{'request_id':'e'*32},headers=headers).status_code == 201
    assert len(access.policies.load()[1].bindings) == 4


def test_retired_seat_management_routes_cannot_change_legacy_records(authority_http):
    client, signin, _, access, *_ = authority_http
    path=access.policies.path.parent/'product-seats.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE preserved_audit(record TEXT)')
        db.execute("INSERT INTO preserved_audit VALUES('historical record')")
    before=path.read_bytes()
    headers=signin('usr_owner',True)
    assert client.get('/api/product-seats').status_code == 403
    assert client.post('/api/product-seats',json={'active':False},headers=headers).status_code == 403
    assert client.get('/api/spaces').status_code == 200
    assert path.read_bytes() == before


def test_platform_revocation_and_scene_acl_still_apply(authority_http):
    client, signin, value, access, _, spaces, subscriptions = authority_http
    signin('usr_no_scene_grant')
    assert client.get('/api/spaces/'+spaces[0]['id']).status_code == 403
    signin('usr_local_test')
    assert client.get('/api/spaces').status_code == 200
    value[0] = facts(status=None,tier=None)
    subscriptions.webhook(*signed_event())
    assert client.get('/api/spaces').json()['detail'] == 'subscription_required'
    assert client.get('/api/auth/session').json()['authenticated']
    value[0] = facts(limits={'member.max':5})
    assert client.get('/api/spaces').status_code == 200
    assert not (access.policies.path.parent/'product-seats.sqlite3').exists()
