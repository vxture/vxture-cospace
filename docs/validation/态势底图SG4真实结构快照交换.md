# SG4 真实 IFC 结构声明快照交换

日期：2026-11-17。本增量将已接入工作台的真实 IFC 结构声明提供给独立消费端。协议与 synthetic 场景图、正式现场事实发布分别管理；没有修改旧发布，也没有部署。

## 业务入口与用途

在现有 IFC 构件资料的“结构声明”区域增加“导出声明”。只有目录提供结构声明并读取成功才出现，不为旧目录生成空成果。导出使用已登录会话和现有 `association.edit` 场景权限。

`GET /api/scene-ifc/structure-snapshot?space_id=…&catalog_sha256=…` 检查权限后，重新核验场景绑定、固定目录 SHA-256 和原 IFC 文件大小/摘要。非法参数 422、无权限 403、源变更或无结构声明 409。HEAD 支持相同摘要；POST 未开放。

HTTP 响应为下载文件，`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`；`X-Content-SHA256` 与下载文件名均包含准确原始字节摘要。固定来源未变时重复导出字节相同，不加入当前时间、临时 ID、用户名称或服务器路径。导出不加载网格、不创建发布、不改写 IFC、不登记观测，也不开放新的机器人服务凭证。

用途为资料交换、外部结构浏览、接入联调和应用语义关联的输入。当前文件不能回答“机器人能否通过”、执行导航或担保现场空间连接。

## 契约与逻辑拆分

协议 `cospace.ifc-structure-snapshot/0.1`，Schema 位于 `contracts/schemas/ifc-structure-snapshot-v0.1.schema.json`，运行校验位于 `packages/views/agent/ifc_structure_exchange.py`。

| 部分 | 表达 | 边界 |
|---|---|---|
| source | 场景、原目录摘要、IFC 摘要与字节数 | 固定来源，不包含源文件或服务器路径 |
| frame_id / unit | IFC 提取坐标标识及米制单位 | 不证明点云单位、重力或配准 |
| entities | GlobalId、目录元素编号、实际 IFC 类型、提取类别、名称、几何提取状态 | 只包含选定 IFC 类别；类别不是已绑定本体类型，名称不充当身份 |
| relations | 原关系 ID、类型、方向与两端 GlobalId | 组成、归属、开洞、填充、边界声明；不推断现场空间连接 |
| 标记 | ifc_design_candidate、unverified、selected_ifc_classes_only | geometry_included、alignment_verified、ontology_bound、real_release_ready 固定 false |

实体和元素编号唯一；关系引用闭合、不允许自环或重复元组。最多 10,000 实体、20,000 关系，文件最多 8 MiB；原 IFC 大小引用最多 128 MiB。未知字段拒绝。文件使用 UTF-8、固定字段、Python 排序键的紧凑 JSON；数值仅含有界整数，跨语言无需处理浮点摘要重编码差异。消费者核对准确字节与规范编码，拒绝重复 JSON 键、额外空白或不同编码形式。

`element_id` 只是固定目录内编号，不能跨目录继承对象身份。GlobalId 也只保留源 IFC 的身份声明，不能证明与现场资产或另一版本实例相同。本体关联仍由独立流程建立，不在导出时猜测。

## 两个独立消费者

Python 使用项目运行环境：

```text
python -m experiments.scripts.read_ifc_structure_snapshot <snapshot.json> <snapshot-sha256> <trusted-source.json>
```

Node 只使用 Node 内置库，不依赖 Python 或 npm 包：

```text
node examples/scene-graph/consumers/read-ifc-structure.mjs <snapshot.json> <snapshot-sha256> <trusted-source.json>
```

`trusted-source.json` 从可信配置或独立核对的来源记录取得，必须包含 space_id、catalog_sha256、ifc_sha256、ifc_bytes。文件摘要从可信导出响应或独立传递的摘要记录取得。把文件自身的 source 复制出来并不能建立信任；下载文件名和同次响应摘要有助于传输核对，但不替代可信传递、来源签名或第三方认证。协议当前无数字签名。

两个消费端都验证来源引用、字节摘要、规范编码、类型/预算、未核验标记、实体唯一和关系闭合。消费结果重算类别统计，始终返回 `original_ifc_content_verified=false`：离线消费者未取得并核验原 IFC，不能仅凭声明摘要声称重验过原文件。文件不含网格和连接端口，也没有完整对象覆盖保证。

## 实际验证与资料管理

本机 Anoeta 固定来源目录摘要 `26a55f65730271579f5a8b03826fbcd0665eaa3cdaa2b3c0770fdf5a41b874e3`；原 IFC 4,207,262 字节。导出 55,984 字节，SHA-256 为 `a6c6aa2b57acd067c60973c743615ce67acf7a3b8a5abcb19520623d34ae250c`。168 个实体、173 条关系；两种消费端统计完全一致，门 7、楼层 3、楼梯 2、楼梯段 6、开洞 59、墙 78、楼板 12、建筑 1；没有空间声明。

实跑作用域使用本机验证场景 ID，未修改生产绑定。快照和可信来源测试文件只留忽略目录 `output/sg4/anoeta-structure-exchange-01`，不进入 Git。合成测试检查确定性、摘要/来源错配、断裂关系、重复键、非法字段、权限先于读取、源文件变化、旧目录拒绝、独立消费端拒绝和 Schema 一致性。实际 IFC 测试是设计声明交换验证，不是现场态势验收。

## 批次状态

SG4 从“两个消费者只读合成资料”推进到“真实设计声明可经业务授权下载并独立消费”。真实现场事实快照、正式用途包与授权发布、生产容量和失败验收仍待完成。SG3 真实配准、区域边界和门两侧连接尚未核实；SG5 厂家上报与真实局部更新也没有由此自动完成。
