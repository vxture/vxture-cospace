# 业务项目与场景关联 v0.1

状态：D01 后端实现。页面项目视角在 D02 接入，跨项目共享及数据版本引用在 D03 接入；本接口不声明这些能力已经提供。

## 归属与兼容

`WorkspaceProjects` 在既有持久目录 `preview-directory/business-projects.sqlite3` 保存业务项目、场景主项目关联、工作区修订及请求审计。首次写入惰性创建，首次读取返回空目录且不创建项目库。该库已纳入部署 checkpoint；实际部署仍须经过正常发布审核。

所有记录以服务端验证后的 `(issuer, org_id, workspace_id)` 摘要隔离。业务项目的稳定 ID 为 `project-` 加 16 位小写十六进制。场景一个时刻仅有一个业务主项目，可以解除或重新关联；旧场景记录、输入、构建、候选和发布中的 `project_id` 是历史来源绑定，永不由本接口修改。

场景主项目关联不等于资源管理归属迁移。D02 的资源管理归属须单独登记，重新关联场景不能追改已登记资源的管理归属或版本引用。

现有 `/api/projects` 继续提供历史目录兼容信息，新业务查询使用 `/api/data-projects`。经过人工明确确认的旧业务项目可用 adopt 接纳，保留原 ID；接纳不自动关联该目录下的场景。场景创建和初始化产生的两个已知工作区技术目录不允许直接接纳；先建业务项目，再显式关联场景。不能按名称、路径或时间推算归属。

## 授权

沿用中央会话及平台访问检查。POST 必须通过同源 Origin 与 CSRF 校验。作用域、actor 不接受客户端参数；未知字段拒绝。

项目管理沿用 `workspace_manager`（工作区所有者或现有产品管理角色）。场景关联还需当前场景的 `data.manage` 和 `space.manage` 权限；项目管理资格不扩大场景数据权限。普通数据管理人员只能读取与自己有 `data.manage` 权限的场景存在关联的项目；没有关联的项目仅管理者可读。

项目列表中的 `scene_count` 始终只统计当前身份有数据管理权限的场景，标明 `scene_count_scope=authorized_scenes`。场景列表只返回同一可见集合；操作历史仅管理者可查，涉及不可见场景的事件不返回。项目成员、共享授权及跨工作区交换尚未实现，不能将项目关联视作新增数据访问授权。

## 读取

`GET/HEAD /api/data-projects`：

- `view`：`projects`（默认）、`scenes`、`history`。
- `project_id`：可选，限定一个当前可见业务项目。不可见或不存在的项目返回 403。
- `q`：可选检索文本，最多 100 字符。
- `offset`：默认 0；`limit`：默认 20，最大 100。

响应 profile 为 `cospace.business-projects/0.1`，包含 `workspace_id`、`revision`、`view`、`can_manage`、`items`、`total`、`offset`、`limit`、`next_offset`。查询和数量过滤在服务端执行。一次读取处于同一项目数据库事务快照；场景目录和请求授权按当前请求读取，不宣称跨系统事务快照。

项目记录有名称、说明、active/archived 状态、创建及更新身份和时间、可选 `legacy_project_id`。场景记录包含当前业务 `project_id/project_name`、历史 `origin_project_id`、关联状态和当前可管理资格；没有显式关联时返回 `project_id=null`、`association_state=unassigned`，页面应显示“待关联业务项目”。

## 写入

`POST /api/data-projects` 共用字段：`action`、`request_id`（32 位小写十六进制）、`expected_revision`（当前工作区项目修订）、`reason`（1–500 字符非空白）。不提供删除操作。

| action | 其他字段 | 行为 |
| --- | --- | --- |
| create | name、可选 description | 创建业务项目；创建身份来自当前主体。 |
| adopt | legacy_project_id、name、可选 description | 显式接纳当前授权场景所关联的旧项目，保留原 ID，不自动迁移成员。 |
| update | project_id、name、可选 description、status | 更新项目元数据；status 默认 active，可设 archived。仍有关联场景时拒绝归档。 |
| associate | space_id、project_id | 设定场景业务主项目；project_id=null 表示解除关联。目标须为同作用域的 active 项目。 |

名称 1–100 字符，说明最多 500 字符；文本去首尾空白。一次事务原子保存业务变更、工作区修订和审计。对同一 scope + actor + request_id，完全相同命令重试返回原事件，`replayed=true`；参数变化返回 409。重试仍须通过当前权限检查。

成功返回事件及 `replayed=false`，含修订、操作、可信 actor、时间、原因、目标项目及 before/after。关联事件另含 space_id。调用方成功后重新读取当前目录，不把重放事件的旧修订当成当前修订。

## 错误与验收

422：参数结构、枚举、文本、标识或分页不合法。403：无权限、不可见项目、Origin 或 CSRF 不通过。409：修订冲突、请求标识复用、目标不是有效项目、仍有关联而归档、重复接纳或尝试接纳技术目录。更新不存在的项目返回 404。存储不可读或损坏返回 503，不重建覆盖。

验收覆盖双项目双场景、重启恢复、并发重试、修订冲突、重新关联与解除、归档前检查、历史项目显式接纳、技术目录拒绝、跨发行方/组织/工作区隔离、场景权限过滤、伪造身份拒绝及来源文件字节保持不变。
