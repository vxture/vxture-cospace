# 合成空间图契约 0.1（SG0）

状态：实验性、仅 synthetic。依据：[ADR-006](../../docs/decisions/ADR-006-态势底图与设备决策边界.md)。

[JSON Schema](synthetic-scene-graph-v0.1.schema.json) 与 `packages/spatial/scene_graph.py` 的严格模型通过一致性测试约束。Schema 检查字段结构；专用校验器再检查引用、类型、关系和时间。只执行 JSON Schema 验证不等于完成契约检查，尤其不能证明空间事实真实。

## 内容与约束

根字段：profile、data_kind、scene_id、snapshot_id、frame、ontology、evidence、sources、entities、geometry、relations、connections、observations。profile 固定 `cospace.synthetic-scene-graph/0.1`，data_kind 固定 synthetic；所有层级拒绝额外字段。

- 单一局部米制坐标，轴向为 right_forward_up；不提供变换树，不允许混入其他 frame。
- 实体：稳定 ID、类型、名称、正整数修订、几何/证据引用；声明 unverified。
- 几何：AABB 是 approximate_bounds，point 是 reference_point，rectangle 是 connection_port。矩形检查非退化、正交与顶点顺序；不证明与房间表面真实相接。
- 所有坐标有限，绝对值不超过 1,000,000 m；文档读取上限 2 MiB，集合数量受 Schema 预算限制。
- contains 仅约束指定空间归属族的单直接父；part_of 独立约束物理组成且无环；adjacent_to 不产生开口连接。
- 连接必须有 door/stair 对应构件、两个不同 space 端点，以及归属该构件的两个不同矩形端口；连接语义仅结构事实。
- opening_state 观测只能引用 door 角色和已声明合成来源；完整 UTC 时间、失效晚于观测、接收不早于观测。晚到且已过期的记录可以保存，不自动充当当前状态。
- 校验报告始终 evidence_verified=false、geometry_verified=false、real_release_ready=false、robot_ready=false。

严格模型不接受布尔值充当数值，也不接受 1.0 充当修订整数；通用 JSON Schema 对 integer 的数学解释可能接受 1.0，因此消费应执行专用校验。SG0 内嵌词表只是测试角色映射，不是正式生产本体。

## 读取

从仓库根目录运行：

```powershell
.venv/Scripts/python.exe -m experiments.scripts.inspect_scene_graph examples/scene-graph/two-level.synthetic.json --entity cabinet --connections-for corridor-l1
```

CLI 只读，输出校验报告、对象和结构连接，成功退出 0，非法输入或查找失败退出 2。拒绝重复 JSON 键和超预算文档。它不是平台 API，不绕过现有身份授权，没有导入、发布或修改生产数据的能力。

CLI 输入限制在仓库 `examples/scene-graph` 内的 JSON，解析真实路径后检查目录边界，不允许 `../` 或相似前缀目录越界。库调用可由可信装配代码显式指定独立根目录。IFC 盘点 CLI 则要求本机事先配置 `COSPACE_SCENE_INPUT_ROOT`，只读其范围内的 `.ifc`，没有配置时拒绝读取；不以 CLI 输入路径本身作为信任根。

`SceneGraphReader` 固定内部副本，返回副本防止调用方改写快照；不保证签名信任、原始观测、几何精度或真实身份。实体未找到与非空间对象作为连接查询参数分别报错。

## 兼容与后续

旧点锚可以将来显式适配为 reference_point，但当前没有旧格式自动升级。身份拆分/合并、旧点锚映射、真实证据、精细网格、范围查询、状态决议和组件分发属于后续批次。Schema 出现可表达的 point 不等于旧对象适配器已经交付。

fixture：[两层合成图](../../examples/scene-graph/two-level.synthetic.json)；生成函数：`experiments.scripts.scene_graph_sample.sample`。样例尺寸和名称全部虚构，不来自用户数据。
