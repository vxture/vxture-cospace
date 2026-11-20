# 对象语义成果合同 v0.1（B06a）

状态：合同基线，尚未接入生产发布。结构见同名schema；结构通过不能代替本文的跨成员语义检查。

实现必须启用严格UTC日历校验；JSON Schema的format在部分运行环境仅为注解，不能单凭format字段认定时间有效。覆盖计数运算、定义依赖和跨成员绑定同样由成果校验器核验。

## 成果范围

profile=`cospace.object-semantic-artifact/0.1`。支持固定对象语义查询，不提供定位、通行、路径规划或任务执行能力。独立本体库不依赖本合同，由宿主成果适配器调用本体内核。

一个成果固定一个可信工作区、场景、模型候选及消费修订。`source_manifest_sha256`固定model.json字节，`source_model_sha256`固定spatial.npz；两者不得混用。对象身份采用上述来源范围内的object_id，不宣称跨候选稳定身份。schema版本、成果修订、消费修订和发布版本分别记录。

## 成员清单

所有成员路径固定为单层相对文件名，不接收客户端文件系统路径；每项记录字节数、SHA256及JSON媒体类型。清单不包含自身摘要，外层发布记录固定该清单的字节和摘要。

| 成员 | 内容 |
| --- | --- |
| object-index.json | 此模型完整对象身份索引、显示名、点锚与模型证据引用，以及框架/单位/源摘要；不是新增稳定主数据 |
| definitions.json | 所采用对象和关系全部固定模块定义依赖闭包，按module_id去重；冲突禁止采用 |
| claims.json | 固定消费修订的对象分类、显式属性、有效期、人工依据和关系映射，保留来源关联；定义闭包统一存储，不重复嵌入每条声明 |
| validation.json | 针对以上固定字节重算的属性及映射关系局部校验，绑定校验器profile及输入摘要；无映射关系时标not_applicable，不伪造通过 |

定义引用仍使用本体固定reference（模块、版本、摘要），由Catalog重新核验。claims中不重复缓存可漂移的definition描述。审计主体在对外交付中仅使用此成果内一致的不可逆标识，不泄露登录账号、邮件或会话；可信原始主体审计保留在宿主。该投影不是伪造审批，仍保留声明时间及操作类型，清单明确audit_identity_policy。

人工文字依据随声明携带，附件仅引用且未随包携带；model.json/spatial.npz在本配置中均为外部证据引用。外层空间交付是否提供相应字节按其配置清单表达，不因摘要存在声称离线复核过模型。此成果的声明/定义查询自包含，几何证据重新验证不是该能力。

## 覆盖与时间

objects_total为完整模型索引数量，linked_objects为已采用分类声明的对象数，unlinked_objects为其差；三者按集合重算。每个对象最多一条本体分类声明，不允许幽灵对象或重复ID。固定消费修订整体采用，不在本版支持任意挑选部分错误声明绕过校验。

relations_total为原候选关系数，mapped_relations为实际映射数，unmapped_relations为差；逐条核对原关系ID、方向、端点和定义。覆盖声明固定为linked_objects_and_mapped_relations，不能将部分覆盖称为全园区完整。未映射关系保留在旧空间关系合同，不混入新本体断言。

本成果是声明快照，不按发布时刻静默删除已过有效期的历史声明。结构合法的历史区间可以交付，查询时按UTC显式时刻分类；无有效期记录不代表永久有效。非法时间/单位/类型/闭包冲突等导致局部校验失败时禁止采用。

## 发布预检、失败与幂等

发布请求显式选择对象语义配置，并携带固定consumer_revision、source_manifest_sha256和预检返回的snapshot_sha256。未选择时不读取消费库。显式选择后禁止回退最新值、零修订、空声明或静默省略成果。

宿主先做publication.manage及来源归属授权/CSRF，再读取固定模型与消费修订。工作区和操作人取可信身份；对外清单不授予读取权限。预检与发布分别核验固定来源、快照摘要及合法性，沿用原发布串行化锁；幂等指纹包含原选择修订和整个语义选择，同request_id不同选择拒绝。重试返回已有固定发布时不重新读取最新草稿。

对象属性校验必须通过。存在关系映射时集合关系校验必须通过；无映射时不要求伪造关系。缺失声明依据、未知对象/端点、定义依赖丢失、摘要不符、覆盖计数错误、预算超限均阻止此次采用。专业及现场状态固定not_performed，工程完整性不替代专业批准。

冻结文件先写暂存目录，完整校验后原子登记。不得将运行SQLite、认证信息、宿主路径、原始账号或任意URL获取能力装入包。初版成果总字节上限8MiB，单文件上限8MiB；外层离线包继续受原32MiB预算约束，不为新增成果取消限制。

## 兼容及消费

旧publication.json、旧offline profile和未采用语义配置的新发布保持现有行为；缺新成果字段表示not_included，不表示损坏或应从最新库补齐。已声明成果却缺文件/错误摘要必须拒绝读取，不能按旧发布降级。

语义成果清单及四个成员由外层发布files完整绑定。在线固定版本语义API与新增离线profile读取相同成员和同一校验/查询实现；不在旧offline profile下偷偷加入文件。离线消费者通过外部可信包摘要验证，拒绝未知profile、成员、重复文件、大小超限及篡改。仅支持旧profile的消费者应明确拒绝新profile。

现有轻量ontology.json、objects.json、business.json、relations.json不改写；新对象语义成果独立声明。本版不改变分区包/设计包的合同；导出尚不支持携带新成果时必须在交付清单明确not_included，不称为语义完整副本。发布暂停/退役、在线场景授权及离线导出授权沿用现有机制；已下载副本不承诺远程收回。

## 验收及后续实现

B06b：预检、冻结、显式发布选择及幂等。B06c：在线/离线同源查询及旧合同兼容。B06d：安全、历史稳定、预算、完整性、生命周期和上线收口。本合同不触发部署。

### B06b 后端接口

POST `/api/publication-semantic-preflight` 接收且仅接收space_id、candidate_id、semantic_selection。selection预检输入为consumer_revision与source_manifest_sha256，返回固定snapshot_sha256、覆盖计数及局部报告；要求publication.manage、可信工作区、候选归属和CSRF，响应no-store。非法输入422，采用条件不满足409，不创建或迁移消费库，不返回定义/实例全文。

原POST `/api/publications`增加可选semantic_selection，包含以上三个固定选择字段。工作区/操作人由宿主注入，独立预览端没有可信身份时拒绝语义采用；不接受浏览器指定scope/actor。未选择仍走原流程，显式选择无法通过时整次发布失败。外层publication记录包含semantic_artifact（路径semantic-artifact.json、artifact_id、profile）、选择和散列化scope；清单及四项成员写入原发布的files并绑定摘要。

B06b是后端冻结能力，不单独上线；发布选择界面及固定语义查询在B06c一并接通。B06c接通前，含新成果的完整包和分区包返回409，不静默生成缺语义的旧包；旧发布的导出不变。

### B06c 同源查询与离线消费

GET `/publications/{id}/api/semantics` 返回 `cospace.publication-semantics/0.1` 摘要，包括 included/not_included、固定实例修订、覆盖计数、校验范围、能力边界及对象清单。加 `object_id` 返回 `cospace.publication-semantic-object/0.1` 固定声明查询；可选 `at` 必须是严格UTC日历时刻，用于分类历史声明及映射关系的有效性，不执行推理。无object_id不能传at，拒绝重复及未知查询参数。响应no-store，沿用space.preview授权及发布生命周期，不授予导出权限。

在线及离线统一使用 `FixedSemantics` 核验清单与发布绑定、成员字节/摘要、完整对象/原关系索引、定义依赖闭包、集合覆盖、局部校验报告及其输入摘要；重建固定定义后查询，不读取当前消费SQLite或公共本体最新版本。模型位置保持外部证据引用状态，不能由固定声明推导出已核验几何或地理定位。

采用新成果的完整包使用 `cospace.preview-offline/0.5`，在原有空间、对象、旧业务及关系文件之外增加semantic-artifact.json与四个语义成员。包内文件集合必须完整，profile、package.files、publication.files和成果members交叉绑定；不能删文件后按旧profile降级。`OfflinePreview.semantics(object_id=None, at=None)` 与在线摘要及对象查询等价，校验过程无需网络。旧profile继续可读，未采用成果返回not_included，不访问最新库补齐。

现有新建发布入口增加右侧准备面板，默认不采用语义；选择正整数固定消费修订并预检后，将完整semantic_selection传入原发布确认与POST。修订或来源变化后预检失效。分区包仍明确拒绝携带新语义成果，B06c不扩展其合同。在线暂停/退役停止新读取和导出，已下载副本继续按其固定内容本地消费。

验收必须包含：旧发布完全不读取新库；最新修改/解除/定义升级不改变旧发布；缺失及非法修订阻断；对象/关系集合覆盖核验；空关系适用性；闭包冲突与篡改；身份投影；在线离线等价；暂停/退役及不同场景/工作区拒绝；失败不产生可见半成果。
