"""User application authority is platform-owned, live and separate from scene ACL."""
from dataclasses import replace
import pytest
from packages.infrastructure.platform_subscription import ApplicationAccessDenied, SubscriptionUnavailable
from test_platform_subscription import gate, authorized_access


def test_strict_mode_assignment_is_not_shared_and_revocation_is_immediate(gate):
    obj, owner, _, calls, _ = gate
    obj.config=obj.config.model_copy(update={'access_cache_seconds':0})
    member = replace(owner, subject='usr_member', governance_roles=())
    grants = {owner.subject}
    access_calls = []
    def access(principal, token):
        access_calls.append((principal.subject, token))
        return authorized_access(principal, token) | {'allowed': principal.subject in grants}
    obj.fetch_access = access
    obj.require(owner, 'owner-token', ui=True)
    with pytest.raises(ApplicationAccessDenied): obj.require(member, 'member-token', ui=True)
    assert obj.summary(member, 'member-token')['access_reason'] == 'application_access_required'
    grants.add(member.subject)
    obj.require(member, 'member-token', ui=True)
    grants.remove(member.subject)
    with pytest.raises(ApplicationAccessDenied): obj.require(member, 'member-token', ui=True)
    assert len(calls) == 1 and len(access_calls) == 5


@pytest.mark.parametrize('change', [
    {'subject': 'someone-else'}, {'workspace_id': 'another'}, {'org_id': 'another'},
    {'product': 'another'}, {'allowed': 'true'}, {},
])
def test_invalid_platform_decision_never_grants(gate, change):
    obj, principal, *_ = gate
    obj.fetch_access = lambda *_: authorized_access(principal, 'token') | change if change else {}
    with pytest.raises(SubscriptionUnavailable): obj.require(principal, 'token', ui=True)


def test_owner_has_no_implicit_seat_bypass(gate):
    obj, principal, *_ = gate
    obj.fetch_access = lambda *_: authorized_access(principal, 'token') | {'allowed': False}
    with pytest.raises(ApplicationAccessDenied): obj.require(principal, 'token', ui=True)


def test_service_calls_keep_workspace_entitlements_without_impersonating_user(gate):
    obj, principal, *_ = gate
    obj.fetch_access = lambda *_: (_ for _ in ()).throw(AssertionError('user access requested'))
    obj.require(principal)


def test_access_network_failure_has_no_stale_grant(gate):
    obj, principal, clock, *_ = gate
    obj.require(principal, 'token')
    clock[0]+=31
    obj.fetch_access = lambda *_: (_ for _ in ()).throw(OSError('offline'))
    with pytest.raises(SubscriptionUnavailable): obj.require(principal, 'token')


@pytest.mark.parametrize('payload', [b'{"allowed": true, "allowed": false}', b'x'*16385])
def test_access_transport_rejects_ambiguous_or_oversized_response(gate, monkeypatch, payload):
    from packages.infrastructure import platform_subscription as module
    from packages.infrastructure.platform_subscription import EntitlementTransport
    obj, principal, *_ = gate
    requests = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, limit): return payload[:limit]
    class Opener:
        def open(self, request, timeout): requests.append(request); return Response()
    transport = object.__new__(EntitlementTransport)
    transport.config = obj.config
    transport.token = lambda p, token: 'test-obo-token'
    monkeypatch.setattr(module, 'build_opener', lambda *_: Opener())
    with pytest.raises(SubscriptionUnavailable): transport.access(principal, 'test-user-token')
    assert requests[0].full_url == 'https://internal.example/platform/product-access'
    assert requests[0].get_header('Authorization') == 'Bearer test-obo-token'


def test_access_transport_requires_a_user_token(gate):
    from packages.infrastructure.platform_subscription import EntitlementTransport
    transport = object.__new__(EntitlementTransport)
    with pytest.raises(SubscriptionUnavailable): transport.access(gate[1], None)

def test_member_decision_cache_is_bounded_and_token_subject_scoped(gate):
    obj,owner,clock,*_=gate
    calls=[]
    obj.fetch_access=lambda p,t:(calls.append((p.subject,t)) or authorized_access(p,t))
    for _ in range(8):obj.require(owner,'owner-token')
    assert calls==[(owner.subject,'owner-token')]
    obj.require(replace(owner,subject='another'),'owner-token')
    obj.require(owner,'rotated-token')
    assert len(calls)==3
    clock[0]=30
    obj.require(owner,'owner-token')
    assert len(calls)==4


def test_signed_event_revokes_cached_member_decisions_across_instances(gate):
    from test_platform_subscription import signed_event,PlatformSubscriptions,NOW
    obj,principal,clock,*_=gate
    allowed=[True]
    def access(p,t):return authorized_access(p,t)|{'allowed':allowed[0]}
    obj.fetch_access=access
    other=PlatformSubscriptions(obj.rp,obj.config,obj.events.path.parent,fetch=obj.fetch,fetch_access=access,now=lambda:clock[0],wall=lambda:NOW)
    obj.require(principal,'token');other.require(principal,'token')
    allowed[0]=False
    import json
    event={'type':'grant.invalidated'}
    raw,headers=signed_event(**event);value=json.loads(raw);value.pop('seq')
    raw,headers=signed_event(raw=json.dumps(value).encode(),**event)
    obj.webhook(raw,headers)
    # Generic events omit seq rather than sending null.
    for gate_instance in (obj,other):
        with pytest.raises(ApplicationAccessDenied):gate_instance.require(principal,'token')


def test_event_during_member_lookup_cannot_publish_allow(gate):
    from test_platform_subscription import signed_event
    obj,principal,*_=gate
    def access(p,t):
        event=dict(type='subscription_changed');raw,headers=signed_event(**event)
        import json
        # Re-sign a generic event without tenant-only sequence.
        value=json.loads(raw);value.pop('seq')
        raw,headers=signed_event(raw=json.dumps(value).encode(),**event)
        obj.webhook(raw,headers)
        return authorized_access(p,t)
    obj.fetch_access=access
    with pytest.raises(SubscriptionUnavailable):obj.require(principal,'token')
    assert not obj.access_cache


def test_different_workspaces_do_not_wait_for_one_network_lock(gate):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from test_platform_subscription import facts
    obj,principal,*_=gate
    entered,release=Event(),Event()
    def fetch(p,t):
        if p.workspace_id==principal.workspace_id:
            entered.set();assert release.wait(5)
        return facts(workspace_id=p.workspace_id)
    obj.fetch=fetch
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(obj.view,principal)
        assert entered.wait(2)
        try:
            second=pool.submit(obj.view,replace(principal,workspace_id='other'))
            assert second.result(timeout=2).workspace_id=='other'
        finally:release.set()
        assert first.result().workspace_id==principal.workspace_id


def test_simultaneous_member_lookups_share_one_inflight_request(gate):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    obj,principal,*_=gate
    entered,release=Event(),Event();calls=[]
    def access(p,t):
        calls.append(t);entered.set();assert release.wait(5)
        return authorized_access(p,t)
    obj.fetch_access=access
    with ThreadPoolExecutor(max_workers=8) as pool:
        pending=[pool.submit(obj.assigned,principal,'token') for _ in range(8)]
        assert entered.wait(2);release.set()
        assert all(f.result() for f in pending)
    assert calls==['token']

def test_manual_recheck_bypasses_a_cached_denial(gate):
    obj,principal,*_=gate
    allowed=[False]
    obj.fetch_access=lambda p,t:authorized_access(p,t)|{'allowed':allowed[0]}
    assert obj.summary(principal,'token')['business_allowed'] is False
    allowed[0]=True
    assert obj.summary(principal,'token')['business_allowed'] is False
    assert obj.summary(principal,'token',refresh=True)['business_allowed'] is True


def test_default_transport_and_public_key_verifier_survive_multiple_calls(gate,monkeypatch,tmp_path):
    from packages.infrastructure import platform_subscription as module
    obj,principal,*_=gate
    instances=[]
    class Transport:
        def __init__(self,*_):instances.append(self)
        def fetch(self,p,t):return {'workspace_id':p.workspace_id,'product':'cospace','status':'active','tier':'pro','bundled':False,'limits':{},'quota_pools':[]}
        def access(self,p,t):return authorized_access(p,t)
    monkeypatch.setattr(module,'EntitlementTransport',Transport)
    service=module.PlatformSubscriptions(obj.rp,obj.config,tmp_path)
    service.require(principal,'a');service.require(principal,'b')
    assert len(instances)==1
    assert service.fetch.__self__ is service.fetch_access.__self__
