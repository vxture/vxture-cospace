# 本机对象标注候选契约 v0.1

B2将人工标注作为新的模型候选，不直接修改已有候选或固定发布。空间、基础候选ID及model.json摘要、本体ID/版本/摘要必须显式指定。创建不自动选择或发布。

POST `/api/semantic-candidates`：`space_id`、`base_candidate_id`、`base_manifest_sha256`、`ontology_ref={ontology_id,version,sha256}`，以及1至100个 `objects={object_id,type_id,properties,point_index}`。基础候选与空间不一致、摘要过期、未知类型、必填缺失或重复对象ID均拒绝。客户端不能填写确认结果或任意坐标；服务端按固定spatial.npz中的点索引生成米制锚点与证据引用。

GET `/candidates/{id}/api/anchor?point_index=N`返回候选及manifest摘要、坐标系、米制坐标、几何成员SHA256和点索引。它只证明锚点来自指定模型，不证明该点对应的语义类型或现场质量。

新候选保存：

objects.json遵循[JSON Schema](preview-objects-v0.1.schema.json)，加载时执行结构、固定引用、本体规则与证据绑定检查。对象ID使用可寻址的ASCII标识，中文名称存于properties.name。

- `objects.json`：标注版本ID、空间/项目、坐标系、几何摘要、固定本体引用及对象列表。每对象含object_id、type_id、properties、anchor_m、模型点证据以及 `confirmation=unverified`。
- `ontology.json`：解释这些实例的固定规则原文，摘要与引用一致。
- model.json的`semantic_annotation`绑定以上成员和基础候选ID/摘要；human_view与agent_view均引用同一objects.json，无第二套独立对象事实。几何与表面单元不重新估计。

GET候选或固定发布的 `/api/objects` 及 `/api/objects/{object_id}`返回相同对象身份、类型、锚点、本体引用和模型版本。旧无对象版本明确返回 `semantic_objects_not_available`，不推测对象。人视图和智能体视图显示相同锚点标记；类型均保留待核实声明。

带对象的离线包使用 `cospace.preview-offline/0.2`，在0.1四成员基础上增加objects.json和ontology.json；新读取器兼容旧0.1，旧读取器应拒绝不支持的0.2。离线验证模型/发布/规则/对象摘要与归属绑定，返回对象结果与在线逐字段一致。包内不带完整点云，模型点证据是固定发布的绑定记录，不是离线重新进行几何或现场校核。

实际样本验证允许建立明确标识的流程测试标注。模型锚点来自真实点云，类型与对象名称仍为待核实草稿；不得把测试标注当作已识别或独立确认的现场设备。
