# 本体分组配置 v0.1

状态：F02 首批实现。业务归组与资源按组检索属于 F03，尚未接通。本契约管理分组定义，不改本体语义、依赖或摘要。

## 挂载与授权

配置页面 `/settings?section=ontology-groups`，归 CoSpace 配置管理 → 业务配置 → 本体分组配置，复用 DS 导航。独立 UI 从 `@vxture/ontology-ui/group-configuration` 导出，注入 load/save 客户端，不导入 CoSpace 的路由、身份、场景或网络地址。

`GET/HEAD/POST /api/ontology-configuration/groups`。当前仅 workspace_manager 可读写，沿用已有工作区所有者或实际管理角色判定。中央会话、权益检查先执行；POST 校验 Origin 和 CSRF。作用域由服务端可信的 issuer/org_id/workspace_id 派生，拒绝查询参数和客户端伪造 scope 字段。不需要选择场景，不读旧工作区本体规则或场景目录。

通用存储 `packages/ontology/group_configuration.py` 仅依赖标准库，接收显式 scope、actor、root；宿主负责身份转换与存储目录。该模块不在当前定义内核 wheel 的交付范围内，后续独立引擎装配时需单独打包配置服务及存储适配。

## 读取

返回 profile=`vxture.ontology-group-configuration/0.1`、revision、can_manage、groups、history、history_limit。groups 已按当前顺序排列；包含 group_id、name、description、origin、status 和内部 sort_order。历史最近 50 条，存储保留全部事件。

7 个稳定预置 ID：preset-built_environment、preset-outdoor、preset-electrical、preset-water、preset-fire_safety、preset-monitoring、preset-operations。预置名固定，可调整说明、启停和顺序。自建 ID 使用 group- 加 UUID；名称按 NFKC/casefold 检查同作用域重复，包括已停用项。停用不删除身份，允许重新启用；无永久删除接口。

预置集合由当前代码版本固定；未提供新增预置项的升级迁移器，不宣称已实现跨预置版本升级。

## 新建与编辑

POST 字段：request_id（32 位小写十六进制）、expected_revision、group_id（新建为 null）、name、description、status（active/inactive）、sort_order（兼容内部字段，不能用来改顺序）、reason。名称 1–60 字符、说明及原因最多 500 字符，原因必填。未知字段拒绝。

新建分组自动追加到底部，编辑保持原位置。界面没有排序数字字段，用户不需要输入或维护内部顺序值。资源归组不会随配置编辑而迁移；已有引用不删除。

## 四个移动操作

同一路径 POST：request_id、expected_revision、group_id、move（top/up/down/bottom）、reason。界面为置顶、上移、下移、置底，直接保存，生成明确的移动原因。搜索或状态筛选时禁用移动，清除筛选后针对完整顺序操作。

在数据库事务内检查修订并调整完整顺序，内部重新生成顺序值。首尾边界禁用无效按钮，服务端边界空操作不增加修订。排序事件包含移动前后完整 sequence（稳定 group_id 与名称），界面显示前后名称顺序，不展示数字排序值。

## 并发、重试与审计

配置修订是作用域级。BEGIN IMMEDIATE 内核对 expected_revision，冲突返回 409；不能覆盖他人变更。同 request_id 与同 actor/规范化负载重复提交幂等；负载变化拒绝。成功变更与审计在同一 SQLite 事务提交，记录 actor、reason、时间、修订和变更前后数据。

返回错误：422 请求无效；409 同名、陈旧修订、请求冲突、预置名修改或目标不存在；503 存储不可用/配置损坏。配置损坏不能回退为空配置或重新生成预置配置。页面保留失败表单，提示刷新核对；未保存表单接入宿主离开提示。

当前存储为宿主运行目录中的 ontology-group-configuration.sqlite3，不进入 Git。本地工程预览写入忽略的 output/ontology-preview/runtime，使用合成作用域和 local-preview actor；不代表生产登录及多用户端到端验收。
