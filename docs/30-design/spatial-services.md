# Spatial service center

`/services` is the consumer entry under 场景中心, alongside 我的场景.
It clears scene/record context and uses the History router and the platform
application route allowlist. No standalone HTML entry is published.

The catalog derives fixed-version service entries from the existing authorized
`/api/spaces` response. Each publication exposes only operations explicitly
granted by the server: 空间预览 (`space.preview`), 空间查询 (`space.query`),
离线交付 (`space.export`). Missing or unknown lifecycle metadata fails closed;
paused and retired releases remain inspectable but cannot be consumed.
The default filter shows active services, newest publication first. No automatic
version switching occurs. Every actual resource request remains subject to the
existing server authorization and publication lifecycle checks.

The detail drawer supplies scope, fixed version, release date, the granted
operation, a copyable resource address and capability-specific support.
Preview opens the existing dual-view application. Query shows the real range
query request contract and reuses the authorized interactive query form when
preview metadata is accessible. Offline delivery reuses the verified package
consumer guide. Cross-system service identities require administrator setup;
browser sessions and cookies must not be copied into integrations.

The published DS supplies ViewHeader, Card, StatusBadge, Input, NativeSelect,
Button and Drawer, including theme and interaction states. Product CSS is limited
to responsive grid composition, bounded descriptions and wrapping endpoint/version
metadata. Typography and colors reference DS tokens; search/filter/description
use 12px tokens, key controls 14px and headings 18/16/14px according to the DS.
Existing scene catalog layout is reused to keep width and toolbar behavior aligned.

This entry does not invent a public service marketplace, credentials, commercial
limits, live device status or an alternative permission system. Platform
subscriptions remain centrally owned. Runtime safety and precision are not certified.
