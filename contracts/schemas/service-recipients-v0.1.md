# 智能体服务对象登记 v0.1

本接口仅在已认证的 authorized_workbench 装配中开放。`profile` 为 `cospace.service-recipients/0.1`。用途登记不授予空间数据提交、在线调用、离线获取或反馈权限；不创建可信设备绑定，不提供设备控制。现有 S2S 严格请求模型保持不变。

## 查询与修改

- `GET /api/service-recipients`：参数 `space_id`、`q`、`morphology`、`purpose`、`offset`、`limit`。默认 50 条，每页 1–100 条；按修改时间倒序与 ID 排序。空结果与读取失败分别返回 200 与 503。
- `POST /api/service-recipients`：原子登记设备信息和零到多个空间关系，返回 201。
- `PATCH /api/service-recipients/{agent_id}`：提交完整可编辑登记快照和 `expected_revision`，返回 200；服务端核对已有关系和新关系的权限，冲突返回 409。

写操作沿用现有 Origin、平台会话、CSRF 与订阅校验。额外参数或字段拒绝；表单不接受租户、授权、厂家凭据、可信身份或实际使用版本字段。所有值通过 `RecipientChange` 严格模型验证。

请求字段：`request_id`（32 位十六进制）、`expected_revision`（新建为 0）、`name`、`morphology`、`morphology_note`、`manufacturer`、`model`、`external_id`、`contact`、`relations`。设备名称不作为唯一身份；外部标识当前是人工声明，尚无厂家身份域，不能据此识别真实调用实例或声称验证通过。

设备形态：`aerial` 飞行式、`quadruped` 四足式、`wheeled` 轮式、`tracked` 履带式、`humanoid` 人形式、`other` 其他形态。其他形态须填写说明；所有形态均支持任意用途组合。

每条关系含 `space_id`、`purposes`、`usage_modes`。`purposes` 独立选择 `collect`（空间数据采集）、`use`（空间服务使用），至少选一项；`usage_modes` 可选 `online`、`offline`，无 `use` 时不得填写。每场景最多一条关系，取消关联从当前快照移除，历史保留。无发布成果的空间仍可登记关系，不绑定页头查看版本。

## 身份与授权

数据以已验证 principal 的 `(issuer, org_id, workspace_id)` 隔离，不接受客户端提供归属。

新增独立空间能力 `recipient.read`、`recipient.manage`。viewer 和 engineer 拥有前者，manager 和工作区 owner 的已绑定空间基线拥有两者。它们不改变 `publication.manage`、`space.query`、`space.export` 或采集权限。

仅返回拥有读取权限的关联空间。只读用户可查看与可见场景相关的智能体；不返回隐藏场景关系，也不计入用途筛选。编辑共享实例的完整快照须拥有全部原有关联场景及新增关联场景的管理权限，防止部分可见快照删除隐藏关系。

允许管理员先登记无空间关联的实例；这类实例仅向创建人（仍具管理能力）或同租户工作区 owner 开放，防止无场景记录向整个工作区泄露。无场景工作区 owner 也能先登记设备。当前管理 UI 不支持删除或归档实例；解除关系只是登记变化，没有已验证设备接入权限可供撤销，不能宣称撤销现有代理身份。

## 持久化与事实

存储位于 directory 根目录 `service-recipients.sqlite3`。事务同时保存实例、递增修订、修改前后快照、可信操作者、时间和幂等结果。重新启动读取同一记录；只读空列表不创建数据库。每工作区最多 10000 条登记是本地存储保护预算，不是商业设备额度。

幂等键作用域为工作区及操作者；同键同请求返回已提交结果，不同内容拒绝。修改还需对比修订号，阻止并发覆盖。幂等重放仍核对当前权限。列表不返回幂等键、内部创建人、历史快照或凭据。

返回 `integration_state=pending`、`external_identity_verified=false`。没有设备心跳或实例事件协议，不提供在线状态、在线率、实际使用版本或虚构接入记录。页面详情明确显示待厂家对接与尚未验证。

实例及空间关系读写失败返回 503；权限不足返回 403；非法登记和查询返回 422；重复请求冲突及过期修订返回 409。未知 API 路径不能继承已登录会话权限。
