# 独立本体模块与目录契约 v0.1

日期：2026-11-20。首批只读草案契约。实现源：`packages/ontology/kernel/catalog.py`；前端契约：`packages/ontology-ui/src/contract.ts`。与旧 `cospace.preview-ontology/0.1`、`0.2` 独立，不可提交给旧编制/封存接口。

## 载体

- `vxture.ontology-module/0.1`：单个模块定义。
- `vxture.ontology-library/0.1`：`{profile, modules}`，可移植导出/导入载体。
- `vxture.ontology-catalog/0.1`：只读展示响应，含 `status=draft`、`library_sha256`、`capabilities` 和 `{reference, definition}` 模块列表。

本版全部定义仅允许 draft，不宣称正式发布、现场适用或专业审核。导出库不携带 CoSpace 的用户、工作空间、园区、模型、路径、实例或认证状态。

## 模块

必需字段：`profile`、`module_id`、`version`、`title`、`description`、`layer=core|domain`、`status=draft`、`requires`、`concepts`、`relations`。未知字段拒绝。ID 限小写英文字母开头及字母/数字/下划线/短横线，最多 64 字符；版本为三段各 1–4 位非负整数。

依赖是精确 `{module_id, version, sha256}`，摘要为该模块按内核 `canonical_bytes` 编码的 SHA-256。库中每个模块 ID 只出现一个版本。核心不可依赖领域，依赖无环，传递闭包必须完整。未导入的模块不得被概念或关系引用。

概念字段：`title`、`definition`、`examples`、`counterexamples`、`properties`，可选 `parent`，引用格式 `module_id:local_id`。本版支持单继承，继承无环，不允许覆盖继承属性。标题不是身份。

属性字段：`title`、`definition`、`data_type=string|number|integer|boolean`、`required`；可选 `unit`、`quantity`、`minimum`。单位与量种必须同时出现且属性为数值类型；最小值必须是有限数值。单位在本版为有明确解释的声明字符串，不执行单位换算或跨单位等价判定。

关系字段：`title`、`definition`、`source_types`、`target_types`、`symmetric`。端点必须是可解析概念且列表不重复；对称关系两端类型集合相同。此处只校验定义，不执行实例的单父、无环、时态或多端连接规则。

## 字节、预算与错误

库输入最多 1 MiB、32 模块；每模块最多 256 概念/256 关系，每概念最多 32 本级属性，示例与反例各 1–8 项。解析拒绝重复键、非有限数值及未知必需语义。文本长度等细节以内核检查为准。

`canonical_bytes` 是本 profile 的 UTF-8、键排序、无空格 JSON 编码，禁止 NaN/Infinity，不是 RFC 8785 声明。模块摘要针对规范编码，库摘要针对模块按 ID 排序后的库载体，均不等同原文件字节摘要。摘要检查不是签名或现场真实性证明。

纯内核 `CatalogError` 返回 code/path；CLI 只向 stderr 输出安全诊断，失败退出 1。库导出返回副本，可独立重新解析，不写运行状态。

## CoSpace 宿主接口

`GET|HEAD /api/ontology-library`：沿用平台会话、中央会话有效性及宿主权益门禁；无额外场景权限要求，定义是同一共享草案。不接收 query。未认证 401，无权/不支持的方法按现有默认拒绝 403，非法 query 422，定义或依赖不可取得/损坏 503。响应 `Cache-Control: no-store`。

该路径只返回随产品安装的共享定义，不访问私有 Workspace 规则，不开放写入、发布或实例保存。独立产品可通过其他 transport 装配同一内核；该路径不是内核依赖。
