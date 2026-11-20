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


## B05b2 已保存关系的显式映射（兼容增量）

GET 增加模型原关系清单 `relations`、消费侧 `relation_links` 和 `relation_report`；发布选项增加每个模块自己的关系定义 `options[].relations`。旧修订没有 relation_links 时视为空集合。属性报告保留原范围，不受关系定义冲突混入。

POST 增加 `relation_set`/`relation_remove`。公共字段沿用场景、候选、来源摘要、expected_revision、request_id，但用 `relation_id` 代替 object_id。关系 ID 必须真实存在于固定模型，禁止客户端伪造端点或注入确认状态。设置另要求 `reference`、`definition_id`（所选模块的关系 ID）、`direction`（forward/reverse）、`valid_time`（非 null）、`evidence_note`；解除不接受这些字段。来源和目标来自原声明，forward 沿用、reverse 显式互换；不按旧 type_id 或名称自动匹配、反转。关系定义来自真实发布记录并冻结完整闭包。

两端对象须先有概念引用，否则 409 relation_endpoints_unlinked。映射以 reported 人工报告保存，由服务端记录操作人和时间；不接受客户端声明专业审核或 corroborated。时间区间/类型/固定闭包不符可保存待修正草稿，但集合报告返回失败。

对象引用和关系映射共用同一分区、不可变修订、CAS、幂等与生命周期锁。属性更新保留映射并重算集合校验。有映射引用某对象时，调整/解除该对象概念引用返回 409 link_relations_present，必须先显式解除相关映射；不会级联静默删除关系。解除映射保留原关系和对象引用；同值或重复解除不增号。

relation_report.scope 为 linked_attributes_and_mapped_relations，coverage=mapped_relations_only，含 unmapped_count、逐条 relations 和独立内核诊断。两端继承类型、所有已引用对象的属性、断言引用、有效时间格式与区间顺序共同校验。集合包含任何错误则逐关系 valid 不标为通过；结构失败和版本冲突均不能冒充局部通过。

relations_checked 表示本报告尝试执行映射关系校验；valid 才表示本次实际满足。geometry_checked=false、professional_review=not_performed、included_in_publication=false。当前不启用 park-baseline 的园区完整性、基数及层级规则，也不自动校验断言区间被对象区间覆盖；不得将此报告当作完整关系验收。未映射声明不自动进入断言集合，计数单列。

关系不存在、定义 ID 不存在为 422 relation_not_found/relation_definition_not_found。其余鉴权、CSRF、来源变化、归档、并发和工作区隔离沿用原接口。原模型、几何、对象属性及历史服务发布不写入本次映射。


## B05c 固定对象联查

只读 GET `/api/scene-ontology-view`。必需参数 space_id、candidate_id、object_id、revision（十进制非负整数，无前导零，范围 0..2^63-1），可选 at（严格 UTC ISO 时刻，Z 后缀）。禁止额外参数、重复键与 POST。沿用 space.preview 场景及候选归属授权，先授权再读取，Cache-Control=no-store。

revision 为明确的消费修订；找不到返回 404 link_revision_not_found，不改读最新值。0 表示空消费基线。已存在修订只读查询，不创建/迁移消费库；校验快照摘要和当前固定来源摘要，不接受跨候选/工作区回退。归档来源允许查看。接口不依赖当前可选发布库，定义和属性均来自该修订冻结闭包。

响应 profile=cospace.scene-ontology-object-view/0.1，包含场景、候选、来源摘要、revision、object_id、对象原名称、at、claim（固定概念/属性/定义/人工依据/服务端审计，不含 bundle）、相关本体 relations（含方向和依据）、attribute_report/relation_report、model_location。未引用的对象 claim=null，仍可查询真实模型证据。

time_query_policy=classify_without_inference。时间状态为 active / inactive（半开区间 start <= at < end）、not_recorded、invalid 或 not_filtered；保留原声明，不删除不活跃数据，不将未记录期当成无限有效。非法 at 返回 422 invalid_query_time；草稿期本身非法则 state=invalid，保留校验失败报告。

model_location.available 要求米制局部点锚、固定 frame_id、spatial.npz 模型摘要与证据摘要一致；服务 source 通过已有模型读取器核对对象/点证据。available 不是现场核验。preview_available 另要求三条坐标轴记录，缺失轴保留点锚证据但禁用画布；点云画布继续通过已有 anchor-preview API 校验来源和摘要。点锚不代表完整实体几何。

geographic_location.available=false，reason=geographic_handoff_not_connected。实际地理配准/地图定位归后续 B07，不从局部点锚生成经纬度。included_in_publication=false、professional_review=not_performed。新服务发布消费归 B06，旧服务发布不读取本接口的最新值。
