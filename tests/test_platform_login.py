import json
import multiprocessing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from experiments.scripts.platform_auth_fixture import MockAccounts
from packages.infrastructure.platform_identity import IdentityRejected, IdentityUnavailable, PlatformTokenVerifier
from packages.infrastructure.platform_rp import RpConfig, safe_return
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.service.platform_login import PlatformLogin,LOGIN_SCOPES
from packages.service.platform_auth_http import create_auth_app

NOW = 1_800_000_000


def test_spatial_services_is_an_internal_application_return(runtime, tmp_path):
    rp, _, _, _ = runtime
    (tmp_path/'index.html').write_text('<main>CoSpace</main>', encoding='utf-8')
    assert safe_return('/services') == '/services'
    with TestClient(create_auth_app(rp, tmp_path), base_url=rp.config.origin) as client:
        response = client.get('/services')
        assert response.status_code == 200
        assert '<main>CoSpace</main>' in response.text
        assert client.get('/services.html').status_code == 404


def test_fetch_logout_keeps_origin_and_csrf_protection(runtime):
    rp,c,accounts,_=runtime
    login(rp,c,accounts)
    csrf=c.get('/api/auth/session').json()['csrf']
    assert c.post('/api/auth/logout').status_code==403
    assert c.post('/api/auth/logout',headers={'Origin':'https://foreign.example','X-CoSpace-CSRF':csrf}).status_code==403
    assert c.post('/api/auth/logout',headers={'Origin':rp.config.origin,'X-CoSpace-CSRF':'wrong'}).status_code==403
    response=c.post('/api/auth/logout',headers={'Origin':rp.config.origin,'X-CoSpace-CSRF':csrf})
    assert response.status_code==200 and response.json()['redirect_url']
    assert c.get('/api/auth/session').json()['authenticated'] is False


@pytest.fixture
def runtime(tmp_path):
    clock = [NOW]; accounts = MockAccounts(now=lambda:clock[0]).start()
    accounts.rp_origin = 'http://127.0.0.1:8768'
    cfg = RpConfig(issuer=accounts.issuer, backchannel=accounts.issuer, client_id=accounts.client_id,
        client_secret=SecretStr(accounts.secret), origin=accounts.rp_origin, allow_loopback_http=True,
        encryption_key=SecretStr(Fernet.generate_key().decode()))
    store = LocalRpStore(tmp_path/'sessions', cfg.encryption_key.get_secret_value())
    rp = PlatformLogin(cfg, store, now=lambda:clock[0])
    with TestClient(create_auth_app(rp, tmp_path/'no-assets'), base_url=cfg.origin, follow_redirects=False) as client:
        yield rp, client, accounts, clock
    accounts.stop()


def begin(rp, client, accounts, **params):
    response = client.get('/auth/login', params=params)
    assert response.status_code == 302
    q = {k:v[0] for k,v in parse_qs(urlsplit(response.headers['location']).query).items()}
    return q, accounts.issue(q)


def login(rp, client, accounts):
    q, code = begin(rp, client, accounts)
    response = client.get('/auth/callback', params={'state':q['state'],'code':code})
    assert response.status_code == 302, response.text
    return response, client.cookies.get(rp.config.cookie_name)


def activity(rp, client):
    session = client.get('/api/auth/session').json()
    return client.post('/api/auth/session', headers={'Origin':rp.config.origin,'X-CoSpace-CSRF':session['csrf']})


def test_authorize_scopes_fit_platform_default_and_refresh_still_rotates(runtime):
    rp, client, accounts, clock = runtime
    q, code = begin(rp, client, accounts)
    assert q['scope'].split()==list(LOGIN_SCOPES)==['openid','profile','email']
    assert set(q['scope'].split())<= {'openid','profile','email','phone'}
    assert q['code_challenge_method']=='S256' and 'offline_access' not in q['scope']
    response=client.get('/auth/callback',params={'state':q['state'],'code':code})
    assert response.status_code==302
    sid=client.cookies.get(rp.config.cookie_name);old=rp.store.get('session',sid)
    assert old['refresh_token']
    clock[0]+=70
    refreshed,_=rp.resolve(sid,active=True,require_access=True)
    assert refreshed['refresh_token']!=old['refresh_token']
    assert sum(c.get('grant_type')=='refresh_token' for c in accounts.calls)==1


def test_pkce_login_public_session_and_encrypted_server_storage(runtime):
    rp, client, accounts, clock = runtime
    assert client.get('/api/auth/session').json()['authenticated'] is False
    response, sid = login(rp, client, accounts)
    assert response.headers['location'] == rp.config.origin+'/space'
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie']
    assert 'Domain=' not in response.headers['set-cookie'] and 'Max-Age=' not in response.headers['set-cookie'].split(',')[0]
    result = client.get('/api/auth/session'); data = result.json()
    assert data['authenticated'] is True and data['user']['display_name'] == '模拟用户'
    assert data['authority_state'] == 'cached' and data['business_authorization'] is False
    assert not any(word in result.text for word in ('access_token','refresh_token','id_token','client_secret','eyJ'))
    stored = rp.store.get('session', sid)
    database = rp.store.path.read_bytes()
    assert all(value.encode() not in database for value in (stored['access_token'],stored['refresh_token'],sid,'usr_local_test'))
    assert result.headers['cache-control'] == 'no-store' and result.headers['referrer-policy'] == 'same-origin'


@pytest.mark.parametrize('target', ['https://evil.example', '//evil.example', '/auth/logout',
    '/workbench/../auth/login', '/workbench/%2e%2e/auth/login', '/workbench/%252e%252e/auth/login',
    '/workbench/\\evil', '/workbench/%0d%0aLocation:x'])
def test_open_redirects_reject_before_authorization(runtime, target):
    _, client, _, _ = runtime
    assert client.get('/auth/login', params={'returnTo':target}).status_code == 400


@pytest.mark.parametrize('kind', ['nonce','subject','sid','missing_browser','wrong_browser','expired','error'])
def test_bad_callback_never_creates_session(runtime, kind):
    rp, client, accounts, clock = runtime
    q, code = begin(rp, client, accounts)
    if kind == 'nonce': accounts.bad_nonce = True
    if kind == 'subject': accounts.bad_subject = True
    if kind == 'sid': accounts.bad_sid = True
    if kind in ('missing_browser','wrong_browser'):
        client.cookies.clear()
        if kind == 'wrong_browser': client.cookies.set(rp.config.cookie_name+'_oidc', 'x'*43)
    if kind == 'expired': clock[0] += 601
    params = {'state':q['state'],'code':code}
    if kind == 'error': params = {'state':q['state'],'error':'access_denied','error_description':'do_not_echo'}
    response = client.get('/auth/callback', params=params)
    assert response.status_code == 400 and 'do_not_echo' not in response.text
    assert client.get('/api/auth/session').json()['authenticated'] is False


def test_callback_single_use_duplicate_parameters_and_fixation(runtime):
    rp, client, accounts, _ = runtime
    _, old = login(rp, client, accounts)
    q, code = begin(rp, client, accounts)
    duplicate = client.get('/auth/callback', params=[('state',q['state']),('state',q['state']),('code',code)])
    assert duplicate.status_code == 400
    response = client.get('/auth/callback', params={'state':q['state'],'code':code})
    assert response.status_code == 302
    new = client.cookies.get(rp.config.cookie_name)
    assert new != old and rp.store.get('session', old) is None
    assert client.get('/auth/callback', params={'state':q['state'],'code':code}).status_code == 400
    assert rp.store.get('session', new)


def test_background_polling_never_prolongs_central_session(runtime):
    rp, client, accounts, clock = runtime
    login(rp, client, accounts); before = len(accounts.calls)
    clock[0] += 500
    for _ in range(3):
        data = client.get('/api/auth/session').json()
        assert data['authenticated'] and not data['access_ready']
    assert len(accounts.calls) == before
    assert activity(rp, client).json()['authority_state'] == 'confirmed'
    assert len(accounts.calls) == before+1 and accounts.calls[-1]['active'] is True


def test_accounts_unavailable_keeps_login_and_recovers_after_retry(runtime):
    rp, client, accounts, clock = runtime
    _, sid = login(rp, client, accounts); clock[0] += 91; accounts.unavailable = True
    data = activity(rp, client).json()
    assert data['authenticated'] and data['authority_state'] == 'unavailable'
    assert rp.store.get('session',sid)
    with pytest.raises(IdentityUnavailable): rp.resolve(sid, active=True, require_access=True)
    accounts.unavailable = False; clock[0] += 31
    assert activity(rp, client).json()['authority_state'] == 'confirmed'


def test_central_valid_false_ends_session_only_when_checked(runtime):
    rp, client, accounts, clock = runtime
    _, sid = login(rp, client, accounts); accounts.valid = False
    assert client.get('/api/auth/session').json()['authenticated']
    clock[0] += 91
    assert activity(rp, client).json()['authenticated'] is False
    assert rp.store.get('session', sid) is None


def test_refresh_rotates_once_without_changing_rp_cookie_and_central_schedule(runtime):
    rp, client, accounts, clock = runtime
    _, sid = login(rp, client, accounts)
    original = rp.store.get('session',sid); clock[0] += 70
    current, _ = rp.resolve(sid, active=True, require_access=True)
    assert current['refresh_token'] != original['refresh_token']
    assert current['next_check_at'] == original['next_check_at']
    assert not current['refresh_pending'] and client.cookies.get(rp.config.cookie_name) == sid
    rp.resolve(sid, active=True, require_access=True)
    assert sum(c.get('grant_type') == 'refresh_token' for c in accounts.calls) == 1


@pytest.mark.parametrize('failure', ['refused','lost_reply','crash_marker'])
def test_failed_or_interrupted_refresh_never_reuses_rotating_token_or_ends_login(runtime, failure):
    rp, client, accounts, clock = runtime
    _, sid = login(rp, client, accounts); clock[0] += 70
    if failure == 'refused': accounts.refresh_failure = True
    if failure == 'lost_reply': accounts.fail_after_consume = True
    if failure == 'crash_marker':
        session = rp.store.get('session',sid); session['refresh_pending'] = True; rp.store.put('session',sid,session)
    for _ in range(2):
        restarted = PlatformLogin(rp.config, LocalRpStore(rp.store.root,rp.config.encryption_key.get_secret_value()),now=rp.now)
        with pytest.raises(IdentityUnavailable): restarted.resolve(sid, active=True, require_access=True)
        assert restarted.resolve(sid)[0] is not None
    assert sum(c.get('grant_type') == 'refresh_token' for c in accounts.calls) == (0 if failure == 'crash_marker' else 1)
    assert client.get('/api/auth/session').json()['authenticated']


def test_session_survives_new_service_instance(runtime):
    rp, client, accounts, _ = runtime
    _, sid = login(rp, client, accounts)
    restarted = PlatformLogin(rp.config,LocalRpStore(rp.store.root,rp.config.encryption_key.get_secret_value()),now=rp.now)
    assert restarted.resolve(sid)[0]['principal']['subject'] == 'usr_local_test'


def test_wrong_encryption_key_reports_unavailable_not_signed_out(runtime):
    rp, client, accounts, _ = runtime
    _, sid = login(rp, client, accounts)
    wrong = PlatformLogin(rp.config,LocalRpStore(rp.store.root,Fernet.generate_key().decode()),now=rp.now)
    with TestClient(create_auth_app(wrong),base_url=rp.config.origin) as other:
        other.cookies.set(rp.config.cookie_name,sid)
        assert other.get('/api/auth/session').status_code == 503
    assert rp.store.get('session',sid) is not None


def test_csrf_origin_and_global_logout(runtime):
    rp, client, accounts, _ = runtime
    _, sid = login(rp, client, accounts); csrf = client.get('/api/auth/session').json()['csrf']
    assert client.get('/auth/logout').status_code == 405
    assert client.post('/auth/logout',data={'csrf':csrf}).status_code == 403
    assert client.post('/auth/logout',data={'csrf':'x'*43},headers={'Origin':rp.config.origin}).status_code == 403
    assert client.post('/api/auth/session',headers={'Origin':rp.config.origin}).status_code == 403
    assert client.post('/api/auth/session',headers={'Origin':'https://evil.example','X-CoSpace-CSRF':csrf}).status_code == 403
    response = client.post('/auth/logout',data={'csrf':csrf},headers={'Origin':rp.config.origin})
    assert response.status_code == 303 and rp.store.get('session',sid) is None
    q = parse_qs(urlsplit(response.headers['location']).query)
    assert q['client_id'] == [rp.config.client_id] and 'id_token_hint' in q
    assert q['post_logout_redirect_uri'] == [rp.config.origin+'/']
    assert client.get('/api/auth/session').json()['authenticated'] is False


def test_business_routes_are_closed_until_resource_acl_assembly(runtime):
    rp, client, accounts, _ = runtime
    assert client.get('/api/spaces').status_code == 401
    login(rp, client, accounts)
    for method,path in [('get','/api/spaces'),('post','/api/builds'),('head','/api/preview')]:
        assert getattr(client,method)(path).status_code == 503
    for path in ['/publications/preview-1234567890123456/','/candidates/build-one/','/spatial.npz']:
        assert client.get(path).status_code == 404


def refresh_child(config, root, sid, now, queue):
    try:
        cfg = RpConfig.model_validate(config)
        rp = PlatformLogin(cfg,LocalRpStore(root,cfg.encryption_key.get_secret_value()),now=lambda:now)
        session,_ = rp.resolve(sid,active=True,require_access=True)
        queue.put(session['principal']['subject'] == 'usr_local_test')
    except Exception:
        queue.put(False)


def test_two_real_processes_share_one_refresh_lock(runtime):
    rp, client, accounts, clock = runtime
    _, sid = login(rp,client,accounts); clock[0] += 70; accounts.refresh_delay = .15
    cfg = rp.config.model_dump(); cfg['client_secret'] = rp.config.client_secret.get_secret_value()
    cfg['encryption_key'] = rp.config.encryption_key.get_secret_value()
    ctx = multiprocessing.get_context('spawn'); queue = ctx.Queue()
    children = [ctx.Process(target=refresh_child,args=(cfg,str(rp.store.root),sid,clock[0],queue)) for _ in range(2)]
    try:
        for child in children: child.start()
        for child in children: child.join(15)
        assert all(child.exitcode == 0 for child in children)
        assert all(queue.get(timeout=2) for _ in children)
        assert sum(c.get('grant_type') == 'refresh_token' for c in accounts.calls) == 1
    finally:
        for child in children:
            if child.is_alive(): child.terminate(); child.join()
        queue.close()


def test_production_cookie_flags(runtime):
    rp, _, accounts, _ = runtime
    cfg = rp.config.model_copy(update={'origin':'https://cospace.example'})
    production = PlatformLogin(cfg,rp.store,now=rp.now)
    with TestClient(create_auth_app(production),base_url=cfg.origin,follow_redirects=False) as client:
        response = client.get('/auth/login')
        cookie = response.headers['set-cookie']
        assert '__Host-cospace_rp_oidc=' in cookie and 'Secure' in cookie and 'HttpOnly' in cookie and 'Domain=' not in cookie


def test_missing_env_configuration_is_closed(monkeypatch):
    for name in ('COSPACE_OIDC_CLIENT_ID','COSPACE_OIDC_CLIENT_SECRET','COSPACE_ORIGIN','COSPACE_SESSION_KEY'):
        monkeypatch.delenv(name,raising=False)
    with pytest.raises(ValueError,match='rp_configuration_incomplete'): RpConfig.from_env()


def test_client_configuration_change_cannot_reuse_session(runtime):
    rp, client, accounts, _ = runtime
    _, sid = login(rp,client,accounts)
    other = PlatformLogin(rp.config.model_copy(update={'client_id':'another-client'}),rp.store,now=rp.now)
    with pytest.raises(IdentityUnavailable): other.resolve(sid)
    assert rp.store.get('session',sid)


@pytest.mark.parametrize('body', [{'valid':False,'unexpected':1},{'valid':True},{'valid':True,'next_check_at':True},
    {'valid':True,'next_check_at':NOW-1},{'valid':'false'},{'valid':0},{'valid':1,'next_check_at':NOW+100}])
def test_malformed_status_does_not_end_login(runtime,body):
    rp, client, accounts, clock = runtime
    _, sid = login(rp,client,accounts); clock[0]+=91
    original_post=rp.transport.post
    rp.transport.post=lambda path,payload,**kwargs: body if path=='/oidc/session/status' else original_post(path,payload,**kwargs)
    result=activity(rp,client).json()
    assert result['authenticated'] and result['authority_state']=='unavailable'
    assert rp.store.get('session',sid)


def test_incomplete_refresh_payload_blocks_replay_but_preserves_login(runtime):
    rp, client, accounts, clock = runtime
    _, sid=login(rp,client,accounts);clock[0]+=70
    original_refresh=rp.transport.refresh
    def without_rotated_token(token):
        result=original_refresh(token);result.pop('refresh_token');return result
    rp.transport.refresh=without_rotated_token
    with pytest.raises(IdentityUnavailable):rp.resolve(sid,active=True,require_access=True)
    assert rp.store.get('session',sid)['refresh_blocked']
    assert rp.resolve(sid)[0] is not None

def test_public_authority_readiness_tracks_server_confirmation_window(runtime):
    rp, client, accounts, clock = runtime
    login(rp,client,accounts)
    calls=len(accounts.calls)
    recent=activity(rp,client).json()
    assert len(accounts.calls)==calls
    assert recent['authority_state']=='cached' and recent['authority_ready'] is True
    clock[0]+=91
    stale=client.get('/api/auth/session').json()
    assert len(accounts.calls)==calls
    assert stale['authority_state']=='cached' and stale['authority_ready'] is False
    accounts.unavailable=True
    unavailable=activity(rp,client).json()
    assert unavailable['authenticated'] and unavailable['authority_ready'] is False
    accounts.unavailable=False;clock[0]+=31
    recovered=activity(rp,client).json()
    assert recovered['authority_state']=='confirmed' and recovered['authority_ready'] is True


def test_account_switch_uses_oidc_chooser(runtime):
    from urllib.parse import urlsplit, parse_qs
    rp = runtime[0]
    url, _ = rp.begin('/space', select_account=True)
    assert parse_qs(urlsplit(url).query)['prompt'] == ['select_account']
