# 本体资源目录与归组契约 v0.1

日期：2026-11-20。状态：首批内置草案集已实现。

## 资源和配置边界

资源分组定义由配置管理维护。资源归组由本体业务维护，不修改本体语义、版本或 SHA256。核心接受 root、scope、actor 和已校验定义集，不读取 CoSpace、身份平台、场景或 HTTP。CoSpace 注入基于 issuer / org / workspace 的可信作用域。

首批 8 个本体：通用核心 core，以及 built_environment、outdoor、electrical、water、fire_safety、monitoring、operations 七个领域本体。领域本体默认关联对应 preset-* 分组，通用核心默认未归组。默认关联采用按需初始值；首次显式保存后以业务记录为准，清空归组不会被默认值重新填回，不覆盖后续用户修改。定义内容仍为草案。

配置与归组是不同对象、表和接口。目前共用一个 SQLite 事务边界，保证分组启停与归组有效性校验串行生效；未来存储适配应保留这一一致性要求。

## HTTP

- GET /api/ontology-resources：layer（空 / core / domain）、q（最长 160）、group（空 / ungrouped / group_id）、sort（title / id）、page（起始 1）、page_size（1–50，默认 10）、snapshot（可选）。未知、重复参数拒绝。服务端返回摘要、分组元数据、总数和分页；不返回完整语义定义或配置审计。
- GET /api/ontology-resources/definition：必须提供 module_id、version、sha256。按固定引用返回该模块及依赖闭包；引用失效拒绝，不静默替换成新版本。
- POST /api/ontology-resources/membership：request_id（32 位十六进制）、module_id、expected_revision、group_ids（最多 100、不重复）。允许多组或空数组；actor、scope 不接受客户端传入。

摘要包含 reference、title、description、layer、status、concept_count、relation_count、revision、group_ids。响应 profile 为 vxture.ontology-directory/0.1；groups 包含 group_id、name、status。can_group 由宿主授权得出。

普通已授权产品用户可查询公共草案目录和本作用域分组元数据。首批归组写权限映射 workspace_manager，沿用宿主 CSRF、会话和订阅边界；后续可接独立业务权限，不改变核心归组模型。

snapshot 绑定目录摘要、配置修订和归组修订。后续分页必须回传快照；发生变更返回 409，重新查询首批页面。排序以名称或标识、模块标识为稳定次键，当前名称按 Unicode 字符顺序。前端保留过滤和页码直到离开当前分类；浏览器整页刷新恢复默认筛选。

幂等重试绑定操作者和规范化载荷；相同 request_id 不重复写入，冲突返回 409。每个本体独立 revision 做并发保护。停用分组允许保留和移出已有关系，禁止新加入。事务保留变更审计，业务页面不展示修改记录。

## 当前规模

服务端分页接口已与完整定义读取分离。当前数据源仍是有上限的内置定义集，服务端遍历该集合，分组元数据一次返回；没有宣称海量注册库性能。大规模阶段需检索索引、分组按需查询、持久化版本仓库和游标查询。当前不开放本体编制或发布。
