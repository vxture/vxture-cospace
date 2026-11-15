# Spatial service card and list views

Date: 2026-11-15.

## Changes

- Upgrade the original GitHub Packages archives to design-system 15.6.1,
  design-ui 12.5.1 and design-tokens 4.1.0, the registry latest versions checked
  on this date. Record archive SHA-256 values in vendor/provenance.json.
- Use DS ViewModeSwitch directly for the directory, online services, offline
  delivery, feedback and smart devices. Remove the hand-built view buttons and
  their styling. Each toolbar starts with the switch; counts follow when known.
- Default to cards. Global service sections keep independent view choices while
  the workspace remains mounted. Changing views does not change filters,
  authorization, selected publications or service destinations.
- Preserve the existing directory layout in list mode. In card mode, service
  entries use a pale primary surface with heading, capabilities, release metadata
  and a bottom-right action. Feedback remains an unavailable placeholder, without
  fabricated feedback records, counts or actions.
- Device cards have a minimum height of 192px, a responsive 300px minimum column
  width, device name/form, top-right integration status, associated scenes and
  purpose tags. Six decorative SVG silhouettes represent aerial, quadruped,
  wheeled, tracked, humanoid and other forms. Silhouettes do not imply a vendor,
  device connectivity or verified service permissions.

## Verification

- Production TypeScript/Vite build passed with the upgraded DS packages.
- All 96 existing frontend tests passed; repository guardrails passed.
- Local Playwright checks used explicitly mocked authorization-preview, scene
  and device responses. No production business records were changed.
- Checked all five sections in card and list modes at 390, 1052 and 1536px.
  No document or entry content overflow was found. At 1052px device cards were
  358px wide and approximately 195px high; at 1536px they were 384px wide and approximately 195px high.
- Checked mouse and keyboard switching, unchanged fixed-publication links across
  modes, opening a device detail, its associated-scene tab, and the add dialog.
- Local screenshots and browser scripts remain under ignored output/.

Service cards use compact 12px vertical gaps and 20px padding; service cards are
approximately 220px high at the checked widths. Business icon tiles across card
and list modes use the same pale primary surface and primary-colored icon.

This is UI verification with synthetic records, not third-party device
integration acceptance or a production deployment record.
