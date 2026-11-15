# Device detail: shared service frame and scoped editing

Date: 2026-11-15. The current layout follows the scene-service detail frame.
The earlier continuous-section layout is retained below as historical context.

## Current layout: scene-service detail frame

- Device detail shares the scene-service header, sticky position, underline tabs,
  and card styles. The title remains the device name. The device's four tabs
  show their own content and retain the existing scoped editors.
- Existing deviceTab links select the corresponding panel. Changing tabs keeps
  the device request and restarts content scroll at the top. An entry from a
  scene retains its scene and publication but shows one header and one tab bar.
- Browser verification at 390px and 1052px confirmed fixed header position on
  scroll, matching tab and card styling, no horizontal overflow, preserved
  scene context, no refetch on tab changes and both independent edit flows.

## Earlier continuous layout

- The global detail page uses the device name as its only primary heading, with
  smart-device category and morphology below. Remove the redundant generic
  heading and return-to-list button; the existing navigation opens the list.
- Device information, associated scenes, integration and usage records all
  appear in one continuous page, separated by spacing and thin horizontal rules.
  No tabs or surrounding section cards are used.
- Information groups device attributes and identifiers in two columns; small
  screens stack the groups. Timestamps and revision sit together below. Empty
  optional values use an em dash instead of repeated explanatory text.
- Associated scenes align scene name, purposes and delivery modes in columns,
  becoming stacked rows on narrow screens. Integration and usage remain honest
  unconfigured/empty states, without unsupported edit or connection controls.
- Existing deviceTab URLs now scroll to the corresponding visible section. They
  remain reloadable and keep scene/publication context; backend authorization,
  exact device-ID matching and unavailable handling remain in place.

## Editing

- Device information and associated scenes each open the existing creation
  dialog at the corresponding form section. Creation keeps its two-step flow;
  editing shows only the selected section with cancel/save actions.
- The current full draft preserves fields outside the edited section. Existing
  expected_revision and request_id handling, server permission checks and
  revision-conflict errors remain authoritative. No new write endpoint is used.
- Only manageable devices expose edit actions. Manufacturer integration and
  usage records have no fabricated edit workflow.

## Verification

- TypeScript/Vite production build and all 98 frontend tests passed.
- Current-layout browser QA at 390px and 1052px verified the shared sticky
  heading, 44px underline tabs, card radius/padding, independent panels, tab
  reload, preserved scene/publication URLs, readonly controls and scoped edits.
  Tab switching does not refetch device data and resets content scroll.
- Local Playwright QA used synthetic devices and mocked API responses only.
  Earlier continuous-layout QA at 390/1052/1536px checked section visibility,
  title hierarchy, absence of
  tabs/back button, responsive information columns and horizontal overflow.
- Exercised information-save preservation of relations, relation-save
  preservation of information, expected revision advancement, retained conflict
  errors, legacy section URLs and reload, readonly/empty/missing/403 states,
  and the unchanged two-step creation flow.
- Screenshots, scripts and logs remain in ignored output/. These checks are
  local UI acceptance, not a production deployment or vendor integration test.
