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
# Persistent scene and session context

The app uses one persistent React Router parent layout. Authentication, theme
and scene context remain mounted while functional child routes change. The
services Launcher entry is handled by the same client router as other modules.
Navigation alone does not bootstrap authentication again.

Scene preference is stored per subject, organization and workspace. Explicit
URL scene context wins; an explicit empty scene clears the preference. A bare
functional URL restores remembered context, while `/space` remains the scene
catalog with the remembered scene visible in the header. Unavailable stored
scenes are shown honestly, never replaced automatically or treated as access.
Storage contains only a scene identifier and grants no permission. Cross-tab
live editing is independent; a newly opened page restores the saved preference.

Initial load confirms the session. Existing trusted activity checks (30-second
throttle), focus/visibility resume checks and server-side authorization remain.
These checks use the central platform's validity schedule. API 401 hides the
workspace immediately; transient authority failures retain drafts behind the
session boundary. Successful local logout signals other same-origin tabs;
other-product logout is detected through central confirmation on resume or
normal activity. Cross-origin logout is not claimed to be an instant push.
In-flight confirmations cannot restore a session after a logout invalidates
its generation. No credentials are stored in browser scene preferences.
