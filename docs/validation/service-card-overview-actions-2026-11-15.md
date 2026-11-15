# Spatial-service card summaries and destinations

Date: 2026-11-15. Supersedes the card geometry and entry behavior in
`service-card-views-2026-11-15.md`; that document remains the DS upgrade record.

## Layout and behavior

- Directory, online services, offline delivery, feedback and smart devices share
  a three-section card: heading, content, footer. Minimum height is 216px with
  20px padding and 16px gaps. Versions/dates appear at the lower left and actions
  at the lower right. Device cards retain their pale morphology artwork.
- The workspace container uses at most three columns. Containers at or below
  1000px use two; at or below 650px use one. Ultra-wide displays do not add a
  fourth column. List views retain the directory row layout.
- The card surface is a keyboard-accessible button opening a summary drawer.
  Summaries use loaded directory data: opening or closing does not navigate,
  fetch permissions or fetch another record. Device summary content remains
  present during its closing animation.
- One destination renders a direct button. Multiple destinations render the
  shared DS vertical-three-dot dropdown, with an icon and label per item.
  Actions are separate from the card surface and never open the summary.
- Service destinations preserve the selected publication and originating list
  filters. Only granted capabilities produce online/offline destinations;
  unavailable publications remain subject to the destination's existing checks.
- Feedback is still an honest unavailable placeholder. Its summary reports no
  records; no fabricated detail-page link or device activity is added.

## Device management routing

- `/services?section=recipients&device=<id>&deviceTab=<tab>` opens an actual device
  page. Tabs are device information, associated scenes, integration and usage
  records. A scene-service context also retains scene/publication parameters.
- Reload uses the existing authorized directory API with an ID search, then
  requires an exact ID match. Missing/inaccessible devices produce an explicit
  unavailable state rather than falling back to another device. Backend scene
  authorization and write permissions remain authoritative.
- Tab changes update the URL without refetching the directory. Returning to the
  list removes only the device and deviceTab parameters. Editing reuses the
  existing permission-gated editor and API.
- Registration, purposes and vendor identifiers do not establish verified device
  identity, connectivity or service entitlement. Integration and usage records
  keep their existing unconfigured states.

## Verification

- TypeScript check, production build, 98 frontend tests and repository
  guardrails passed. New contract tests cover capability-filtered destinations,
  fixed publications, filter retention, device identity encoding and scene URLs.
- Local Playwright QA used synthetic authorization-preview, six scene records
  and all six device morphologies; no production data was modified.
- All five sections checked at 390, 1052, 1536 and 2300px: 1/2/3/3 columns,
  216px cards and no document/card horizontal overflow.
- Checked summary request counts and unchanged URL, independent menu actions,
  icon-bearing destinations, pinned publications, single-action service entry,
  device page reload, tabs without requests, edit/cancel, return to list,
  keyboard summary entry and missing-device handling.
- Screenshots, mock scripts and logs stay under ignored `output/`. This record
  documents local UI validation, not a production deployment or vendor acceptance.
