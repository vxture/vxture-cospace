# Ontology

语义本体平台模块，负责类型、属性、关系、单位、约束、外部类型映射及本体版本。现场实例及几何锚定归spatial，外部资产主数据归原系统。

发布本体不可覆盖；真值固定引用本体版本及摘要，视图与服务继承该解释。本体升级须评估实例迁移，不能静默修改历史真值。固定快照支持离线校验与解释。

`validation.py` 是早期小型词表校验；后续 `preview_relations.py`、`ifc_mapping.py`、`workspace_authoring.py` 已分别提供受限关系、IFC 类型提案和 Workspace 编制能力。通用单位、完整映射及迁移尚未实现，不预先选定 RDF/OWL、图数据库或推理引擎。详细计划见[平台规划](../../docs/architecture/数据管理与语义本体平台规划-v0.1.md)。

`preview_versions.py`提供B1本机规则版本封存、按ID/版本/SHA256读取及可定位的草稿校验；工作台语义本体页已连接。规则源位于 `configs/ontology`，固定副本保存在运行目录的 `preview-ontologies`。该模块不调用合成实例的confirmation规则，也不创建现场对象或修改已有模型。见[本体工作面契约](../../contracts/schemas/preview-ontology-v0.1.md)。

2026-11-20 独立产品首批：新增 [kernel](kernel/README.md)，可独立打包为 `vxture-ontology`，运行时不依赖父目录旧代码、CoSpace 或第三方库；UI 位于独立包 [ontology-ui](../ontology-ui/README.md)。内置核心/领域候选定义和依赖校验，公共资源目录可读取及导出。全部为草案，不替换旧正式规则或实例链路。产品边界见 [ADR-007](../../docs/decisions/ADR-007-语义本体独立产品边界.md)。

2026-11-20 信息架构修订：业务资源与系统配置分开，分组体系管理归配置管理，资源归组及语义约束归本体业务。导航不按本体或分组数据增长，查看/编辑/发布是对象操作。后续以[业务与配置边界及导航框架](../../docs/architecture/语义本体业务与配置边界及导航框架-v0.1.md)为实施依据；该文为设计，不表示配置与发布功能已落地。

2026-11-20 园区实施 B01：按[五批任务](../../docs/architecture/园区本体实施批次与任务-v0.1.md)推进。首批新增建筑空间范围、管理范围、入驻与设施职责指派及资产记录，当前 8 模块、42 概念、19 关系；全部为候选草案。三类园区能力问题见仓库 `examples/ontology/park-competency-questions.json`，结果见 [B01 验证](../../docs/validation/园区本体-B01-2026-11-20.md)。

2026-11-20 园区实施 B03：独立内核增加纯实例校验 API 与 CLI，执行 B02 实例契约和显式选用的候选园区规则；3 个正例通过、23 个反例实际拒绝。见 [B03 验证](../../docs/validation/园区本体-B03-2026-11-20.md)与[报告契约](../../contracts/schemas/ontology-instance-report-v0.1.md)。不增加现场实例库、宿主授权或事实核实职责。

2026-11-20 园区实施 B04a：新增独立编制服务和可替换事务存储端口，落地草稿、固定审批快照、不可变发布与精确历史版本读取；SQLite 参考适配器位于纯内核之外。见[编制契约](../../contracts/schemas/ontology-authoring-v0.1.md)和[B04a 验证](../../docs/validation/园区本体-B04a-2026-11-20.md)。HTTP 与业务表单接入仍待 B04b，第四批整体未完成。

2026-11-20 B04b 增量：已接通可信宿主 HTTP、现有模块业务编辑表单、送审快照、双人审批、不可变发布和历史依赖读取；第四批首版工程范围完成。见 [B04b 验证](../../docs/validation/园区本体-B04b-2026-11-20.md)。当前仍为候选定义的治理，不宣称专业审核通过；下一批进入消费侧实例与态势地图接入。
