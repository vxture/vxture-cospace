# @vxture/globe 0.1.0

Shared CesiumJS globe engine for CoSpace and agent applications. This release is a
TypeScript **source package** for TS-aware bundlers (Vite); it is not a browser
script or a published npm registry release. `pnpm pack` produces a portable source
archive. Install that archive in another project, with Cesium **1.147.0**; React 19
is optional and only needed for `@vxture/globe/react`.

## Host responsibilities

- Authenticate through the host's BFF and obtain authorized scene/version data.
  The SDK validates shape, budgets and binding consistency, not permissions.
- Fetch CoSpace `/api/globe/config` using an authenticated session. It is public
  provider configuration, without credentials. Never put service tokens in URLs.
- Serve the matching Cesium `Assets`, `Workers`, `ThirdParty`, `Widgets` directories
  under `assetsBaseUrl`, and import `cesium/Build/Cesium/Widgets/widgets.css`.
  CoSpace's Vite plugin and production image already do this.
- Give the viewer host a size and `position: relative`. Keep configuration stable
  while mounted. Call `destroy()` when leaving; React handles this automatically.

## Two agents, one scene version

```ts
import {createGlobe} from '@vxture/globe';
import 'cesium/Build/Cesium/Widgets/widgets.css';

// Values come from the host's authenticated data adapter, never from URL input.
const globe = createGlobe(hostElement, authorizedConfiguration);
const binding = {spaceId: authorizedSpace.id, publicationId: authorizedPublication.id};
globe.setScenes([{...binding, name: authorizedSpace.name, position: wgs84Position}]);
globe.setLayers([
  {id: 'agent-a', binding, color: '#4361ff', features: agentAPoints},
  {id: 'agent-b', binding, color: '#20a584', features: agentBTrack},
]);
globe.command({type: 'focus', binding});
// Later: globe.destroy();
```

Features are `{id, name?, geometry: {type:'point', position:[lon,lat,height?]}}`
or `{id, name?, geometry: {type:'line', positions:[[lon,lat],...]}}`. Positions
must be WGS84; heights are ellipsoid metres, and lines currently clamp to terrain.
Layer IDs distinguish agents, while each layer binds to an available scene AND
publication. Replacing scenes drops layers whose binding is no longer present.
Limits per viewer: 10,000 scenes, 100 layers, 50,000 total feature vertices.
This release does not georegister or load project point-cloud/models.

React hosts can render `GlobeCanvas` from `@vxture/globe/react`, passing
`configuration`, `scenes`, `layers`, `satellite`, `scrollZoom`. `onReady` exposes
the controller and receives `null` on cleanup; `onState`, `onSelect`, `onCamera`
provide viewer events. `resize` is automatic, or available on the controller.

## Optional embedded viewer

Use `/space?embed=globe&space=<id>&publication=<id>&parent_origin=<exact-origin>`.
The backend requires a same-origin or explicitly allowed parent and the viewer
checks the logged-in user's scene and publication permission. No latest-version
fallback. Sign in to CoSpace in a top-level window first. Cross-site iframe
sessions depend on browser cookie policy; use SDK+BFF when third-party cookies
are unavailable. Cookie/CORS/CSRF policy is unchanged.

```js
const origin = 'https://cospace.example';
const frame = document.querySelector('iframe');
window.addEventListener('message', event => {
  if (event.origin !== origin || event.source !== frame.contentWindow) return;
  if (event.data?.protocol !== 'vxture.globe/0.1') return;
  // Handle ready, ack, error, selection; ready includes the pinned binding.
});
function reset() {
  frame.contentWindow.postMessage({protocol:'vxture.globe/0.1',
    requestId:crypto.randomUUID(), command:{type:'reset'}}, origin);
}
```

Commands: `reset`, `north`, `tilt`, `zoom-in`, `zoom-out`, or
`{type:'focus',binding:{spaceId,publicationId}}` matching the pinned publication.
Messages with tokens, URLs, arbitrary coordinates, layers or unknown keys are
discarded. The child checks both exact parent origin and frame identity. Replies
use the exact parent origin. Runtime command failures return
`{type:'error',requestId,code:'command_unavailable'}`; accepted commands return
`{type:'ack',requestId}` (acceptance, not animation completion). A scene without
valid WGS84 coordinates remains visible in the directory but cannot be focused.
