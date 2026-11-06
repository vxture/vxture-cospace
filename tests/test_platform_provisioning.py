import json
import sqlite3
import threading
from types import SimpleNamespace
from urllib.error import HTTPError

from fastapi.testclient import TestClient
import pytest

from packages.infrastructure.platform_provisioning import ProvisioningTransport, ProvisioningReconciler
from packages.infrastructure.platform_subscription import SubscriptionUnavailable
from packages.infrastructure.platform_identity import PlatformTokenVerifier, PlatformVerifierConfig
from packages.service.platform_auth_http import create_auth_app
from test_platform_subscription import gate, config, facts, signed_event, production_client
from test_platform_identity import keys, signed, NOW, ISSUER
from test_platform_login import runtime


def item(**changes):
    return dict(workspace_id='ws_mock',tenant_id='tenant_mock',state='provisioned',seq=1,
                updated_at='2026-11-06T01:02:03.123456Z')|changes


def refs(obj):
    with obj.events.connect() as db:
        return db.execute('SELECT workspace,tenant,state,seq FROM provisioning_refs ORDER BY workspace').fetchall()


def test_full_scan_pagination_replay_restart_and_absence_are_not_deletion(gate):
    obj,p,*_=gate;calls=[]
    def page(cursor):
        calls.append(cursor)
        if cursor is None:return {'items':[item()],'nextCursor':'opaque-page-two'}
        assert cursor=='opaque-page-two'
        return {'items':[item(workspace_id='ws_other')],'nextCursor':None}
    worker=ProvisioningReconciler(obj,page=page)
    assert worker.run_once()=={'pages':2,'scanned':2,'applied':2}
    assert worker.run_once()['applied']==0
    assert calls==[None,'opaque-page-two',None,'opaque-page-two']
    restarted=ProvisioningReconciler(obj,page=lambda _:dict(items=[],nextCursor=None))
    assert restarted.run_once()['applied']==0
    assert len(refs(obj))==2
    assert obj.require(p).allowed()  # Lifecycle references are not another entitlement gate.


def test_lost_webhook_reconciliation_invalidates_c2_but_never_grants_scene_access(gate):
    obj,p,clock,calls,values=gate
    obj.require(p)
    values[0]=facts(status=None,tier=None)
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[item(state='deprovisioned',seq=2)],nextCursor=None))
    assert worker.run_once()['applied']==1
    assert obj.summary(p)['business_allowed'] is False
    assert len(calls)==2
    # Reconciliation persists IDs/state/seq only, without entitlement values or scene grants.
    with obj.events.connect() as db:
        assert db.execute('PRAGMA table_info(provisioning_refs)').fetchall()[0][1]=='workspace'
        assert not db.execute("SELECT name FROM sqlite_master WHERE name IN ('seats','policy')").fetchall()


def test_webhook_and_poll_share_monotonic_sequence_pending_is_not_a_command(gate):
    obj,*_=gate
    obj.webhook(*signed_event(type='tenant.deprovisioned',seq=3))
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[item(seq=2)],nextCursor=None))
    assert worker.run_once()['applied']==0
    assert refs(obj)==[('ws_mock','tenant_mock','deprovisioned',3)]
    worker.page=lambda _:dict(items=[item(state='pending',seq=4)],nextCursor=None)
    assert worker.run_once()['applied']==0
    obj.webhook(*signed_event(id='provision-again',seq=4))
    assert refs(obj)==[('ws_mock','tenant_mock','provisioned',4)]
    assert worker.run_once()['applied']==0


def test_equal_sequence_conflict_does_not_override_retained_fact(gate):
    obj,*_=gate
    obj.webhook(*signed_event(seq=3))
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[item(state='deprovisioned',seq=3)],nextCursor=None))
    with pytest.raises(SubscriptionUnavailable,match='sequence_conflict'):worker.run_once()
    assert refs(obj)==[('ws_mock','tenant_mock','provisioned',3)]


def test_migration_repairs_reference_for_same_already_seen_sequence(gate):
    obj,*_=gate
    with obj.events.connect() as db:
        db.execute('INSERT INTO generations VALUES(?,?,?)',('ws_mock',5,3));db.commit()
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[item(seq=3)],nextCursor=None))
    assert worker.run_once()['applied']==1
    assert worker.run_once()['applied']==0
    assert refs(obj)==[('ws_mock','tenant_mock','provisioned',3)]


@pytest.mark.parametrize('page',[
    {},{'items':None,'nextCursor':None},{'items':[]}, {'items':[],'nextCursor':''},
    {'items':[],'nextCursor':'bad cursor'}, {'items':[item(seq=True)],'nextCursor':None},
    {'items':[item(seq=-1)],'nextCursor':None}, {'items':[item(state='future')],'nextCursor':None},
    {'items':[item(workspace_id='../bad')],'nextCursor':None},
    {'items':[item(updated_at='2026-11-06T01:02:03')],'nextCursor':None},
])
def test_invalid_page_never_becomes_successful_empty_scan(gate,page):
    obj,*_=gate
    worker=ProvisioningReconciler(obj,page=lambda _:page)
    with pytest.raises(SubscriptionUnavailable):worker.run_once()
    assert refs(obj)==[]


def test_cursor_loop_is_rejected_and_network_failure_can_retry_from_beginning(gate):
    obj,*_=gate
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[],nextCursor='same'))
    with pytest.raises(SubscriptionUnavailable,match='cursor_loop'):worker.run_once()
    def fail(_):raise SubscriptionUnavailable('offline')
    worker.page=fail
    with pytest.raises(SubscriptionUnavailable):worker.run_once()
    worker.page=lambda cursor:dict(items=[item()],nextCursor=None) if cursor is None else None
    assert worker.run_once()['applied']==1


def test_pending_version_zero_does_not_break_scan_or_imply_activation(gate):
    obj,*_=gate
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[item(state='pending',seq=0),
        item(workspace_id='ws_ready')],nextCursor=None))
    assert worker.run_once()=={'pages':1,'scanned':2,'applied':1}
    assert refs(obj)==[('ws_ready','tenant_mock','provisioned',1)]
    assert obj.webhook(*signed_event(seq=0))['received']
    assert ('ws_mock','tenant_mock','provisioned',0) in refs(obj)


@pytest.mark.parametrize('changes',[
    {},{'act':{'sub':'other'}},{'scope':'tool:vxture'},{'workspace_id':'ws_mock'},
    {'sub':'usr_test'},{'mode':'obo'},{'delegated':True},{'exp':NOW+301},
])
def test_dedicated_reader_ticket_has_no_workspace_or_user_and_only_reads_own_list(keys,monkeypatch,changes):
    import packages.infrastructure.platform_provisioning as module
    cfg=PlatformVerifierConfig(issuer=ISSUER,audience='cospace',jwks_url=ISSUER+'/oidc/jwks')
    claims=dict(iss=ISSUER,aud='vxture',act={'sub':'cospace'},scope='provisioning:read',mode='service',iat=NOW,exp=NOW+300)|changes
    calls=[];requests=[]
    def post(path,body,**kwargs):
        calls.append((path,body,kwargs))
        return {'token_type':'Bearer','access_token':signed(keys[0],claims)}
    rp=SimpleNamespace(config=SimpleNamespace(verifier_config=cfg),transport=SimpleNamespace(post=post))
    transport=ProvisioningTransport(rp,config())
    transport.verifier=PlatformTokenVerifier(cfg.model_copy(update={'audience':'vxture'}),
        fetch=lambda _:{'keys':[keys[0].as_dict(private=False)]},now=lambda:NOW)
    monkeypatch.setattr(module.time,'time',lambda:NOW)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,*_):return b'{"items":[],"nextCursor":null}'
    class Opener:
        def open(self,request,timeout):requests.append(request);return Response()
    monkeypatch.setattr(module,'build_opener',lambda *args:Opener())
    if changes:
        with pytest.raises(SubscriptionUnavailable):transport.page()
        assert requests==[]
    else:
        assert transport.page()['items']==[]
        transport.page('opaque-token')
        assert calls==[('/oidc/token',{'grant_type':'urn:ietf:params:oauth:grant-type:token-exchange',
            'audience':'vxture','scope':'provisioning:read'},{'form':True})]
        assert requests[0].full_url=='https://internal.example/platform/provisioning?limit=200'
        assert requests[1].full_url.endswith('limit=200&cursor=opaque-token')
        assert requests[0].get_header('Cookie') is None


def test_401_refreshes_reader_ticket_once_without_user_context(monkeypatch):
    import packages.infrastructure.platform_provisioning as module
    rp=SimpleNamespace(config=SimpleNamespace(verifier_config=PlatformVerifierConfig(
        issuer=ISSUER,audience='cospace',jwks_url=ISSUER+'/oidc/jwks')))
    transport=ProvisioningTransport(rp,config());tokens=[];requests=[]
    def token():tokens.append(1);return 'test-ticket'
    monkeypatch.setattr(transport,'token',token)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,*_):return b'{"items":[],"nextCursor":null}'
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            if len(requests)==1:raise HTTPError(request.full_url,401,'unauthorized',None,None)
            return Response()
    monkeypatch.setattr(module,'build_opener',lambda *args:Opener())
    assert transport.page()['nextCursor'] is None
    assert len(tokens)==len(requests)==2


def test_production_lifespan_starts_scan_and_shuts_down_without_affecting_login(runtime,tmp_path):
    from packages.infrastructure.platform_subscription import PlatformSubscriptions
    rp,_,accounts,_=runtime;production_client(rp,accounts)
    obj=PlatformSubscriptions(rp,config(),tmp_path/'policy',fetch=lambda *_:facts())
    worker=ProvisioningReconciler(obj,page=lambda _:dict(items=[item()],nextCursor=None))
    completed=threading.Event();original=worker.run_once
    def observed():
        try:return original()
        finally:completed.set()
    worker.run_once=observed
    with TestClient(create_auth_app(rp,subscriptions=obj,reconciler=worker),base_url=rp.config.origin) as client:
        assert completed.wait(5)
        assert refs(obj)==[('ws_mock','tenant_mock','provisioned',1)]
        assert client.get('/api/auth/config').status_code==200
    assert worker.stop.is_set()


def test_periodic_retry_recovers_from_failure_without_revoking_access(runtime,tmp_path):
    from packages.infrastructure.platform_subscription import PlatformSubscriptions
    rp,_,accounts,_=runtime;production_client(rp,accounts)
    obj=PlatformSubscriptions(rp,config(),tmp_path/'policy',fetch=lambda *_:facts())
    attempts=[];recovered=threading.Event()
    def page(cursor):
        attempts.append(cursor)
        if len(attempts)==1:raise SubscriptionUnavailable('simulated outage')
        return dict(items=[item()],nextCursor=None)
    worker=ProvisioningReconciler(obj,page=page)
    worker.interval=0.01  # Test clock acceleration; production interval remains 300 s.
    original=worker.run_once
    def observed():
        value=original();recovered.set();return value
    worker.run_once=observed
    with TestClient(create_auth_app(rp,subscriptions=obj,reconciler=worker),base_url=rp.config.origin) as client:
        assert recovered.wait(5)
        assert attempts[:2]==[None,None]
        assert client.get('/api/auth/config').status_code==200
        assert refs(obj)==[('ws_mock','tenant_mock','provisioned',1)]


def test_backup_preserves_reconciled_sequence_refs_for_restart(tmp_path):
    from test_workbench_backup import runtime as fixture, save
    from packages.infrastructure.preview_backup import restore
    from packages.infrastructure.platform_subscription import SubscriptionEvents
    env=fixture.__wrapped__(tmp_path);root,archive=env
    events=SubscriptionEvents(root/'policy')
    assert events.reconcile(item(seq=7))
    receipt=save(env);root.rename(tmp_path/'saved-original')
    restore(archive,root,receipt['sha256'])
    reopened=SubscriptionEvents(root/'policy')
    assert not reopened.reconcile(item(seq=6))
    assert not reopened.reconcile(item(seq=7))
    assert reopened.reconcile(item(seq=8,state='deprovisioned'))
