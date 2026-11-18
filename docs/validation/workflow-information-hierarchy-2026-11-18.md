# Workflow information hierarchy validation — 2026-11-18

- Shared workflow title row reserves 32px; metadata row reserves 24px, matching the build-description action. Real wrapping remains responsive.
- Build header uses FlowArrow, matching the launcher workflow icon.
- Basic information uses h3 with the shared section divider; scene description, location and history use h4 with icons. Separate edit permissions remain in effect.
- Revision is reported from the existing settings response to the workflow header, scoped to scene ID, across build, association and delivery. No additional settings request.

Validation:
- `pnpm --dir apps/workbench build` passed.
- Authenticated local browser fixture: at 710/831px the information/model headers both measure 129px; at 1864px both measure 85px. No document overflow.
- Verified headings, read mode, section edit/discard and revision placement in all three workflows.
- Location-only permissions expose location editing without scene-description editing; exactly one settings GET on refresh.
- Screenshots reviewed locally under ignored `output/playwright/hierarchy/`.
