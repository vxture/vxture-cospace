# Header context and account identity

The internal header retains its 48px height and 32px control geometry. After
the CoSpace product brand it shows organization name, a short 12px divider,
and the selected scene name. Scene names come from the authorized scene directory
and update with router context. No selected scene shows 未选择场景; unknown or
inaccessible names never fall back to raw IDs. Long names truncate with a title.
The optional context hides below 580px to preserve global tool access.

Launcher headings contain only the group name. The home badge and explanatory
paragraph are omitted; entry descriptions and three title underlines remain.

The DS ShellUserMenu supplies avatar, name, contact metadata, preferences and
actions. Account center uses the DS `newTab` option. Mainland phone numbers use
the platform's country-prefix plus 3-4-4 grouping (`+86 138 0000 0000`); email
appears on a separate line. Contact verification is labeled explicitly as phone
or email verification, never personal identity certification. Missing profile
fields are omitted, with an avatar fallback when the account has no picture.

Display-only profile fields are projected from already verified platform access
claims, stored with the encrypted RP session and refreshed on token rotation.
Existing sessions can be upgraded from a still-valid verified token. Profile
fields never influence principal roles, tenant binding, authorization or session
validity; tokens and credentials remain server-side. The projection accepts
bounded text and HTTPS avatar URLs without embedded credentials. Login scopes
remain the existing openid/profile/email; the platform already emits available
email/phone contact fields with its tenant identity claims.

Custom CSS composes the bounded header context and two-line contact metadata.
It uses DS typography/color/spacing surfaces; the DS owns panel controls,
avatar, verification badge and external-link behavior.
