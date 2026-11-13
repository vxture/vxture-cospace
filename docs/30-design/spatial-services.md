# Spatial service center

`/services` is the workspace-wide service entry. The application router owns
both the global lists and the scene service page.

## Scope and navigation

- Global service navigation always opens a list across the workspace's authorized
  services: 服务目录 / 在线服务 / 离线交付 / 态势反馈 / 服务对象.
- Neither the Header nor the list contains a scene selector. 我的场景 also keeps
  an organization-only Header. 服务发布 remains a scene production workspace.
- Global list rows show service identity, granted capabilities, pinned version,
  publication state and one entry action. There are no covers, card/list toggles,
  scene editing menus or version dropdowns in the list.
- Each outlined row distributes scene identity, capabilities, release information
  and the entry action across the available width. The state badge follows the
  scene title; the entry button aligns to the top. Release metadata uses two
  lines, with the version above the date and version count. Narrow screens stack
  these groups without horizontal overflow. The list has no table header.
- A `space` parameter identifies one scene service page; it is not a list filter.
  Navigation links do not inherit this parameter. Scene service navigation does
  not update the production workspace's remembered scene.
- Service list search and publication state use `q` and `status` URL parameters.
  They survive entry into a service and return. The mounted workspace remembers
  list scroll position per section.

## Scene service page

The fixed page header shows the scene, project/location, publication state,
version selector and authorized 空间预览 action. It has five horizontal tabs:
服务概况 / 在线服务 / 离线交付 / 态势反馈 / 服务对象.

Entry from 服务目录 selects 服务概况. Entry from another list selects its matching
tab. The `tab` and `publication` parameters survive reload, browser history and
tab navigation. Scene-only legacy links are pinned to a version after loading.
An inaccessible scene or publication never falls back to a different one.

服务概况 summarizes granted capabilities, service identity configuration,
recorded requests and attention items. It does not repeat addresses or code.
在线服务 holds version-bound integration instructions, a browser query trial,
scene monitoring, diagnostics and recorded calls. 离线交付 holds the fixed
package, download, verification and local installation/recovery instructions.
Long technical instructions and diagnostic records expand within the tab.

Consumer operations use the selected publication. Refresh cannot silently move
an existing pin to a newer release. Paused, retired and unknown states disable
consumption. Every request remains checked by the server.

Monitoring is separately authorized with `publication.manage`, covers all
versions of the scene and says so explicitly. It is not relabeled as the
selected version's activity. It refreshes every 30 seconds while the page is
visible. Read failures and lack of permission are distinct from zero recorded
calls. Counts do not claim device online status or SLA.

Available consumer capabilities remain `space.preview`, `space.query`,
`space.export`. Feedback is not open yet. Recipient registration now uses
`/api/service-recipients`, with independent `recipient.read` and
`recipient.manage` permissions. The global page lists actual device instances;
the scene tab reads the same records filtered by scene, even without a release.
Registration includes morphology and independent 空间数据采集 / 空间服务使用
purposes per scene. It grants no service access. Vendor integration and instance
activity remain unverified; there are no synthetic device events or online states.
Any future usage record must retain its own version binding rather than inheriting
the header's selected version. See `embodied-agent-service-recipients.md` and
`../../contracts/schemas/service-recipients-v0.1.md` for the registration contract.

The vendored DS supplies navigation, controls, tabs, badges and the mobile
navigation drawer. Product CSS composes the service ledger and responsive scene
workspace using DS tokens. This service UI intentionally differs from the image
cards in 我的场景.
