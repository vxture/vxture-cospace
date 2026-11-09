# Scene selection DS alignment

## Published dependency

The workbench consumes the official `@vxture/design-system@15.0.1` tarball
downloaded from GitHub Packages. Its registry SHA-1 is
`955c1fea150c41e3aa644576c1106a148f1b68b3`; the lockfile also pins SHA-512.
The package depends on design-ui 12.0.0 and design-tokens 4.0.0.
The archive is vendored for reproducible builds without registry credentials.

## Typography and components

DS sans is used for body text and controls; DS brand is reserved for headings.
Default heading roles are 18 / 16 / 14 px. Main content and primary actions use
body/label (14 px). Search, filters, descriptions, secondary actions and metadata
use body-small (12 px). Compact status tags and illustration captions may use
label-micro (10 px). Role variables keep the global font-size preference working.

Buttons, search inputs, selects, tabs, segmented controls, switches, popovers,
dropdown menus and the detail drawer are DS components. Map and catalog use
the same SceneDetail drawer with publication, location and scoped workflow links.
Shell panels inherit the 15.0.1 published 32 px row rhythm.

## Product CSS retained, and why

| Area | Reason |
| --- | --- |
| Catalog grid and responsive list | Scene covers and publication metadata need a domain-specific responsive layout; controls remain DS components. |
| Cover illustration and semantic card surface | The illustration is spatial domain content; lifecycle colors come from DS primary/info/warning/destructive/neutral tokens. |
| Map overlay positioning, translucency and backdrop blur | Overlays must expose the map underneath and avoid attribution, controls and safe areas. DS does not define a geographic workspace layout. |
| Map status tabs | A single DS Tabs surface uses translucent token colors and removes nested frames/shadows for map readability. Keyboard and selection behavior remain DS. |
| AMap marker DOM and pin glyphs | The SDK consumes HTML markers rather than React components. Geometry expresses scene state; colors use DS semantic tokens. |
| Shared detail drawer sections and 32 px actions | Domain metadata and scoped links need arrangement inside the DS Drawer; its focus trap, close behavior and overlay remain DS. |
| Compact search and secondary action typography | Explicit body-small roles implement the owner's 12 px scene-selection specification; they do not introduce another font family or arbitrary font scale. |

## Administrative layer capability

The separate persisted Administrative divisions switch controls the official
`AMap.DistrictLayer.Country` overlay at province depth. Its fill is transparent
and its boundary contrast follows the global DS theme. It defaults off.
Turning it off removes the enhancement, not the built-in borders painted by
the selected official base-map style. The UI states this limitation.
Reference: <https://a.amap.com/jsapi/static/doc/20230922/index.html>.

## Map surface transparency

Every map overlay uses one surface recipe in both themes: 60% DS card color
(40% transparency) and 3 px backdrop blur. This includes the directory heading,
directory, phase tabs, mode switch, tool group, legend, status/group panels,
settings popover and the map-only detail drawer. Portal surfaces declare the
same variables explicitly. Nested controls use 12% card color, with 24% hover
and 36% selected primary-muted tints, avoiding stacked opaque panels. Text,
icons, semantic status tags and primary actions retain their DS contrast.
Catalog detail drawers retain the standard DS surface.

Dark map appearance uses AMap's official neutral `dark` style (幻影黑), replacing
`darkblue`. Administrative enhancement lines use cartographic neutral dark grays
(nation #454545, province #383838); these are map data paint, not UI brand colors.
Light map appearance and its boundary treatment remain unchanged.

The official dark basemap retains red national borders. A grayscale filter is
scoped to SDK map canvases only to neutralize these accents; marker DOM,
legend/status colors, attribution and all UI retain their original colors.
