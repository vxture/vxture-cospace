import hashlib
import hmac
import json
from types import SimpleNamespace
from dataclasses import replace
import pytest
from pydantic import SecretStr,ValidationError
from starlette.datastructures import Headers
from fastapi.testclient import TestClient
from packages.infrastructure.platform_subscription import (
    SubscriptionConfig,Entitlement,PlatformSubscriptions,SubscriptionDenied,
    SubscriptionUnavailable,WebhookRejected,WebhookConflict,EntitlementTransport,
)
from packages.infrastructure.platform_identity import PlatformPrincipal,PlatformTokenVerifier
from packages.service.platform_auth_http import create_auth_app
from packages.service.platform_business_http import BusinessAccess
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_platform_login import runtime,login
from test_platform_business import secured
from test_platform_identity import keys,signed,NOW as TOKEN_NOW,ISSUER
from test_online_consumer import consumer

KEY='test-only-not-a-production-secret-123456'
NOW=1800000000

def config(**changes):
    return SubscriptionConfig(api_base='https://internal.example',webhook_keys=(SecretStr(KEY),),**changes)

def facts(**changes):
    return dict(workspace_id='ws_mock',product='cospace',status='active',tier='pro',bundled=False,
                limits={'points':10,'member.max':1,'scene.max':3},quota_pools=[])|changes

def signed_event(event=None,*,key=KEY,timestamp=NOW,raw=None,**changes):
    value=dict(id='event-one',type='tenant.provisioned',occurred_at=NOW,workspace_id='ws_mock',tenant_id='tenant_mock',application='cospace',data={},seq=1)
    value.update(event or {});value.update(changes)
    raw=raw or json.dumps(value).encode()
    signature=hmac.new(key.encode(),str(timestamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return raw,Headers({'x-vxture-signature':f't={timestamp},v1={signature}','x-vxture-event':value['type'],'x-vxture-delivery':value['id']})

def production_client(rp,accounts):
    accounts.client_id='cospace'
    rp.config=rp.config.model_copy(update={'client_id':'cospace'})
    rp.transport.config=rp.config
    rp.verifier=PlatformTokenVerifier(rp.config.verifier_config,now=rp.now)

@pytest.fixture
def gate(tmp_path):
    rp=SimpleNamespace(config=SimpleNamespace(client_id='cospace',issuer='https://accounts.vxture.com'))
    clock=[0.];calls=[];value=[facts()]
    def fetch(principal,user_token):calls.append((principal.workspace_id,user_token));return value[0]
    obj=PlatformSubscriptions(rp,config(),tmp_path/'policy',fetch=fetch,now=lambda:clock[0],wall=lambda:NOW)
    principal=PlatformPrincipal(rp.config.issuer,'usr_test','org_mock','ws_mock',('workspace:owner',),'test',NOW+300)
    return obj,principal,clock,calls,value

@pytest.mark.parametrize('url,allowed',[
    ('http://public.example',False),('http://100.100.197.42:8080',False),('https://a.example/path',False),
    ('https://user:pass@a.example',False),('https://a.example?q=x',False),('https://a.example#x',False),
    ('https://a.example',True),
])
def test_endpoint_validation(url,allowed):
    if allowed:assert SubscriptionConfig(api_base=url,webhook_keys=(SecretStr(KEY),))
    else:
        with pytest.raises(ValidationError):SubscriptionConfig(api_base=url,webhook_keys=(SecretStr(KEY),))

def test_private_http_requires_explicit_transport_and_strong_key():
    assert SubscriptionConfig(api_base='http://100.100.197.42:8080',webhook_keys=(SecretStr(KEY),),allow_tailnet_http=True)
    with pytest.raises(ValidationError):SubscriptionConfig(api_base='http://39.103.62.17',webhook_keys=(SecretStr(KEY),),allow_tailnet_http=True)
    with pytest.raises(ValidationError):SubscriptionConfig(api_base='https://a.example',webhook_keys=(SecretStr('short'),))
    with pytest.raises(ValidationError):config(cache_seconds=46)

@pytest.mark.parametrize('changes,data,ui',[
    ({},True,True),({'status':'trialing','tier':'free'},True,True),
    ({'status':None,'tier':None},False,False),({'status':None,'tier':None,'bundled':True},True,False),
    ({'status':'future'},False,False),({'tier':'future'},False,False),
    # C2 tier/bundled axes are authoritative; do not locally reinterpret billing status.
    ({'status':'overdue','tier':'starter'},True,True),
    ({'status':'suspended','tier':None},False,False),
])
def test_entitlement_axes(changes,data,ui):
    value=Entitlement.model_validate(facts(**changes))
    assert value.allowed()==data and value.allowed(ui=True)==ui

@pytest.mark.parametrize('changes',[
    {'workspace_id':'other'},{'product':'other'},{'tier':1},{'bundled':'true'},{'limits':{'p':float('nan')}},
    {'quota_pools':None},
])
def test_invalid_or_foreign_facts_fail_closed(gate,changes):
    obj,p,_,_,value=gate;value[0]=facts(**changes)
    with pytest.raises(SubscriptionUnavailable):obj.require(p)

def test_owner_cannot_bypass_and_cache_does_not_cross_workspace(gate):
    obj,p,clock,calls,value=gate
    obj.require(p,'actual-user-token',ui=True);obj.require(p,'same-workspace-other-user',ui=True)
    assert len(calls)==1
    with pytest.raises(SubscriptionUnavailable):obj.require(replace(p,workspace_id='other'))
    clock[0]=31;value[0]=facts(tier=None,status=None)
    with pytest.raises(SubscriptionDenied):obj.require(p,ui=True)
    assert obj.summary(p)['business_allowed'] is False

def test_cache_expiry_network_failure_no_stale_fallback(gate):
    obj,p,clock,*_=gate;obj.require(p);clock[0]=31
    obj.fetch=lambda *_:(_ for _ in ()).throw(OSError('offline'))
    with pytest.raises(SubscriptionUnavailable):obj.require(p)

def test_signed_notification_invalidation_across_instances_and_no_grants(gate):
    obj,p,clock,calls,value=gate;obj.require(p)
    second=PlatformSubscriptions(obj.rp,obj.config,obj.events.path.parent,fetch=obj.fetch,now=lambda:clock[0],wall=lambda:NOW)
    second.require(p);value[0]=facts(status=None,tier=None)
    assert second.webhook(*signed_event())['received']
    with pytest.raises(SubscriptionDenied):obj.require(p)
    assert len(calls)==3
    raw=obj.events.path.read_bytes()
    assert b'actual-user-token' not in raw and b'"tier"' not in raw and KEY.encode() not in raw

def test_invalidation_during_fetch_rejects_race(gate):
    obj,p,*_=gate
    def fetch(*_):obj.webhook(*signed_event());return facts()
    obj.fetch=fetch
    with pytest.raises(SubscriptionUnavailable,match='changed_during_read'):obj.require(p)

def test_replay_conflict_and_out_of_order_lifecycle(gate):
    obj,*_=gate
    payload,headers=signed_event(seq=2)
    assert not obj.webhook(payload,headers)['replayed']
    assert obj.webhook(payload,headers)['replayed']
    assert obj.events.generation('ws_mock')==1
    with pytest.raises(WebhookConflict):obj.webhook(*signed_event(seq=3))
    assert obj.webhook(*signed_event(id='event-old',seq=1))['ignored_stale']
    assert obj.events.generation('ws_mock')==1
    value=dict(id='notify',type='subscription_changed',occurred_at=NOW,workspace_id='ws_mock',tenant_id='tenant_mock',application='cospace',data={})
    raw=json.dumps(value).encode();obj.webhook(*signed_event(value,raw=raw))
    assert obj.events.generation('ws_mock')==2
    second=PlatformSubscriptions(obj.rp,obj.config,obj.events.path.parent,fetch=obj.fetch,wall=lambda:NOW)
    assert second.webhook(payload,headers)['replayed']

@pytest.mark.parametrize('changes',[
    {'application':'other'},{'type':'unknown.event'},{'workspace_id':'../evil'},
    {'tenant_id':''},{'seq':True},{'seq':-1},{'occurred_at':NOW+301},{'data':[]},
])
def test_invalid_signed_payload_rejected(gate,changes):
    obj,*_=gate
    with pytest.raises(WebhookRejected):obj.webhook(*signed_event(**changes))

@pytest.mark.parametrize('delta',[-301,301])
def test_old_or_future_signature_rejected(gate,delta):
    with pytest.raises(WebhookRejected):gate[0].webhook(*signed_event(timestamp=NOW+delta))

def test_signature_tamper_duplicate_headers_json_and_rotation(gate):
    obj,*_=gate;raw,headers=signed_event()
    with pytest.raises(WebhookRejected):obj.webhook(raw+b' ',headers)
    with pytest.raises(WebhookRejected):obj.webhook(raw,Headers(raw=headers.raw+[(b'x-vxture-signature',headers['x-vxture-signature'].encode())]))
    with pytest.raises(WebhookRejected):obj.webhook(*signed_event(raw=b'{"id":"x","id":"x"}'))
    with pytest.raises(WebhookRejected):obj.webhook(b'x'*65537,headers)
    reordered=dict(headers);parts=headers['x-vxture-signature'].split(',');reordered['x-vxture-signature']=','.join(reversed(parts))
    assert obj.webhook(raw,Headers(reordered))['received']
    reordered['x-vxture-signature']+=','+parts[0]
    with pytest.raises(WebhookRejected):obj.webhook(raw,Headers(reordered))
    newkey='another-test-key-for-rotation-1234567890'
    obj.config=config();obj.config=obj.config.model_copy(update={'webhook_keys':(SecretStr(newkey),SecretStr(KEY))})
    assert obj.webhook(*signed_event(id='rotated',key=newkey))['received']
    assert obj.webhook(*signed_event(id='previous'))['received']

def test_identity_pilot_subscription_route_and_signed_callback(runtime,tmp_path):
    rp,_,accounts,clock=runtime;production_client(rp,accounts)
    values=[facts()];obj=PlatformSubscriptions(rp,config(),tmp_path/'policy',fetch=lambda *_:values[0],wall=lambda:NOW)
    with TestClient(create_auth_app(rp,subscriptions=obj),base_url=rp.config.origin,follow_redirects=False) as c:
        assert c.get('/api/subscription').status_code==401
        login(rp,c,accounts)
        r=c.get('/api/subscription');assert r.status_code==200 and r.json()['business_allowed']
        assert r.headers['cache-control']=='no-store' and 'access_token' not in r.text
        assert c.get('/api/subscription?workspace_id=other').status_code==400
        assert c.get('/api/spaces').status_code==503
        raw,headers=signed_event();h=dict(headers)|{'content-type':'application/json'}
        assert c.post('/api/webhooks/vxture',content=raw,headers=h).status_code==200
        assert c.post('/api/webhooks/vxture',content=raw).status_code==415
        assert c.post('/api/webhooks/vxture',content=raw,headers={'content-type':'application/json'}).status_code==400
        assert c.post('/api/webhooks/vxture',content=b'x'*65537,headers=h).status_code==413

def test_business_gate_precedes_records_preserves_session_and_scene_policy(secured,tmp_path):
    rp,_,accounts,clock,jobs,directory,spaces,policies,*_=secured
    production_client(rp,accounts);value=[facts(status=None,tier=None)]
    obj=PlatformSubscriptions(rp,config(),tmp_path/'policy',fetch=lambda *_:value[0],now=lambda:clock[0],wall=lambda:NOW)
    access=BusinessAccess(rp,policies,directory,jobs,subscriptions=obj)
    app=create_auth_app(rp,business=create_app(None,jobs,space_directory=directory,platform_origin=rp.config.origin),access=access,subscriptions=obj)
    with TestClient(app,base_url=rp.config.origin,follow_redirects=False) as c:
        assert c.get('/api/spaces').status_code==401
        login(rp,c,accounts)
        r=c.get('/api/spaces');assert r.status_code==403 and r.json()['detail']=='subscription_required'
        assert c.get('/api/auth/session').json()['authenticated']
        assert c.post('/api/build-jobs',json={}).json()['detail']=='csrf_rejected'
        value[0]=facts();obj.webhook(*signed_event())
        assert len(c.get('/api/spaces').json()['spaces'])==1
        assert c.get('/api/spaces/'+spaces[1]['id']).status_code==403
        obj.fetch=lambda *_:(_ for _ in ()).throw(OSError());clock[0]+=31
        assert c.get('/api/spaces').status_code==503
        assert c.get('/api/auth/session').json()['authenticated']

def test_https_business_cannot_omit_gate(runtime):
    rp,*_=runtime;rp.config=rp.config.model_copy(update={'issuer':'https://accounts.vxture.com'})
    with pytest.raises(ValueError,match='subscription_gate_required'):
        create_auth_app(rp,business=object(),access=SimpleNamespace(subscriptions=None))

def test_backup_restores_only_receipts_and_generation(tmp_path):
    from test_workbench_backup import runtime as fixture,save
    from packages.infrastructure.preview_backup import restore,tree
    from packages.infrastructure.platform_subscription import SubscriptionEvents
    env=fixture.__wrapped__(tmp_path);root,output=env
    ledger=SubscriptionEvents(root/'policy');raw,_=signed_event();ledger.accept(json.loads(raw),raw)
    before=tree(root);result=save(env);root.rename(tmp_path/'previous')
    restore(output,root,result['sha256'])
    assert tree(root)==before and SubscriptionEvents(root/'policy').generation('ws_mock')==1

@pytest.mark.parametrize('user',[True,False])
@pytest.mark.parametrize('changes',[
    {},{'aud':'other'},{'act':{'sub':'other'}},{'scope':'tool:vxture extra'},
    {'workspace_id':'foreign'},{'org_id':'foreign'},{'delegated':False},
    {'exp':TOKEN_NOW+301},{'mode':'operator'},
])
def test_token_exchange_context_signature_and_no_cookie_proxy_transport(keys,monkeypatch,user,changes):
    from packages.infrastructure.platform_identity import PlatformVerifierConfig
    import packages.infrastructure.platform_subscription as module
    claims=dict(iss=ISSUER,aud='vxture',act={'sub':'cospace'},scope='tool:vxture',
                mode='obo' if user else 'service',org_id='org_mock',workspace_id='ws_mock',iat=TOKEN_NOW,exp=TOKEN_NOW+300)
    if user:claims['sub']='usr_test'
    claims.update(changes);calls=[];requests=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,*_):return json.dumps(facts()).encode()
    class Opener:
        def open(self,request,timeout):requests.append(request);return Response()
    def post(path,body,**kwargs):calls.append((path,body,kwargs));return {'token_type':'Bearer','access_token':signed(keys[0],claims)}
    cfg=PlatformVerifierConfig(issuer=ISSUER,audience='cospace',jwks_url=ISSUER+'/oidc/jwks')
    rp=SimpleNamespace(config=SimpleNamespace(verifier_config=cfg),transport=SimpleNamespace(post=post))
    transport=EntitlementTransport(rp,config())
    transport.verifier=PlatformTokenVerifier(cfg.model_copy(update={'audience':'vxture'}),fetch=lambda _:{'keys':[keys[0].as_dict(private=False)]},now=lambda:TOKEN_NOW)
    monkeypatch.setattr(module.time,'time',lambda:TOKEN_NOW)
    monkeypatch.setattr(module,'build_opener',lambda *args:Opener())
    p=PlatformPrincipal(ISSUER,'usr_test','org_mock','ws_mock',(),'test',TOKEN_NOW+300)
    if changes:
        with pytest.raises(SubscriptionUnavailable):transport.fetch(p,'user-token' if user else None)
        assert not requests
    else:
        assert transport.fetch(p,'user-token' if user else None)['product']=='cospace'
        request=requests[0]
        assert request.full_url=='https://internal.example/platform/entitlements?workspace_id=ws_mock&product=cospace'
        assert request.get_header('Authorization').startswith('Bearer ') and request.get_header('Cookie') is None
        body=calls[0][1];assert body['audience']=='vxture' and calls[0][2]=={'form':True}
        if user:assert body['subject_token']=='user-token' and 'workspace_id' not in body
        else:assert body['workspace_id']=='ws_mock' and 'subject_token' not in body

def test_s2s_subscription_before_geometry_and_on_revoke(consumer,tmp_path,monkeypatch):
    client,route,body,headers,_,_,access,jobs,spaces,old,new,c,accounts,clock=consumer
    production_client(access.rp,accounts)
    value=[facts(tier=None,status=None)];obj=PlatformSubscriptions(access.rp,config(),tmp_path/'policy',fetch=lambda *_:value[0],wall=lambda:NOW)
    access.consumer.subscriptions=obj
    assert client.post(route,json=body,headers=headers).json()['detail']=='subscription_required'
    value[0]=facts(tier=None,status=None,bundled=True);obj.webhook(*signed_event())
    assert client.post(route,json=body,headers=headers).status_code==200
    from packages.service.preview_publications import PreviewPublications
    original=PreviewPublications.read
    def read(self,identity):
        record,model=original(self,identity);query=model.query
        def revoke(point):
            result=query(point);value[0]=facts(tier=None,status=None)
            obj.webhook(*signed_event(id='revoke',type='tenant.deprovisioned',seq=2))
            return result
        model.query=revoke;return record,model
    monkeypatch.setattr(PreviewPublications,'read',read)
    result=client.post(route,json=body,headers=headers)
    assert result.status_code==403 and result.json()=={'detail':'subscription_required'}


@pytest.mark.parametrize('status',[None,'active','expired'])
def test_pricing_deeplink_has_only_product_and_uses_configured_website(gate,status):
    obj,p,_,_,values=gate
    obj.config=obj.config.model_copy(update={'website_base':'https://website.example'})
    values[0]=facts(status=status,tier=None if status!='active' else 'pro')
    summary=obj.summary(p)
    assert summary['pricing_url']=='https://website.example/pricing?product=cospace'
    assert 'console_url' not in summary


@pytest.mark.parametrize('url',['http://public.example','https://a.example/','https://a.example/path',
    'https://user:password@a.example','https://a.example?q=x','https://a.example#x','https://a .example'])
def test_website_origin_configuration_rejects_unsafe_or_ambiguous_values(url):
    with pytest.raises(ValidationError):config(website_base=url)


def test_only_platform_signature_header_is_required_and_optional_headers_are_not_authority(gate):
    obj,p,_,calls,values=gate
    obj.require(p)
    raw,headers=signed_event(type='subscription_changed')
    payload=json.loads(raw);payload.pop('seq')
    raw,headers=signed_event(payload,raw=json.dumps(payload).encode())
    # Unsigned optional headers cannot override the signed envelope.
    headers=Headers({'x-vxture-signature':headers['x-vxture-signature'],
        'x-vxture-event':'misleading','x-vxture-delivery':'untrusted'})
    assert obj.webhook(raw,headers)['received']
    values[0]=facts(limits={'member.max':5})
    assert obj.require(p).limits['member.max']==5
    assert len(calls)==2


def test_grant_invalidation_uses_signed_data_and_does_not_touch_lifecycle_sequence(gate):
    obj,p,*_=gate
    obj.webhook(*signed_event(seq=5))
    event=dict(id='grant-change',type='grant.invalidated',occurred_at=NOW,
        workspace_id=p.workspace_id,tenant_id=p.org_id,application='cospace',data={'grant_id':'grant-one','future':True})
    raw,headers=signed_event(event,raw=json.dumps(event).encode())
    only_signature=Headers({'x-vxture-signature':headers['x-vxture-signature']})
    assert obj.webhook(raw,only_signature)['received']
    assert obj.webhook(raw,only_signature)['replayed']
    with obj.events.connect() as db:
        assert db.execute('SELECT seq FROM generations').fetchone()[0]==5
