"""Platform roster consumption never turns a failed/partial read into membership."""
import io
import json
from urllib.error import HTTPError

import pytest

from packages.infrastructure import platform_roster as module
from packages.infrastructure.platform_identity import PlatformVerifierConfig
from packages.infrastructure.platform_roster import ProductRoster, ProductRosterChanged, ProductRosterUnavailable
from test_platform_subscription import gate


ALICE = 'usr_00000000-0000-4000-a000-000000000701'
BOB = 'usr_00000000-0000-4000-a000-000000000702'


@pytest.fixture(autouse=True)
def verifier_config(gate):
    gate[0].rp.config.verifier_config = PlatformVerifierConfig(
        issuer='https://accounts.vxture.com', audience='cospace',
        jwks_url='https://accounts.vxture.com/oidc/jwks')


def page(principal, items=None, **changes):
    return {'org_id': principal.org_id, 'workspace_id': principal.workspace_id, 'product': 'cospace',
            'authorization_mode': 'assigned_seats', 'version': 'version-one',
            'items': items if items is not None else [{'subject': ALICE, 'display_name': 'Alice', 'eligible': True}],
            'nextCursor': None} | changes


def reader(gate, fetch):
    service, principal, *_ = gate
    return ProductRoster(service.rp, service.config, page=fetch), principal


def test_complete_pages_preserve_exact_subject_and_nullable_name(gate):
    calls = []
    def fetch(principal, cursor):
        calls.append(cursor)
        return page(principal, nextCursor='opaque-next') if cursor is None else page(principal, [
            {'subject': BOB, 'display_name': None, 'eligible': True}])
    roster, principal = reader(gate, fetch)
    value = roster.read(principal)
    assert value.names == {ALICE: 'Alice', BOB: None}
    assert value.version == 'version-one' and calls == [None, 'opaque-next']


def test_valid_empty_roster_is_distinct_from_failure(gate):
    roster, principal = reader(gate, lambda p, _: page(p, []))
    assert roster.read(principal).names == {}
    roster.page = lambda *_: (_ for _ in ()).throw(ProductRosterUnavailable())
    with pytest.raises(ProductRosterUnavailable):
        roster.read(principal)


@pytest.mark.parametrize('change', [
    {'org_id': 'another'}, {'workspace_id': 'another'}, {'product': 'another'},
    {'authorization_mode': 'everyone'}, {'version': ''}, {'items': {}}, {'nextCursor': ''},
    {'nextCursor': 'not opaque'}, {'items': [{'subject': ALICE, 'eligible': True}]},
    {'items': [{'subject': 'console-user-no', 'display_name': 'Name', 'eligible': True}]},
    {'items': [{'subject': ALICE, 'display_name': '  ', 'eligible': True}]},
    {'items': [{'subject': ALICE, 'display_name': None, 'eligible': 'true'}]},
])
def test_invalid_or_foreign_page_is_never_a_member_directory(gate, change):
    roster, principal = reader(gate, lambda p, _: page(p, **change))
    with pytest.raises(ProductRosterUnavailable):
        roster.read(principal)


def test_changed_version_restarts_without_mixing_partial_members(gate):
    calls = []
    def fetch(principal, cursor):
        calls.append(cursor)
        if len(calls) == 1:
            return page(principal, nextCursor='old-cursor')
        if cursor:
            raise ProductRosterChanged()
        return page(principal, [{'subject': BOB, 'display_name': 'Bob', 'eligible': True}], version='new-version')
    roster, principal = reader(gate, fetch)
    assert roster.read(principal).names == {BOB: 'Bob'}
    assert calls == [None, 'old-cursor', None]


def test_repeated_change_and_cursor_loops_fail_instead_of_returning_partial(gate):
    roster, principal = reader(gate, lambda *_: (_ for _ in ()).throw(ProductRosterChanged()))
    with pytest.raises(ProductRosterChanged):
        roster.read(principal)
    roster.page = lambda p, _: page(p, nextCursor='same')
    with pytest.raises(ProductRosterUnavailable):
        roster.read(principal)


def test_version_mismatch_between_successful_pages_also_restarts(gate):
    calls = []
    def fetch(principal, cursor):
        calls.append(cursor)
        if len(calls) == 1:
            return page(principal, nextCursor='next')
        return page(principal, [], version='different')
    roster, principal = reader(gate, fetch)
    assert roster.read(principal).names == {}
    assert calls == [None, 'next', None]


def test_page_budget_does_not_publish_an_incomplete_roster(gate):
    clock = [0]
    def fetch(principal, cursor):
        clock[0] += 31
        return page(principal, nextCursor='next')
    roster, principal = reader(gate, fetch)
    roster.clock = lambda: clock[0]
    with pytest.raises(ProductRosterUnavailable):
        roster.read(principal)


def test_transport_sends_only_pagination_with_one_service_ticket(gate, monkeypatch):
    obj, principal, *_ = gate
    requests, tokens = [], []
    roster = ProductRoster(obj.rp, obj.config)
    roster.transport.token = lambda p: tokens.append(p) or 'test-service-ticket'
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _):
            return json.dumps(page(principal, [] if len(requests) == 2 else None,
                                   nextCursor='opaque-cursor' if len(requests) == 1 else None)).encode()
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Response()
    monkeypatch.setattr(module, 'build_opener', lambda *_: Opener())
    assert roster.read(principal).names == {ALICE: 'Alice'}
    assert tokens == [principal]
    assert [r.full_url for r in requests] == [
        'https://internal.example/platform/product-roster?limit=200',
        'https://internal.example/platform/product-roster?limit=200&cursor=opaque-cursor']
    assert all(r.get_header('Authorization') == 'Bearer test-service-ticket' for r in requests)


@pytest.mark.parametrize('status', [400, 401, 403, 404, 503])
def test_transport_errors_never_become_empty_members(gate, monkeypatch, status):
    roster, principal = reader(gate, None)
    roster.transport.token = lambda _: 'test-service-ticket'
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, status, 'upstream-private-error', {}, io.BytesIO(b'private'))
    monkeypatch.setattr(module, 'build_opener', lambda *_: Opener())
    with pytest.raises(ProductRosterUnavailable, match='^product_roster_unavailable$'):
        roster.read(principal)


@pytest.mark.parametrize('raw', [b'{"items":[],"items":[]}', b'x'*1_048_577])
def test_transport_rejects_ambiguous_or_oversized_json(gate, monkeypatch, raw):
    roster, principal = reader(gate, None)
    roster.transport.token = lambda _: 'test-service-ticket'
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, limit): return raw[:limit]
    class Opener:
        def open(self, *_args, **_kwargs): return Response()
    monkeypatch.setattr(module, 'build_opener', lambda *_: Opener())
    with pytest.raises(ProductRosterUnavailable):
        roster.read(principal)
