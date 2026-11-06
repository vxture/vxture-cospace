"""Real signatures, deterministic clock, no calls to the actual platform."""
import copy
import base64
import json
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey, OctKey
from pydantic import ValidationError
from packages.infrastructure.platform_identity import (
    PlatformVerifierConfig, PlatformTokenVerifier, IdentityRejected, IdentityUnavailable,
)

NOW = 1_800_000_000
ISSUER = 'https://accounts.vxture.com'


@pytest.fixture(scope='module')
def keys():
    return [RSAKey.generate_key(2048, parameters={'kid': str(i)}) for i in range(2)]


def claims(**changes):
    return dict(iss=ISSUER, aud='cospace', sub='usr_alice', iat=NOW-10,
                exp=NOW+300, userType='tenant_user', account_status='active',
                active_org='org_1', active_workspace='ws_1',
                roles=['workspace:member'], name='Alice') | changes


def signed(key, value=None, **headers):
    return jwt.encode({'alg': 'RS256', 'kid': key.kid} | headers,
                      claims() if value is None else value, key)


def verifier(keys, now=None, fetch=None):
    return PlatformTokenVerifier(PlatformVerifierConfig(
        issuer=ISSUER, audience='cospace', jwks_url=ISSUER+'/oidc/jwks'),
        fetch=fetch or (lambda _: {'keys': [k.as_dict(private=False) for k in keys]}),
        now=now or (lambda: NOW))


@pytest.mark.parametrize('aud', ['cospace', ['another', 'cospace']])
def test_verified_access_context_and_scoped_roles(keys, aud):
    p = verifier(keys).verify(signed(keys[0], claims(aud=aud, roles=[
        'workspace:owner', 'ORG:OWNER ', 'admin', 'owner', 'workspace:admin'])))
    assert (p.subject, p.org_id, p.workspace_id, p.display_name) == ('usr_alice', 'org_1', 'ws_1', 'Alice')
    assert p.governance_roles == ('org:owner', 'workspace:owner') and p.workspace_owner


@pytest.mark.parametrize('changes', [
    {'iss': 'https://evil.example'}, {'aud': 'yucer'}, {'aud': ['yucer']},
    {'exp': NOW-61}, {'iat': NOW+61}, {'nbf': NOW+61}, {'exp': NOW-10},
    {'exp': True}, {'iat': '1800000000'}, {'nbf': False},
    {'sub': 'opr_operator'}, {'sub': []}, {'userType': 'operator'}, {'userType': None},
    {'account_status': 'suspended'}, {'account_status': None},
    {'active_org': None}, {'active_workspace': ''}, {'active_workspace': '../ws'},
    {'roles': 'workspace:owner'}, {'roles': [123]}, {'roles': ['x']*65},
])
def test_bad_claims_rejected(keys, changes):
    with pytest.raises(IdentityRejected):
        verifier(keys).verify(signed(keys[0], claims(**changes)))


@pytest.mark.parametrize('field', ['iss', 'aud', 'sub', 'iat', 'exp', 'userType',
                                   'account_status', 'active_org', 'active_workspace', 'roles'])
def test_required_claims_cannot_default_into_authority(keys, field):
    value = claims(); value.pop(field)
    with pytest.raises(IdentityRejected):
        verifier(keys).verify(signed(keys[0], value))


def test_wrong_signature_and_id_token_are_not_api_credentials(keys):
    with pytest.raises(IdentityRejected):
        verifier([keys[0]]).verify(signed(keys[1], kid=keys[0].kid))
    value = {k: v for k, v in claims().items() if k not in (
        'active_org', 'active_workspace', 'roles', 'account_status', 'name')}
    value.update(sid='session1', nonce='login-only')
    with pytest.raises(IdentityRejected):
        verifier(keys).verify(signed(keys[0], value))


@pytest.mark.parametrize('header', [{'kid': None}, {'kid': ''}, {'jku': 'https://evil.example'},
    {'jwk': {}}, {'x5u': 'https://evil.example'}, {'x5c': []}, {'crit': []}])
def test_untrusted_headers_reject_before_key_fetch(keys, header):
    def forbidden(_):
        pytest.fail('untrusted header must not cause a key request')
    token = signed(keys[0]).split('.')
    # Assemble malformed headers independently of the signing library's own validation.
    token[0] = base64.urlsafe_b64encode(json.dumps({'alg': 'RS256', 'kid': '0'} | header).encode()).rstrip(b'=').decode()
    with pytest.raises(IdentityRejected):
        verifier(keys, fetch=forbidden).verify('.'.join(token))


def test_algorithm_downgrade_and_malformed_tokens_rejected(keys):
    hs = jwt.encode({'alg': 'HS256', 'kid': '0'}, claims(), OctKey.generate_key(256))
    for token in (hs, 'eyJhbGciOiJub25lIiwia2lkIjoiMCJ9.e30.', 'x', '', None, 'x'*32769):
        with pytest.raises(IdentityRejected):
            verifier(keys).verify(token)


def test_rotation_cache_backoff_and_key_service_failure_are_distinct(keys):
    clock = [NOW]; requests = []; available = [keys[0]]
    def fetch(url):
        requests.append(url)
        if available[0] is None:
            raise OSError('simulated offline')
        return {'keys': [k.as_dict(private=False) for k in available]}
    v = verifier(keys, now=lambda: clock[0], fetch=fetch)
    v.verify(signed(keys[0])); v.verify(signed(keys[0])); assert len(requests) == 1
    with pytest.raises(IdentityRejected): v.verify(signed(keys[1]))
    assert len(requests) == 1
    clock[0] += 6; available[:] = keys
    v.verify(signed(keys[1])); assert len(requests) == 2
    clock[0] += 301; available[:] = [None]
    with pytest.raises(IdentityUnavailable):
        v.verify(signed(keys[0], claims(exp=NOW+900)))
    assert len(requests) == 3
    # Restoring the key endpoint recovers verification; no login state was deleted.
    available[:] = keys
    assert v.verify(signed(keys[0], claims(exp=NOW+900))).subject == 'usr_alice'


@pytest.mark.parametrize('kind', ['private', 'duplicate', 'weak', 'key_ops', 'empty', 'invalid'])
def test_invalid_trusted_jwks_is_unavailable_not_user_logout(keys, kind):
    item = keys[0].as_dict(private=False)
    if kind == 'private': item = keys[0].as_dict(private=True)
    if kind == 'weak': item = RSAKey.generate_key(1024, parameters={'kid': '0'}).as_dict(private=False)
    if kind == 'key_ops': item['key_ops'] = ['sign']
    value = {'keys': [item, copy.deepcopy(item)] if kind == 'duplicate' else [item]}
    if kind == 'empty': value = {'keys': []}
    if kind == 'invalid': value = {'keys': [42]}
    with pytest.raises(IdentityUnavailable):
        verifier(keys, fetch=lambda _: value).verify(signed(keys[0]))


@pytest.mark.parametrize('url', ['http://accounts.vxture.com', 'https://user:pass@accounts.vxture.com',
    'https://accounts.vxture.com/?x=1', 'https://accounts.vxture.com/#x', 'file:///keys'])
def test_unsafe_endpoint_configuration(url):
    with pytest.raises(ValidationError):
        PlatformVerifierConfig(issuer=url, audience='cospace', jwks_url=url)


def test_explicit_dev_loopback_and_backchannel_address_are_independent(keys):
    config = PlatformVerifierConfig(issuer='http://localhost:3081', audience='cospace',
        jwks_url='https://internal.example/oidc/jwks', allow_loopback_http=True)
    urls = []
    def fetch(url):
        urls.append(url); return {'keys': [keys[0].as_dict(private=False)]}
    v = PlatformTokenVerifier(config, fetch=fetch, now=lambda: NOW)
    assert v.verify(signed(keys[0], claims(iss=config.issuer))).issuer == config.issuer
    assert urls == [config.jwks_url]
    with pytest.raises(ValidationError):
        PlatformVerifierConfig(issuer='http://outside.example', audience='x',
            jwks_url=config.jwks_url, allow_loopback_http=True)
