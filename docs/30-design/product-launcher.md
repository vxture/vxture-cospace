# Product launcher layout

Scene workflow design: [服务发布工作区](service-publication-workspace.md) and
[版本编码与依赖快照](version-identification.md) define the shared basic-information
entry, build-to-publication numbering, and immutable version context. These are
design requirements; their implementation status is recorded in each document.

The launcher has three groups: 场景中心, 场景作业, 公共资源.
The default homepage entry always targets /space without scene/record parameters.
空间服务 is the consumer entry beside 我的场景; it targets /services without
carrying selected scene or record parameters.
Module links retain only the selected scene through the existing navigation
contract. Space preview is reached through scene center; build,
association and delivery retain their existing scene selection guards.

The panel uses published DS ShellPanelContent, ShellPanelSection and
ShellPanelRow components. Product CSS defines only the three-column composition,
responsive stacking, title underlines and background treatment. The background
is a 135-degree gradient from 12% DS primary mixed into the DS popover color,
through 4%, to the standard popover surface. It adapts to the DS theme without
literal brand colors. No platform logo or Ruyin label appears inside the panel.

Group headings contain only their names, without a default-home marker or supplementary home note. Entry labels,
icons, descriptions, focus/hover/active/disabled states remain DS components.
Descriptions are concise to avoid clipping. Below 700 px the three groups stack
vertically, with a bounded scrollable panel. Each title has one horizontal dashed underline;
32 px desktop column gaps and 24 px mobile group gaps separate the groups.
Space preview remains available inside a selected scene, and is omitted from
the launcher to avoid duplicating scene-center navigation. The publication
module name is consistently 服务发布 across product navigation and handoffs.
The production shell and isolated map lab share one ProductLauncher component.
