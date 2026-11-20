# 空间对象固定本体引用 v0.1

宿主接口 `/api/scene-ontology-links`，响应禁用缓存。此契约表示明确的定义引用，不表示实例校验通过或已纳入服务发布。

GET 参数仅允许 `space_id`、`candidate_id`。响应包含来源模型摘要 `source_sha256`、当前引用集合 `revision`、真实对象摘要 `objects`、引用清单 `links`、已发布版本与概念选项 `options`、权限 `can_edit`，以及能力声明 `instance_validation`、`instance_report`、`included_in_publication=false`。无引用时为 `not_performed`，有引用时为 `attributes_checked`；执行过校验不表示校验通过，具体以报告为准。

每条引用包含 `object_id`、精确 `reference={module_id,version,sha256}`、`concept_id`、冻结的定义闭包 `bundle`、概念与继承后属性说明 `definition`，及服务端生成的 `linked_by`、`linked_at`。发布时间来自定义发布记录，引用时间不称为发布日期。

POST 公共字段：`action`（`set`、`remove` 或 `properties`）、`space_id`、`candidate_id`、`source_sha256`、`object_id`、`expected_revision`（非负整数）、`request_id`（32 位小写十六进制）。`set` 另要求精确 `reference` 和 `concept_id`；`remove` 不允许这两个字段。拒绝额外字段与重复 query/body key。

引用必须指向当前可信工作区的真实发布记录，以及当前固定模型中存在的对象。内置草案即使可从定义库读取也不能作为发布版本选用。读取和修改之前均验证场景授权与候选归属；修改另受统一 CSRF 保护。

响应包含 `revision`、`object_id`、`changed`。同一请求内容、可信操作人和分区重试返回原结果；请求标识与内容冲突报 409。新请求重复设置相同定义不增加修订，解除不存在的引用同样不增号。旧快照不被修改。

主要失败：401 未登录；403 无场景权限、候选归属不符或 CSRF 失败；422 参数、对象或概念不合法；409 预期修订/模型摘要变化、请求冲突或固定发布不存在；503 定义库、源模型或消费库不可用/完整性失败。失败不暴露内部文件路径。


## B05b1 实例属性（兼容增量）

`properties` 操作使用相同授权、CSRF、候选生命周期、预期修订和幂等机制。除公共字段外必须提供 `properties`、`valid_time`、`evidence_note`，不得提供 `reference`/`concept_id`。目标对象必须已有固定引用，否则 409 `link_not_found`。

`properties` 为不超过 128 个命名属性的对象，值为 `{value, unit?, quantity?}`。`value` 是字符串、有限数字或布尔值；字符串最多 2000 字符，整数最多 1023 bit，量种/单位最多 80 字符。禁止注入来源、证据 ID、操作人或时间戳。`valid_time` 为 null 或 `{start, end}`，end 可为 null；时间语义由独立内核校验。`evidence_note` 是不超过 2000 字符的非空录入依据。参数结构不合法为 422；类型、必填、单位、量种、最小值、有效期不满足时允许保存可修正草稿，报告返回失败，不等于采用成功。

服务端将声明保存在消费侧不可变修订：`instance_properties`、`instance_valid_time`、`evidence_note`、`properties_updated_by`、`properties_updated_at`。旧模型属性不复制、不覆盖。相同声明的新请求不增修订，重试返回原结果；无变化时保留时间戳和报告摘要。

`set` 可带布尔 `reset_properties`。已有属性记录后更换概念/固定版本，必须明确传 true，否则 409 `link_attributes_present`；明确重置后清除消费侧属性、有效时间和录入依据，按新定义重填。同一引用的重复设置仍为无变化。`remove` 同时解除引用与消费侧属性，旧模型及既有服务发布不变。

`instance_report.scope=linked_object_attributes`，含 `revision`、来源摘要、`valid`、`diagnostics`、逐对象 `objects`，及校验器/实例/定义摘要。固定闭包中同模块版本不一致时返回 `definition_version_conflict`/`conflict`，不自动择新。内核结构错误会阻止整批语义执行；无直接错误路径的对象也不能标为通过，返回 `object_validation_incomplete`/`unknown`。

此报告始终 `relations_checked=false`、`geometry_checked=false`、`professional_review=not_performed`。通过仅表示当前固定定义下属性局部满足，不证明现场事实、完整园区规则、关系或几何正确；不纳入当前或旧服务发布。内核自身的 geometry_not_recorded 信息提示保留，不能当作属性错误。服务端读取时从固定闭包和声明确定性重算报告，不保存可被客户端伪造的通过状态。
