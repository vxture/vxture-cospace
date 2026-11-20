# 空间对象固定本体引用 v0.1

宿主接口 `/api/scene-ontology-links`，响应禁用缓存。此契约表示明确的定义引用，不表示实例校验通过或已纳入服务发布。

GET 参数仅允许 `space_id`、`candidate_id`。响应包含来源模型摘要 `source_sha256`、当前引用集合 `revision`、真实对象摘要 `objects`、引用清单 `links`、已发布版本与概念选项 `options`、权限 `can_edit`，以及固定能力声明 `instance_validation=not_performed`、`included_in_publication=false`。

每条引用包含 `object_id`、精确 `reference={module_id,version,sha256}`、`concept_id`、冻结的定义闭包 `bundle`、概念与继承后属性说明 `definition`，及服务端生成的 `linked_by`、`linked_at`。发布时间来自定义发布记录，引用时间不称为发布日期。

POST 公共字段：`action`（`set` 或 `remove`）、`space_id`、`candidate_id`、`source_sha256`、`object_id`、`expected_revision`（非负整数）、`request_id`（32 位小写十六进制）。`set` 另要求精确 `reference` 和 `concept_id`；`remove` 不允许这两个字段。拒绝额外字段与重复 query/body key。

引用必须指向当前可信工作区的真实发布记录，以及当前固定模型中存在的对象。内置草案即使可从定义库读取也不能作为发布版本选用。读取和修改之前均验证场景授权与候选归属；修改另受统一 CSRF 保护。

响应包含 `revision`、`object_id`、`changed`。同一请求内容、可信操作人和分区重试返回原结果；请求标识与内容冲突报 409。新请求重复设置相同定义不增加修订，解除不存在的引用同样不增号。旧快照不被修改。

主要失败：401 未登录；403 无场景权限、候选归属不符或 CSRF 失败；422 参数、对象或概念不合法；409 预期修订/模型摘要变化、请求冲突或固定发布不存在；503 定义库、源模型或消费库不可用/完整性失败。失败不暴露内部文件路径。
