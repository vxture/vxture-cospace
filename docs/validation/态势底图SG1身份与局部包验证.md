# 态势底图 SG1 验证：身份、旧点锚与局部包

依据：[实施计划](../architecture/态势底图实施批次与数据清单-v0.1.md)、[交换契约](../../contracts/schemas/scene-sg1-v0.1.md)。本批使用合成样例，不上传、迁移或改写已有场景数据。真实数据的下一步是 SG2：在现有地址解析 IFC 构件与关系，提取未对齐空间候选；不会从缺失的 IfcSpace 或类型自动补造房间、楼道、配电柜。

执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_scene_sg1.py tests/test_scene_graph.py tests/test_preview_objects.py tests/test_preview_relations.py tests/test_partitioned_preview.py -q
```

关键检查：拆分/合并/未决提案与前后快照绑定，拒绝端点重复、越界、修订倒退或沿用已退役端点；旧点锚保留坐标和身份但无空间范围；局部包拒绝坏引用和组件依赖，区分只验包与对照完整源。重算被篡改组件的摘要只能得到自洽包，源对照仍拒绝。三份新 Schema 与严格模型保持一致，样例可从生成函数复现。

本机新增 47 项检查，连同 SG0、既有对象、关系与分区读取共 165 项通过。

局部样例选取一层楼道，额外附带一层门、相连房间、楼梯和二层楼道。二层楼道是依赖，不继续展开二层门。结构连接与状态保留为两类数据，未引入设备通行结论。
