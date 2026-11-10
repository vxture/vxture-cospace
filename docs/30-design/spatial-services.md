# Spatial service center

`/services` is the consumer entry under 场景中心. It uses the app router, never a standalone HTML page.

The current domain design and roadmap are in [空间服务域](spatial-service-domain.md).
Its five sections are 服务目录 / 离线交付 / 在线服务 / 态势反馈 / 服务对象.
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
