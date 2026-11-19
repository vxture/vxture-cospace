# 空间访问策略 v0.1

2026-11-13：服务对象登记新增 `recipient.read`、`recipient.manage` 两个独立能力。viewer、engineer 可读，manager 及工作区 owner 的已绑定空间基线可管理；登记用途不授予调用或采集权限，详见 `service-recipients-v0.1.md`。

结构定义见 `space-access-policy-v0.1.schema.json`，由 `packages.service.space_access.SpaceAccessPolicy.model_json_schema()` 生成。

`profile` 固定为 `cospace.space-access-policy/0.1`。`bindings` 将每个物理 `space_id` 显式绑定到 `(issuer, org_id, workspace_id)`；`grants` 将 `(issuer, subject, space_id)` 映射到一个产品角色 `viewer/engineer/manager`。subject 保存完整 `usr_...`。禁止额外字段、通配角色或通配空间。

JSON Schema 检查字段形状。应用模型另外检查：每个空间只绑定一次，同一用户空间组合只授予一次，所有 grant 引用已绑定空间。策略结构合格不代表其来源可信；I3从受控服务端SQLite存储加载，浏览器不得提交策略替换当前权限。

授权先检查绑定与已验签 principal 的 issuer/组织/工作区一致，再检查平台 `workspace:owner` 的产品管理员基线或产品 grant。单纯平台 org:owner、workspace:manager、裸 owner/admin 不自动产生产品空间权限。没有绑定和没有授权均拒绝，不从旧目录推断用户归属。

I3的`SpacePolicyStore`以完整策略、递增revision和历史记录原子保存；受信任本机管理员通过`manage_space_policy` CLI提交`expected_revision`、actor和reason，冲突拒绝覆盖。actor是本机操作者声明，可信度依赖主机访问控制。每次业务请求重新读取策略，撤权对下一次准入生效，不追溯终止已准入请求或删除已有离线副本。存储缺失或损坏返回503，不回退旧策略或匿名访问。

`authorized_workbench`装配已覆盖目录过滤、资产、查询、下载及写操作；`engineering_preview`仍为独立无认证的本机工程服务，不因导入规则而自动启用授权。没有浏览器成员授权API或空间创建API；账户登录契约见`platform-session-v0.1.md`。运行与边界见`docs/guides/空间业务权限I3运行.md`。


## 2026-11-19：独立场景数据范围

可选 `scene_scopes` 将 `(issuer, org_id, workspace_id, subject)` 映射到一组 `space_ids`。无记录表示整个工作区；空数组表示零个场景；指定列表只覆盖这些场景，不随新增场景扩展。所有引用必须属于完全相同的工作区绑定，不允许重复范围或重复场景。

功能权限与数据范围分别保存。有效访问为角色能力与数据范围的交集；显式工程师/管理者授权不能绕过数据范围，默认查看者基线也不能绕过。工作区所有者保留该工作区已绑定场景的所有权基线。目录、详情、资料、下载与写操作共享同一权限策略校验，范围变更对后续请求生效。

`POST /api/scene-permissions/scopes` 仅允许验签后的工作区所有者调用，需要 CSRF、`expected_revision`、已知成员、同工作区场景和非空原因；在同一写事务中重验范围并保存完整策略审计。传 `space_ids: null` 恢复整个工作区，传数组设置指定范围。禁止调整自己的所有者范围。管理者仅可读自己管理范围内的已知成员，不能用该接口修改工作区级限制。

当前为整个场景级数据隔离，不提供场景内部字段、对象或资料分类过滤；不宣称已支持百万场景或规范化授权存储。四种角色的功能组合仍为产品固定定义，权限管理页提供能力清单，不提供尚未实现的自定义权限编辑。
