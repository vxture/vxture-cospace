# AMap production integration

CoSpace uses the official AMap JavaScript API 2.0, with `normal` and `darkblue`
base-map styles. The experimental Tianditu layer is not part of this entry.

Create a **Web 端（JS API）** key and its security JS code. Store these only in
the production Environment secrets `COSPACE_AMAP_WEB_KEY` and
`COSPACE_AMAP_SECURITY_JS_CODE`. Do not add credentials to Vite variables,
source files, screenshots, logs or release archives.

After the required checks and production reviewer gate, deployment sends the
pair over SSH stdin to worker02. The remote helper atomically writes a mode-600
`/srv/md0/cospace/etc/amap.env`, outside the checkout. Compose reads that optional
runtime file. Blank release inputs preserve the existing configuration.

Authenticated, subscription-authorized clients read `/api/map/config`; only
the public JS key and same-origin service host are returned. The security code
stays server-side. `/_AMapService` proxies only the fixed official style and
coordinate-conversion endpoints, with bounded responses and no redirects.
Anonymous requests remain unauthorized.

Scene coordinates are managed with existing `space.manage` authorization,
revision checks and audit history in scene settings. Store the original CRS
explicitly. GCJ02 anchors display directly; WGS84 anchors use the official
conversion API for a display copy. Missing coordinates remain unlocated.
No fixture coordinates or inferred geocoding are substituted into production.

Console restriction fields may vary. Check the selected JS API key's actual
controls. An IP whitelist needs the actual requesting server's public egress
address for proxied calls; a CDN ingress address is not equivalent. Browser SDK
calls must also work under that key's restrictions. Validate both from the
production browser before declaring acceptance; never solve a rejection by
silently switching to a different provider or disabling authentication.

Official references:
- https://lbs.amap.com/api/javascript-api-v2/prerequisites
- https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode
