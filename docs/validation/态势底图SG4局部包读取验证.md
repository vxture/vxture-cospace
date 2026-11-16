# SG4 前置：固定局部包只读消费

日期：2026-11-17。主批次仍为 SG4；本次只落实消费端读取与失败语义，不包含在线服务、授权路由或真实发布。SG3 仍缺单位、对应点及真实空间连接依据，不能用合成包替代验收。

## 已实现

`SceneSubsetReader` 复用 SG1 的组件摘要、依赖、引用和来源绑定校验，读取后固定内存快照。支持按类型列实体、读取实体及其几何/包内关系/原始观测、查询指定空间或连接构件的结构连接。结果按 ID 排序；当前返回完整的有界包内集合，不实现分页或空间几何查询。输入、上下文和返回结果相互隔离，调用方修改字典不会改变已固定读取内容。

每次构造都必须由调用方独立提供预期来源三元组（scene_id、snapshot_id、内容摘要）。只从待验证包复制 manifest.source 并不能建立来源信任。仓库的 `source-ref.synthetic.json` 是随合成源样例固定的演示引用；实际应用需要从已授权、可信的固定发布上下文取得引用，本次没有实现该生产信任链。

只验局部包能够证明内部引用与成员字节自洽，不能证明裁剪忠实。可额外传完整源文档，与确定性裁剪结果逐项比较；即使攻击者删除连接后重新计算成员摘要，完整源对照仍拒绝。摘要不是签名，来源对照也不把合成内容升级为真实事实。

## 查询语义

| 结果/标志 | 含义 |
|---|---|
| found | 包内有匹配记录，仍保留 unverified 状态 |
| no_match | 该包内没有匹配记录，不表示整个场景不存在 |
| out_of_scope | 指定实体不在该包中，不能据此宣布它被删除或不存在 |
| query_scope=package_only | 所有查询只覆盖当前包；full_scene_coverage 恒为 false |
| incident_connections_complete=true | 已对照完整来源，且查询实体属于原始 requested_ids，一跳关联连接齐全 |
| incident_connections_complete=false | 未对照完整源、查询对象只作为依赖附带，或对象在包外；不能当完整邻接表 |
| observation_resolution=not_applied | 返回原始观测，不计算当前状态、时效优先级或冲突消解 |

一层楼道样例包含两个结构连接：一层门和跨层楼梯。二层楼道作为楼梯端点依赖附带，仅带楼梯连接，不递归带入二层门。即使整包已通过完整源对照，查询二层楼道仍明确 `incident_connections_complete=false`。门的 closed 观测不会删除结构连接，也不会产生设备通行结论。

## 首个独立消费入口

命令行输入限制在显式 `--input-root` 内，拒绝越界、超额及重复 JSON 键。包上限 4 MiB，完整源 2 MiB，预期来源文件 4 KiB；输入错误退出码为 2，不自动联网获取其他场景或依赖。

从仓库根目录执行：

```text
python -m experiments.scripts.consume_scene_subset --input-root examples/scene-graph --package examples/scene-graph/sg1/corridor-subset.synthetic.json --expected-source examples/scene-graph/source-ref.synthetic.json --source-document examples/scene-graph/two-level.synthetic.json --connections-for corridor-l1
```

将最后参数改为 `--entity door-l1` 可读取门的几何表达与原始观测，改为 `--type corridor` 可列出包内楼道。省略 `--source-document` 时保留包内校验，但不能声明原始选择范围的连接完整性。CLI 不写入场景、成果或发布。

## 验证与后续

自动检查覆盖：请求对象与依赖对象的完整性区别、关闭门仍保留连接、返回结果与输入突变隔离、错误预期来源、损坏组件、伪装 real、重新计算摘要后的恶意省略、非法查询 ID、越界/超额/重复键及仓库样例引用一致性。

SG4 剩余：真实快照契约与接入、在线/离线授权和发布边界、只读概要界面、第二个独立消费例及性能/故障验收。SG5 的识别、状态解析和持续更新不在本次范围。
