# SG1：身份提案、旧点锚投影与局部包

本批是[态势底图实施计划](../../docs/architecture/态势底图实施批次与数据清单-v0.1.md)的 D0 后续验证，不修改 SG0 或正式发布协议，也不写入现有候选。参考输入和输出位于[样例目录](../../examples/scene-graph/sg1/)。

## 身份提案

[Schema](synthetic-identity-changes-v0.1.schema.json) 表达 `split`（一对多）、`merge`（多对一）和 `unresolved`（待判断的对应关系）。每个端点必须存在于各自的快照、属于同类 `kind`，且不能继续用作同一对快照中的保留身份。每侧端点不能参与多个提案；新增和移除报告只列未被提案覆盖的 ID。`unresolved` 不触发合并或 ID 继承，结果始终未核实。样例中的拆分与未决是备选提案，不可同时使用；合并以新 ID 结束。此实现仅检查一对快照，完整历史上的 ID 禁复用和采用审批留待真实生命周期集成。

场景相同，快照 ID 不同，坐标和本体一致。保留的 ID 不能改变基础 `kind`；实体记录（不含修订号）或其绑定几何变化时必须提高修订号；独立观测变化不要求改实体修订。SG1 不支持坐标变换或本体迁移。

## 旧点锚投影

[映射 Schema](legacy-anchor-mapping-v0.1.schema.json) 固定旧 `preview-objects/0.1` 文档原字节摘要、所属场景、模型 ID、`spatial.npz` 摘要和坐标系，以及显式的旧/新类型 ID 对照。`project_legacy_anchors` 对照旧 Schema 和声明，保留对象 ID、原坐标、点索引和两侧类型 ID。输出只声明 `reference_point`，没有包围盒、状态或空间连接。类型映射是调用者的建议，不是目标本体核实；未读取模型点，未执行变换或跨场景归并。结果标记 `source_unverified`，不能作为 SG0 合成图或正式底图直接安装。

## 局部包

[清单 Schema](synthetic-scene-subset-v0.1.schema.json) 固定来源快照、选择 ID、依赖实体 ID、组件摘要及字节数。JSON 容器有 `manifest` 和 `payloads` 两部分。四个必需组件为：

| 组件 | 依赖 | 内容 |
|---|---|---|
| entities | — | 实体、本体、坐标和合成证据目录 |
| geometry | entities | 所含实体的几何表达 |
| structure | entities、geometry | 选取的连接和两端均在包内的普通关系 |
| observations | entities | 所含实体的原始观测 |

选择规则是实体 ID 选择，不是几何裁切。基于原始选择展开一跳连接，补齐构件、端口和对侧实体；不会从依赖实体再向外递归。外部关系可省略，因此包内没有某对象或关系，不证明源中不存在。没有状态时效决议、安装、网络分发或访问授权。

组件和 SG0 来源快照摘要按本批固定的 Python JSON 序列化：UTF-8、键排序、紧凑分隔符、保留 Unicode、禁止非有限值。数组顺序保留。不声称符合 RFC 8785 或任意语言的浮点序列化一致；将来跨语言时需固定独立编码。旧点锚文档摘要直接取输入原字节，不使用上述重编码。

`validate_scene_subset` 验证外部来源引用、组件摘要、固定依赖和内部闭合，不证明源内容或选择完整。`verify_subset_against_source` 还从提供的完整源重新构造并比对，验证相对于该源和一跳规则的内容一致性；不证明真实世界覆盖或来源可信，摘要不是签名。
