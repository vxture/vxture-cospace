# Spatial service center

`/services` is the consumer entry under 场景中心. It uses the app router, never a standalone HTML page.

The current domain design and roadmap are in [空间服务域](spatial-service-domain.md).
Its five sections use the published DS ShellSidebarFrame + ShellSidebarNav, with a DS Drawer on phones. Its sections are 服务目录 / 离线交付 / 在线服务 / 态势反馈 / 服务对象.
Offline delivery, online consumption and feedback are independent capabilities.
Service recipients record service relationships, not device control or operation.

The first increment groups authorized `/api/spaces` publications by space. Each
space appears once with an explicit version selector. The initial active version
is pinned for the page lifetime; refreshing cannot silently select a newer release.
Unavailable or removed versions do not fall back to a different publication.
A capability drawer shares the selected fixed version across preview, query and
export. Every request remains checked by the server. Unknown lifecycle fails closed.

Available operations remain `space.preview`, `space.query`, `space.export`.
No feedback or recipient API exists yet: those sections explicitly show unavailable,
without synthetic records, online counts, credentials or non-persistent save forms.
The browser query uses the user session; machine service identity is separate.
Existing S2S support is deployment/authorization dependent and is not inferred from
browser access. Version synchronization and heartbeat are not claimed as available.

The official vendored DS 15.0.1 provides tabs, controls, menus, badges and drawers.
Product CSS only composes the domain cover, card regions and responsive layout.
Typography and colors use DS tokens; search/filter/description use 12px roles,
key controls 14px, headings 18/16/14px and compact tags 10px.

The version control lives at the card footer left as a DS dropdown radio menu.
The cover reuses SceneCover from scene selection, including authorized images and
the explicitly labeled default spatial illustration. Product CSS only places
the sidebar/content and adapts card columns to available content width.
# Header scene context and service card states

The product header uses the published DS Popover, ShellPanelContent, Input,
and ShellPanelRow for scene selection. Search matches scene and project names;
the current scene has a circle check. Unselected or inaccessible context uses
DS warning tokens. Scene selection is URL scoped, retains the current module
or service section, and clears previous scene record IDs. Service navigation
retains this context. No global last-scene storage is introduced.

Service cards show three fixed capability badges: offline delivery, online
service and situation feedback. DS status icons and tones reflect authorized,
active capabilities; feedback remains unavailable until its integration exists.
Each badge exposes its state through its accessible name and tooltip. Preview
remains an operation, not a fourth capability badge. Version selection uses
a persistent secondary button, 32px tall, labeled `Ver: <short version>`.
Section headings reuse the same DS icon mapping as functional navigation.

Custom CSS only supplies header truncation, popover width/scroll limits,
warning token bindings and alignment with the existing 32px header/footer
controls; DS owns control surfaces, typography, rows and badge states.
