# SG4 离线设计资料包的坐标查询

日期：2026-11-17。补齐应用离线消费环节：宿主取得固定设计资料包后，可在没有 CoSpace 服务、原 IFC、原 NPZ 或 Python 服务进程的条件下，按 IFC 坐标查询最近构件表面。Python 与 Node 分别实现消费路径，不修改现有 HTTP 查询、资料包格式或生产配置。

## 接入与返回

宿主先完成下载授权、有界读取，独立取得可信的整包 SHA-256 与 source pin。包内自带的摘要和 source 不能自行建立信任；本版本没有数字签名。每次查询校验完整资料包，损坏的非命中组件也不能跳过。Python 仅依赖已有包解析器及几何计算；Node 仅使用内置库，独立计算距离，无 Python 或 CoSpace 服务调用。

```python
from packages.views.agent.ifc_offline_surface import query_package_surface
result = query_package_surface(
    raw, expected_sha256=trusted_sha256, expected_source=trusted_source,
    query={"frame_id": trusted_frame_id, "point_xyz_m": [1., 2., 3.], "max_distance_m": 1.})
```

```javascript
import {queryPackageSurface} from './examples/scene-graph/consumers/query-ifc-package.mjs';
const result = queryPackageSurface(rawBuffer, {sha256: trustedSha256, source: trustedSource}, {
  frame_id: trustedFrameId, point_xyz_m: [1, 2, 3], max_distance_m: 1
});
```

查询 Schema 为 `contracts/schemas/ifc-offline-nearest-surface-request-v0.1.schema.json`。三个字段必须齐全，不接受额外字段。坐标为三项有限数值，各轴绝对值不超过 1,000,000 米；半径大于 0、最多 1,000 米。frame_id 必须严格等于包内固定 IFC 坐标系。禁止将点云、设备定位或其他地图坐标直接传入而不核实变换。

结果 profile 为 `cospace.ifc-offline-nearest-surface/0.1`，固定整包与结构摘要、来源、查询条件和覆盖计数。`found` 返回 entity_id、element_id、IFC 类型、名称、原网格摘要、几何组件摘要、原三角形序号、最近点和无符号距离。距离恰好等于半径时仍命中；无匹配为 `no_match`，完全没有已提取几何为 `geometry_unavailable`，两者 match 均为 null。错误抛出异常，不伪装为无匹配。

算法完整遍历所有已提取结构网格的三角面；面内使用垂足，面外使用线段，零面积面退化为边或点。不是最近顶点或包围盒查询。完全等距时按最低构件编号、最低原三角形序号取一个结果；它不是唯一空间归属。浮点误差可能影响极近距离的排序，不承诺任意接近等距情形的跨语言逐位一致。

## 完整性与计算预算

沿用资料包 32 MiB、512 组件、每组件 200,000 顶点 / 400,000 三角形及成员完整性限制；额外限制整次查询最多 400,000 三角形，超限在距离计算前拒绝，不静默抽样或漏查。该额外预算在完整包验证后执行，不代表超限包不会被解析。两个组件各 200,001 个三角形的回归证明：单成员合法时仍拒绝超过总预算的查询。

当前每次调用重新校验完整包、再逐成员读取数组进行距离计算，优先保持一致校验边界，没有常驻索引、批量查询或缓存。宿主需自行限制调用频率；最大预算下的内存、并发和延迟尚未生产验收。

离线输出始终保留 `ifc_design_candidate`、`unverified`、`original_ifc_content_verified=false`、`original_mesh_content_verified=false`、`alignment_verified=false`、`ontology_bound=false` 和 `real_release_ready=false`。包与成员摘要通过只证明固定字节和声明绑定，未在离线端重新核验原文件，也不证明发布者身份、现场准确性或资料完整覆盖。

## 现有资料验证

复用先前固定资料包，未覆盖原数据或生产资料。两套来源各验证原网格顶点、顶点附近偏移和远处坐标；Python 离线、Node 离线及现有服务端查询在六组情况下状态、实体、原三角形、来源网格、最近点与距离一致（浮点比较容差 1e-8）。原顶点距离为 0，远处均无匹配，重复原顶点查询返回一致结果。

| 样本 | 查询覆盖网格 / 三角形 | 无几何实体 | 本机 Python 每次查询耗时 |
|---|---:|---:|---:|
| Anoeta | 162 / 28,788 | 6 | 约 877–933 ms |
| Longyearbyen | 151 / 32,808 | 6 | 约 781–835 ms |

耗时包含重复包校验、组件解码与遍历，Windows 本机单次测量，不包含下载、真实会话或网络；不是生产性能承诺。原始结果仅留忽略目录 `output/sg4/offline-surface-01`，包摘要与[离线资料包记录](态势底图SG4离线设计资料包.md)一致。

回归覆盖离线与服务端一致、删除原文件仍可查询、半径边界、面/边/点、退化三角形、等距构件与三角形、缺失几何、错误坐标系/来源/摘要、非命中组件损坏、非法和非有限数值、总计算预算。

## 业务边界

应用得到的是“此坐标靠近哪个设计构件及其表面”，不能由此推断所在房间、封闭占据、碰撞、实时门状态、可通行性或路线。机器人结合自身条件与经核实的空间资料作出行动决策。SG3 现场对齐与连接核验、SG4 正式事实发布和生产验收、SG5 真实来源上报仍独立完成，不因离线查询通过而标记完成。

本轮新增离线查询 30 项专项通过，既有资料包与服务端查询 41 项回归通过；仓库护栏和 ruleset 检查通过。

应用可以进一步使用[来源关系上下文查询](态势底图SG4来源关系上下文查询.md)，从相同固定结构快照读取构件及原始相关声明；保留原关系方向，不推断现场归属或连接。
