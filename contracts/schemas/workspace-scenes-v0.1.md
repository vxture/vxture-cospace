# Workspace 场景创建与资料来源分配 v0.1

范围：CoSpace 自有场景资源。平台提供验签身份、当前组织／Workspace 和治理角色；场景由产品保存，不调用虚构的平台场景创建接口。平台订阅／权益接入独立于本契约，本阶段不实现计量。

## 授权依据

已核对平台 `D:/MyWebSite/vxture/vxture-platform/docs/30-design/identity/080-rp-integration.md` §2.6 及 Yucer `docs/20-specs/50-role-permission-catalog.md`：`workspace:owner` 具有该 Workspace 内的产品 owner 基线；其他产品功能授权由应用保存。单场景 manager、`org:owner` 或 `workspace:manager` 不自动取得新建场景能力。

产品部署配置需明确启用当前 `(issuer, org_id, workspace_id)` 的在线创建。启用后，已验签的 `workspace:owner` 或该配置显式列出的 `creator_subjects` 可以创建空场景。初始成员仅绑定当前用户为场景 manager；不从浏览器接收归属、父项目、初始成员或本机路径。

此结论修正 P5a 阶段“等待平台创建接口”的假设；P5a CLI 契约及旧 `/api/spaces` POST 继续保持关闭，不改变其历史验收。

## 部署配置

`cospace.workspace-scenes/0.1`：`revision` 正整数、`workspaces` 数组。每项含：

| 字段 | 含义 |
| --- | --- |
| issuer / org_id / workspace_id | 完整、精确的验签上下文；不按名称或 URL 推断 |
| allow_create | 是否启用本 Workspace 在线创建，默认 false |
| creator_subjects | 本产品明确允许创建场景的完整用户 sub，默认空；不镜像平台成员表 |
| source_bindings | 来源ID → 服务端来源指纹；指纹固定格式和规范化路径，路径只留服务端 |

JSON Schema 见 [配置](workspace-scenes-v0.1.schema.json)。来源目录来自已有受控部署配置。只向当前 Workspace 提供获分配且指纹仍一致的来源。来源文件实际内容仍由登记／预检核验。source_bindings 不是内容摘要，也不能替代内容校验。

配置指定后缺失／损坏返回503。默认位置发现有效配置后，写持久必需标记；以后删除配置及服务重启也不能退回全局来源。没有安装本能力的旧工程部署保留旧来源行为，在线创建始终关闭；正式部署必须显式指定配置文件，不依赖兼容路径。

配置为可信本机管理操作，管理员替换时使用完整验证后的文件原子替换。更改来源目录指纹后，必须明确重新分配。撤销分配阻止新登记及启用，不删除既有资料、构建、发布。过往资料按自身生命周期和场景权限管理。

## HTTP

所有接口要求有效 RP 会话和已验签 access token；响应 `Cache-Control: no-store`。POST 还要求同源 Origin 与既有 CSRF 校验。未知字段、重复请求键拒绝。

`GET /api/workspace-scenes` 返回 `cospace.workspace-scenes-context/0.1`：`enabled`、`can_create`、`workspace_id`、`context_sha256`、`configuration_revision`。不返回其他 Workspace 配置、来源路径或 token。上下文摘要固定部署配置、当前来源指纹、身份与 Workspace，供提交前核对。

`POST /api/workspace-scenes` 请求：

```json
{
  "request_id": "e27e2851ce1d4b35af66f3d751d4cc2af",
  "context_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "name": "一层设备间与相连走廊",
  "description": "设备间及相连走廊，独立管理采集资料与历史版本"
}
```

示例摘要必须换为刚读取的上下文。请求 Schema 见 [创建请求](workspace-scene-create-v0.1.schema.json)。名称去除首尾空格，1—100字符；说明可空，最多500字符。

成功201，重放200，返回 `cospace.workspace-scene-receipt/0.1`：`space_id`、`project_id`、`request_id`、`policy_revision`、`workspace_id`、`actor`、`created` 和质量限制。新空间为空，没有资料、构建、默认本体、选择或发布。父项目仅为产品内目录父记录，与平台 Workspace 有明确归属但不另建客户实体。

401：会话／凭证不可用；403：无创建授权或CSRF不合法；422：请求字段错误；409：上下文变化、请求ID换内容、碰撞或重放资源已变化；503：部署配置或存储暂不可用。503后保留原请求ID核对重试。

## 幂等、恢复和追溯

请求身份由验签 scope、subject、request_id 共同确定，不按名称自动合并场景；同名可能是不同物理场景。同一请求换名称或说明拒绝，换 Workspace 则为另一独立请求。更新配置摘要后，相同已完成请求仍可重放，前提是当前授权仍有效且请求内容未变。

策略SQLite保存 prepared 意图 → 写不可变目录文件 → 同一事务写归属、manager授权、完成回执与审计。实际进程退出时，文件可能已存在但未绑定；无 HTTP 访问权。明确重试复用文件，完成后重放不补回撤销的绑定／授权，不重建丢失目录。失败不做级联删除。

这只是创建请求幂等，不自动识别现实世界中的重复场景。采集数据归属仍须用户选择并核对。P5a 的样本物理场景键及显式接管继续用于预置样本。

## 页面

数据管理复用 DS Dialog、Input、Button，增加“新建场景”。仅显示服务端允许的入口。创建成功切换左侧目录与当前场景，后续配置来源、导入资料、预检、构建。未确认请求保存在本标签页 sessionStorage；刷新后继续同一请求，浏览器不保存 token。移动端标题和操作区上下排列。

所有成果保持 `unverified / production_ready=false / robot_ready=false`。本地模拟通过不表示真实 accounts 生产联调完成。
