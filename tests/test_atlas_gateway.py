import json
import io
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from pydantic import ValidationError
from packages.infrastructure.atlas_gateway import AtlasConfig, AtlasGateway, AtlasUnavailable
from packages.infrastructure.platform_identity import PlatformPrincipal, PlatformVerifierConfig, PlatformTokenVerifier
from test_platform_identity import keys, signed, NOW, ISSUER


@pytest.mark.parametrize('url,options,allowed', [
    ('https://atlas.example', {}, True),
    ('http://100.100.1.2:8888', {'allow_tailnet_http':True}, True),
    ('http://127.0.0.1:8782', {'allow_loopback_http':True}, True),
    ('http://public.example', {'allow_tailnet_http':True}, False),
    ('https://atlas.example/path', {}, False),
    ('https://user:secret@atlas.example', {}, False),
    ('https://atlas.example?model=x', {}, False),
])
def test_only_explicit_server_config_can_choose_atlas_origin(url, options, allowed):
    if allowed:assert AtlasConfig(base_url=url, coordinate_endpoint='chat/coordinate', **options)
    else:
        with pytest.raises(ValidationError):AtlasConfig(base_url=url, coordinate_endpoint='chat/coordinate', **options)


def gateway(keys, changes=None):
    value = dict(iss=ISSUER, aud='atlas', sub='usr_alice', act={'sub':'cospace'}, mode='obo',
        scope='tool:atlas', org_id='org_1', workspace_id='ws_1', iat=NOW-10, exp=NOW+200) | (changes or {})
    calls=[]
    def exchange(path, body, **options):
        calls.append((path,body,options))
        return {'token_type':'Bearer', 'access_token':signed(keys[0],value)}
    config=PlatformVerifierConfig(issuer=ISSUER,audience='cospace',jwks_url=ISSUER+'/oidc/jwks')
    rp=SimpleNamespace(now=lambda:NOW, config=SimpleNamespace(verifier_config=config),transport=SimpleNamespace(post=exchange))
    obj=AtlasGateway(rp,AtlasConfig(base_url='https://atlas.example',coordinate_endpoint='chat/coordinate'))
    obj.verifier=PlatformTokenVerifier(config.model_copy(update={'audience':'atlas'}),
        fetch=lambda _:{'keys':[key.as_dict(private=False) for key in keys]},now=rp.now)
    principal=PlatformPrincipal(ISSUER,'usr_alice','org_1','ws_1',(),'Alice',NOW+300)
    return obj,principal,calls


def test_atlas_uses_verified_user_bound_ticket_not_product_access_token(keys):
    obj,principal,calls=gateway(keys)
    ticket=obj.token(principal,'user-access')
    assert ticket!='user-access'
    assert calls==[('/oidc/token',{'grant_type':'urn:ietf:params:oauth:grant-type:token-exchange',
        'audience':'atlas','requested_token_type':'urn:ietf:params:oauth:token-type:access_token',
        'subject_token':'user-access','subject_token_type':'urn:ietf:params:oauth:token-type:access_token'},{'form':True})]


@pytest.mark.parametrize('changes', [
    {'aud':'vxture'}, {'act':{'sub':'arda'}}, {'scope':'tool:vxture'}, {'mode':'service'},
    {'sub':'usr_other'}, {'org_id':'other'}, {'workspace_id':'other'}, {'delegated':True},
    {'exp':NOW}, {'iat':NOW-301}, {'iat':NOW+31}, {'exp':NOW+400},
])
def test_cross_product_workspace_subject_scope_and_expired_tickets_rejected(keys, changes):
    obj,principal,_=gateway(keys,changes)
    with pytest.raises(AtlasUnavailable,match='coordinate_ai_identity_unavailable'):
        obj.token(principal,'user-access')


def test_http_wire_matches_atlas_and_never_sends_credentials_or_uses_redirects(keys,monkeypatch):
    obj,principal,_=gateway(keys);requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,budget):return json.dumps({'message':{'role':'assistant','content':'{}'},'finishReason':'stop','thinking':'off'} if budget==65_537 else routes()).encode()
    def opener(*handlers):
        assert any(type(handler).__name__=='NoRedirect' for handler in handlers)
        def send(request,timeout):requests.append((request,timeout));return Response()
        return SimpleNamespace(open=send)
    monkeypatch.setattr('packages.infrastructure.atlas_gateway.build_opener',opener)
    assert obj.chat(principal,'user-access','task-one',[{'role':'user','content':'source'}])=='{}'
    assert requests[0][0].full_url=='https://atlas.example/v1/model-routes'
    request,timeout=requests[1];body=json.loads(request.data)
    assert request.full_url=='https://atlas.example/v1/chat' and timeout==50
    assert body['endpointCode']=='chat/coordinate' and body['taskId']=='task-one'
    assert body['tenantId']=='org_1' and 'workspaceId' not in body and body['stream'] is False
    assert body['thinking']=='off'
    assert body['timeoutMs']==45000 and 'user-access' not in request.data.decode()
    assert request.get_header('Authorization').startswith('Bearer ') and request.get_header('Authorization')!='Bearer user-access'


def test_unconfigured_busy_and_upstream_failure_do_not_retry_or_leak_source(keys,monkeypatch):
    obj,principal,calls=gateway(keys)
    obj.config=None
    with pytest.raises(AtlasUnavailable,match='unconfigured'):obj.chat(principal,'token','t',[])
    assert not calls
    obj.config=AtlasConfig(base_url='https://atlas.example',coordinate_endpoint='coordinate')
    obj.slots.acquire();obj.slots.acquire()
    with pytest.raises(AtlasUnavailable,match='busy'):obj.chat(principal,'token','t',[])
    assert not calls
    obj.slots.release();obj.slots.release()
    def failed(*args):
        def send(*a,**k):raise HTTPError('https://atlas.example',403,'private provider body',{},None)
        return SimpleNamespace(open=send)
    monkeypatch.setattr('packages.infrastructure.atlas_gateway.build_opener',failed)
    monkeypatch.setattr(obj,'check_route',lambda *a:None)
    with pytest.raises(AtlasUnavailable,match='^coordinate_ai_access_denied$'):obj.chat(principal,'token','t',[])
    assert len(calls)==1


@pytest.mark.parametrize('payload,expected', [
    ({'code':'UPSTREAM_ACCOUNT_REFUSED','message':'private vendor account and source'}, 'coordinate_ai_provider_account_unavailable'),
    ({'code':'UPSTREAM_ERROR','message':'private source'}, 'coordinate_ai_unavailable'),
    ({'message':'UPSTREAM_ACCOUNT_REFUSED is only quoted vendor text'}, 'coordinate_ai_unavailable'),
    (['UPSTREAM_ACCOUNT_REFUSED'], 'coordinate_ai_unavailable'),
    ('invalid response', 'coordinate_ai_unavailable'),
    ({'code':'UPSTREAM_ACCOUNT_REFUSED','message':'x'*9000}, 'coordinate_ai_unavailable'),
])
def test_vendor_account_refusal_has_a_safe_actionable_code_without_retry(keys,monkeypatch,payload,expected):
    obj,principal,calls=gateway(keys)
    monkeypatch.setattr(obj,'check_route',lambda *a:None)
    attempts=[]
    def opener(*handlers):
        def send(request,timeout):
            attempts.append(request)
            raise HTTPError(request.full_url,502,'private upstream message',{},io.BytesIO(json.dumps(payload).encode()))
        return SimpleNamespace(open=send)
    monkeypatch.setattr('packages.infrastructure.atlas_gateway.build_opener',opener)
    with pytest.raises(AtlasUnavailable,match='^'+expected+'$'):
        obj.chat(principal,'user-access','task-one',[{'role':'user','content':'private source'}])
    assert len(attempts)==len(calls)==1


def routes():
    return {'endpoints':[{'endpointCode':'chat/coordinate','state':'active','category':'chat',
        'contextWindow':32768,'maxOutputTokens':4096,'thinkingModes':['off','on']}], 'maxRequestBytes':16777216}


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(endpoints=[]),
    lambda r:r['endpoints'][0].update(state='inactive'),
    lambda r:r['endpoints'][0].update(thinkingModes=['on']),
    lambda r:r['endpoints'][0].update(contextWindow=None),
    lambda r:r['endpoints'][0].update(contextWindow=20),
    lambda r:r['endpoints'][0].update(maxOutputTokens=10),
    lambda r:r.update(maxRequestBytes=1),
])
def test_missing_grant_incompatible_thinking_and_insufficient_capacity_prevent_inference(keys,monkeypatch,mutation):
    obj,principal,_=gateway(keys);value=routes();mutation(value);calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,budget):return json.dumps(value).encode()
    def opener(*handlers):
        def send(request,timeout):calls.append(request);return Response()
        return SimpleNamespace(open=send)
    monkeypatch.setattr('packages.infrastructure.atlas_gateway.build_opener',opener)
    with pytest.raises(AtlasUnavailable,match='route_unavailable'):
        obj.chat(principal,'user-access','task-one',[{'role':'user','content':'source'}])
    assert len(calls)==1 and calls[0].get_method()=='GET'
