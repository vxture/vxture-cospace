"""Login context comes from a platform-verified token, never browser authority."""
from urllib.parse import parse_qs, urlsplit
import pytest
from test_platform_login import runtime, begin

ORG = '11111111-1111-4111-8111-111111111111'
WORKSPACE = '22222222-2222-4222-8222-222222222222'


def test_login_forwards_scope_hints_and_preserves_return(runtime):
    rp, client, _, _ = runtime
    response = client.get('/auth/login', params={'tenant_hint': ORG, 'workspace_hint': WORKSPACE, 'returnTo': '/services'})
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers['location']).query)
    assert query['tenant_hint'] == [ORG] and query['workspace_hint'] == [WORKSPACE]
    pending = rp.store.get('state', query['state'][0])
    assert pending['return_to'] == '/services' and pending['hints']['workspace_hint'] == WORKSPACE


@pytest.mark.parametrize('params', [
    {'tenant_hint': 'invalid'}, {'workspace_hint': WORKSPACE},
    [('tenant_hint', ORG), ('tenant_hint', ORG)],
])
def test_invalid_or_ambiguous_hint_rejected(runtime, params):
    _, client, _, _ = runtime
    assert client.get('/auth/login', params=params).status_code == 400


def test_idp_fallback_cannot_silently_enter_a_different_workspace(runtime):
    rp, client, accounts, _ = runtime
    query, code = begin(rp, client, accounts, tenant_hint=ORG, workspace_hint=WORKSPACE)
    response = client.get('/auth/callback', params={'state': query['state'], 'code': code})
    assert response.status_code == 400
    assert client.get('/api/auth/session').json()['authenticated'] is False
