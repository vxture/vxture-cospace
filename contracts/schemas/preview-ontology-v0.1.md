# 本机本体版本工作面契约 v0.1

本文件保留B1原类型规则边界。后续F3新增兼容的独立profile0.2关系词表、可选关系草稿校验和固定实例，见[空间对象关系契约](preview-relations-v0.1.md)；旧0.1规则不增加关系。

B1使用[JSON Schema](preview-ontology-v0.1.schema.json)定义人工维护的小型规则包。`ontology_id + version + sha256`共同构成固定引用，sha256是UTF-8原始文件字节摘要。类型和属性使用稳定ID；中文名称是显示内容。当前仅实现字符串属性、必填、长度及未定义属性拒绝，不宣称支持OWL、SHACL、关系、单位、继承或行业标准映射。

规则源位于 `configs/ontology`。服务启动时将指定规则包原文及摘要封存到运行目录 `preview-ontologies/{ontology_id}/{version}`。同ID和版本只允许相同字节；变更必须使用新版本。旧版本保持原样，不按latest引用规则。读取时重新校验原文摘要、字节数、结构及ID/版本。

| 接口 | 行为 |
| --- | --- |
| GET `/api/ontologies` | 返回已封存规则版本及摘要、标题、类型数量；没有版本时明确为空 |
| GET `/api/ontologies/{id}/{version}?sha256=...` | 按固定引用读取规则原文的JSON内容及完整性信息；摘要必填 |
| POST `/api/ontologies/{id}/{version}/validate` | 请求含sha256和1至100个objects；只校验草稿，不保存对象或绑定空间 |

校验草稿对象字段为 `object_id`、`type_id`、`properties`。不接受其他字段冒充确认结果、位置或证据。错误逐项返回code、JSON Pointer path、object_id和message；未知类型不自动映射到近似类型，重复对象ID、缺失属性、未定义属性及值类型/长度错误均失败。

返回 `status=passed|failed`、`checked_at`、固定本体引用、object_count及issues。passed只代表规则检查通过，`saved=false`、`semantic_confirmation=not_attempted`、`robot_ready=false`，不代表对象属于任何真实模型或已由人工确认。当前NYU固定发布仍无语义对象，不为旧发布自动附加本体。B2在人工对象、证据及模型快照中固定引用此规则。

未知版本404，原文完整性失败或引用摘要不匹配409，未配置规则库503，请求结构错误422；失败时页面清除旧规则/结论，不显示为合格或空库。版本列表及校验不提供任意文件路径读取或在线编辑接口。
