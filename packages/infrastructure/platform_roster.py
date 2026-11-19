"""Live, ticket-bound product roster; no local copy of platform membership."""
from dataclasses import dataclass
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

from packages.infrastructure.platform_identity import IdentityUnavailable, NoRedirect
from packages.infrastructure.platform_subscription import EntitlementTransport, PRODUCT, unique_json


SUBJECT = re.compile(r'^usr_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class ProductRosterUnavailable(IdentityUnavailable):
    pass


class ProductRosterChanged(ProductRosterUnavailable):
    pass


@dataclass(frozen=True)
class RosterSnapshot:
    names: dict[str, str | None]
    version: str


class ProductRoster:
    def __init__(self, rp, config, *, page=None, clock=time.monotonic):
        self.config, self.clock = config, clock
        self.transport = EntitlementTransport(rp, config)
        self.page = page

    def fetch_page(self, principal, cursor=None, *, bearer):
        try:
            query = {'limit': '200'}
            if cursor is not None:
                query['cursor'] = cursor
            request = Request(self.config.api_base+'/platform/product-roster?'+urlencode(query),
                              headers={'Authorization': 'Bearer '+bearer, 'Accept': 'application/json'})
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
                if response.status != 200:
                    raise ValueError('roster_status')
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise ValueError('roster_response_budget')
                return unique_json(raw)
        except HTTPError as exc:
            exc.close()
            if exc.code == 409:
                raise ProductRosterChanged('product_roster_changed') from None
            raise ProductRosterUnavailable('product_roster_unavailable') from None
        except (IdentityUnavailable, OSError, ValueError, TypeError, KeyError):
            raise ProductRosterUnavailable('product_roster_unavailable') from None

    def read(self, principal):
        # A changing page sequence restarts once. Never return a partial list or a stale fallback.
        deadline = self.clock()+30
        page = self.page
        if page is None:
            try:
                bearer = self.transport.token(principal)  # One workspace-bound service ticket per read.
            except IdentityUnavailable:
                raise ProductRosterUnavailable('product_roster_unavailable') from None
            page = lambda p, cursor: self.fetch_page(p, cursor, bearer=bearer)
        for attempt in range(2):
            try:
                return self.read_snapshot(principal, deadline, page)
            except ProductRosterChanged:
                if attempt:
                    raise
        raise ProductRosterUnavailable('product_roster_unavailable')

    def read_snapshot(self, principal, deadline, page):
        names, cursors = {}, set()
        cursor = version = None
        for _ in range(1000):
            if self.clock() >= deadline:
                raise ProductRosterUnavailable('product_roster_read_budget')
            value = page(principal, cursor)
            items, next_cursor, current_version = validated_page(value, principal)
            if version is not None and version != current_version:
                raise ProductRosterChanged('product_roster_changed')
            version = current_version
            for item in items:
                subject = item['subject']
                if subject in names:
                    raise ProductRosterUnavailable('product_roster_duplicate_subject')
                names[subject] = item['display_name']
            if next_cursor is None:
                return RosterSnapshot(names, version)
            if not items or next_cursor in cursors:
                raise ProductRosterUnavailable('product_roster_cursor_loop')
            cursors.add(next_cursor)
            cursor = next_cursor
        raise ProductRosterUnavailable('product_roster_read_budget')


def bounded_text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and not any(ord(c) < 32 for c in value)


def validated_page(value, principal):
    if (not isinstance(value, dict)
            or (value.get('org_id'), value.get('workspace_id'), value.get('product')) !=
               (principal.org_id, principal.workspace_id, PRODUCT)
            or value.get('authorization_mode') != 'assigned_seats'
            or not bounded_text(value.get('version'), 512)
            or not isinstance(value.get('items'), list) or len(value['items']) > 200
            or 'nextCursor' not in value):
        raise ProductRosterUnavailable('product_roster_invalid_page')
    cursor = value['nextCursor']
    if cursor is not None and (not bounded_text(cursor, 4096) or not cursor.isascii() or any(c.isspace() for c in cursor)):
        raise ProductRosterUnavailable('product_roster_invalid_cursor')
    for item in value['items']:
        if (not isinstance(item, dict) or not isinstance(item.get('subject'), str)
                or not SUBJECT.fullmatch(item['subject']) or item.get('eligible') is not True
                or 'display_name' not in item
                or item['display_name'] is not None and
                   (not bounded_text(item['display_name'], 500) or not item['display_name'].strip())):
            raise ProductRosterUnavailable('product_roster_invalid_member')
    return value['items'], cursor, value['version']
