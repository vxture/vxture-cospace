# Platform product member roster

CoSpace reads `GET /platform/product-roster` on the configured platform tailnet
API through its existing confidential product client's workspace-bound service
ticket. The server checks the current operator's product member-management role
before reading. It never forwards Console cookies, browser tokens or identity
selectors. The existing live product-access and subscription checks remain
independent and unchanged.

The minimal contract is documented in the platform integration guide:
https://claude.ai/artifact/54YtaMf3K7tPULZur29Vzf#product-roster
and its consumer obligations:
https://claude.ai/artifact/WjCmptqy2TR5mfXLoNt1pP#product-roster
Platform implementation is tracked by vxture-platform/vxture-platform#710;
publication and production acceptance are prerequisites to product rollout.

Each read completes keyset pagination with a consistent version before exposing
the directory to the browser. Only `limit` and the unchanged returned cursor are
sent upstream. A changed version or HTTP 409 restarts from page one once; repeated
changes, loops, invalid scope, unknown authorization mode, invalid subjects,
oversized responses or the bounded read budget fail explicitly. No partial or
stale roster is presented as an empty or complete directory. The service retains
no roster cache or platform membership copy.

Platform subjects are used exactly as returned, never reconstructed from Console
IDs. Names come from the platform response. Null names show a neutral missing-name
label without account, email, phone or UUID fallback. The browser's member list,
role assignment picker and scene-scope list all join local scene grants and data
scope onto this completed authoritative roster. Newly eligible people appear
before their first product visit, with the existing default viewer baseline.

Every role/scope save reads the current roster again and validates that the target
remains eligible. Product role, scene boundaries, policy revision, CSRF and the
workspace owner's scope-management boundary are checked separately at save time.
A completed upstream read is a point-in-time eligibility snapshot; it is not a
distributed transaction with platform changes or a persistent authorization.
Revocation after that snapshot is still enforced by the independent live product
access gate on use. Leaving the roster never deletes historical grants, scope
restrictions or audit records automatically.

The local mock assembly without platform subscriptions retains its explicitly
labeled product-record directory. Production with platform subscriptions always
uses the roster and fails closed on read failure; there is no fallback switch.
The current consumer completes at most 1,000 pages (200 items per page), with a
30-second round budget plus the active request timeout. It does not claim
unlimited-directory scalability or server-side upstream name/role search.

This integration changes no subscriptions, seats, commercial limits, platform
member administration, header or organization display contract. It requires no
policy-schema migration or environment variable additions.
