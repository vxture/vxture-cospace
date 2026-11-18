# Basic-information heading parity — 2026-11-18

The previous hierarchy fix did not match the rendered construction headings: `.construction-flow h3` overrode the local information h3 rule (13px/550 instead of 16px/600). The second-level icons also differed from the material-section baseline.

- Reuse the existing build-stage heading structure and classes for Basic information, removing the conflicting local h3 rule.
- Reuse material-section heading icon and copy structure for Scene description, Location and Change history. Keep edit actions on their respective heading rows.
- Existing permissions, data requests, revision placement and read/edit behavior are unchanged.

Validation: workbench type check/build passed. Authenticated browser comparison at 710px and 1864px for build, association and delivery matched the actual reference computed styles exactly:

| Level | Font / weight | Line height | Icon | Icon/text gap |
| --- | --- | --- | --- | --- |
| Stage (reference: Materials preparation) | 16px / 600 | 24.8px | 20px, primary | 10px |
| Content (reference: Current build materials) | 14px / 500 | 21.7px | 24px, primary | 12px |

All three information subheadings matched; no horizontal overflow. Local screenshots reviewed under ignored `output/playwright/hierarchy/parity-*.png`.
