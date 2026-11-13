"""User application authority is platform-owned, live and separate from scene ACL."""
from dataclasses import replace
import pytest
from packages.infrastructure.platform_subscription import ApplicationAccessDenied, SubscriptionUnavailable
from test_platform_subscription import gate, authorized_access


def test_assignment_is_not_shared_by_workspace_and_revocation_is_immediate(gate):
    obj, owner, _, calls, _ = gate
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
    obj, principal, *_ = gate
    obj.require(principal, 'token')
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
