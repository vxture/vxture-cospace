# SG3 首步：IFC 与点云的坐标对齐候选

本批将配准候选与 SG2 的 IFC 结构提取、独立本体映射分开。类型映射不参与求解，重新配准也不改写 IFC 原始身份、本体绑定或正式发布。当前仅实现已知对应点的刚体拟合与独立检查，不自动生成对应点，不应用到真实 IFC 网格，不推断空间连接。

## 输入与验收

`packages.construction.ifc_alignment.fit_ifc_alignment` 接受 `cospace.ifc-alignment-input/0.1`：IFC 和点云各自固定的米制 frame ID 和成果 SHA-256、检查误差上限，以及 6 至 256 组对应点。每组含 `id`、`evidence_ref`、`purpose`（fit / check）、`ifc_m` 和 `cloud_m` 两组三维坐标。调用方需从独立可信上下文提供预期两份成果引用，不能把请求本身当作来源核实。

至少 3 组不共线拟合点，以及另外至少 3 组不共线检查点。拟合使用不含比例、镜像的旋转与平移；检查点不参与拟合。结果给出 IFC → 点云的 4×4 矩阵，分别列出两组 RMSE 与最大误差。检查上限是调用方声明的验收条件，不是通用产品精度。超过上限给出失败诊断；低于上限也仅供人工复核，不证明对应点独立性、全场覆盖或正式发布可用。

真实操作时优先使用分布在场景不同角落和楼层的同名稳定特征点；检查点不重复使用拟合点，不在观察检查结果后用其反复调参。米制单位须先核实。若已有测绘变换与独立检查报告，可作为后续直接核验路线输入，本批尚未实现该导入路径。

## 数据现状

原 SUM4Re 目录只读核对：5 个 IFC、20 个 LAZ，未发现独立的配准报告、对应点表或平面图。已有 Anoeta HL2 局部化证明只解释点云坐标，不作为 IFC 对齐依据。Donor、Longyearbyen 的 IFC 地图转换声明可继续核对，但仅凭声明不能确认与相应点云处于同一基准。

需要进一步确认：

1. 首选 Anoeta 的点云与 IFC 对应点或已知变换、方向、单位和适用范围。有共同可辨识特征时，也可在双视图人工选点，原始点云不必重发。
2. 对齐后再核对房间和楼道边界、门所在开口的两侧空间和楼梯上下端。优先使用现有几何配合人工标注；有平面图可直接作为参考。
3. 配电柜进入样板时，补资产表、实景图或位置确认。不能把“柜体”类型提案当现场资产身份。

求解器使用合成输入验证，涵盖已知刚体变换、检查点超限、来源绑定、重复及退化控制点。未生成或采用真实场景配准结果。

## Anoeta 真实数据预检

在本地用已固定摘要的 Anoeta IFC 结构网格和 HL2 派生点云生成三视图：5,581 个网格三角面、16,948 个显示采样点。俯视图两侧均可见圆形主体连接长廊，足以确定后续三维复核的优先区域。各面板独立缩放，侧视图也会重叠不同深度的表面，不能以屏幕上的点、轮廓端点或包围盒直接充当三维对应点。点云米制单位仍需核实；未填写任何控制点。

复用命令：

```text
python -m experiments.scripts.ifc_control_review --ifc-root <目录> --cloud-root <目录> --ifc-sha256 <IFC目录摘要> --cloud-sha256 <PLY摘要> --output-dir <新输出目录>
```

其中 IFC 摘要指 `ifc.json` 文件的 SHA-256，点云摘要指 `cloud.ply` 的 SHA-256，使用已核对的外部记录。输出 SVG 和未对齐、空控制点工作表；工作表不是求解器输入。后续在原始三维视图确认连接处、廊道端部及具有高度差的稳定结构点，记录每侧原坐标 XYZ、特征描述和定位证据。分开记录拟合组与检查组，保留至少 3 组独立检查点；无法在两侧识别同一物理点时，舍弃该点。

## 三维选点与坐标单位核对

再次检查 Anoeta 五份 LAZ 文件头：均为 LAS 1.2，XYZ 量化步长均为 0.001，唯一 VLR 为 LASzip 压缩记录，未发现投影或单位记录。量化步长只决定解码数值精度；不能用来证明米制，也不能根据坐标范围倒推 EPSG。IFC 使用米，HL2 仍需原始导出设置、测绘说明或可追溯的尺度实测证据。

```text
python -m experiments.scripts.ifc_control_picker --ifc-root <目录> --cloud-root <目录> --ifc-sha256 <IFC目录摘要> --cloud-sha256 <PLY摘要> --output <新HTML文件>
```

生成的 HTML 可离线打开。Anoeta 显示 27,904 个结构三角面及 42,370 个原始点样本（总计 254,219，按 6 点步长取样），原坐标不变。点击两侧顶点与样本、描述共同特征并指定用途后，导出未核验工作表。IFC 记录实体 GlobalId 和原网格顶点索引，点云记录原 PLY 顶点索引，索引均从 0 起。线框和投影点的深度会重叠，必须换角度核对选点；若采样没有覆盖具体特征，应先回看完整点云。浏览器工作表保留原始候选；经人工确认物理对应、组间独立性和米制单位后再整理为求解输入。本次没有生成实测控制点或配准矩阵。

## 复核工作表到求解候选

`experiments.scripts.ifc_reviewed_alignment` 补齐离线工作表与求解器之间的核验环节。保留浏览器工作表的未核验标记，通过独立复核记录声明单位依据与逐点证据，不允许直接将工作表布尔值改为已核验。

复核记录结构如下（摘要与证据 ID 仅为结构示意，必须替换；controls 覆盖工作表所有点）：

```json
{
  "profile": "cospace.ifc-control-review-record/0.1",
  "worksheet_sha256": "<工作表规范化内容的SHA-256>",
  "reviewer": "reviewer-id",
  "unit_evidence": {"id": "survey-unit-report", "sha256": "<单位依据文件SHA-256>"},
  "controls": [
    {"control_id": "control-1", "evidence": {"id": "landmark-1", "sha256": "<该点复核证据SHA-256>"}}
  ]
}
```

工作表摘要使用 `packages.spatial.scene_identity.content_digest`（JSON 键排序、无额外空白、UTF-8）计算，不是原始 JSON 文件字节的摘要。证据应保留可识别同一物理位置的三维定位记录；检查点在求解前固定，不在看到误差后改作拟合点。复核记录与工作表一起保存在本地证据目录，不提交原始现场数据或身份信息。

```text
python -m experiments.scripts.ifc_reviewed_alignment --worksheet <工作表.json> --review <复核记录.json> --ifc-root <IFC目录> --cloud-root <点云目录> --ifc-sha256 <已核对目录摘要> --cloud-sha256 <已核对PLY摘要> --max-check-error-m <本次检查阈值> --output <新候选.json>
```

程序重新读取固定来源，逐点比对 GlobalId、网格顶点索引、PLY 顶点索引和原始坐标，拒绝改写坐标、未知实体、越界索引、过期工作表复核及缺项记录。然后调用同一刚体求解器，沿用独立检查点及退化几何检查。输出保留复核记录及其摘要；证据文件内容没有被程序读取或认证，`evidence_content_verified`、`control_evidence_verified`、`alignment_verified` 和正式可用标记始终为 false。声明证据摘要不能替代实际复核，也不构成线上审批机制。

当前进展：离线工具链已可用，合成验证通过；Anoeta 的单位依据及真实对应点证据仍缺失，未生成真实候选。后续应先完成这些资料，再核对误差、覆盖范围和结构一致性，不能直接进入正式成果采用。

## IFC 原坐标中的结构复核清单

配准依据待补时，可独立在 IFC 自身坐标系整理空间结构证据，不必停下所有 SG3 工作。`experiments.scripts.ifc_structure_review` 从固定来源生成门和楼梯的复核任务，重验目录、原 IFC 和所引用网格摘要；只列显式源关系，不根据名称、本体映射、包围盒相邻或楼层编号生成空间连接。

```text
python -m experiments.scripts.ifc_structure_review --ifc-root <IFC目录> --ifc-sha256 <已核对目录摘要> --output <新结构复核清单.json>
```

2026-11-17 已用 Anoeta 原生结构目录实际生成 9 项任务：

| 原始声明 | 核对结果 | 尚缺内容 |
|---|---|---|
| 7 个 IfcDoor | 每扇门都有 fills → IfcOpeningElement → opening_in → IfcWall 路径，门、开口及宿主墙均有网格 | 两侧空间边界与端口；现场是否仍一致 |
| 2 个 IfcStair | 整体无独立网格；每部均聚合 3 个 IfcStairFlight 和 2 个 IfcSlab，子构件均有网格 | 平台接口、上下端所在空间与楼层的逐项确认 |
| 3 个 IfcBuildingStorey | 保留声明名称和来源身份，没有楼层独立网格 | 不能把名称中的数字或单一 contained_in 关系当作楼梯两端楼层 |
| 0 个 IfcSpace | 明确标缺少空间声明，任务端点保持空列表 | 房间、楼道区域边界，后续再独立关联本体类型 |

输出中的 `index_bounds_m` 只是已读取网格的索引范围，不能作为净开口尺寸、房间边界或通行能力。所有任务为 pending/unverified；`confirmed_connections` 为空，未与点云对齐，未生成正式空间实例或连接。复核清单是本地工作资料，不是 SG0 synthetic 图，也不是线上发布协议。

## 空间边界和端点标注

在原 IFC 坐标下填写 2.5D 区域和门、楼梯端点。工具每次从固定 IFC 来源重建复核清单，工作表与清单内容摘要绑定；旧清单上的工作表不能静默用于新修订。

```text
python -m experiments.scripts.ifc_spatial_annotation --ifc-root <IFC目录> --ifc-sha256 <已核对目录摘要> --output <新工作表.json>
python -m experiments.scripts.ifc_spatial_annotation --ifc-root <IFC目录> --ifc-sha256 <已核对目录摘要> --worksheet <已填写工作表.json> --output <新检查报告.json>
```

1. 在 `evidence` 登记定位图或复核记录的 ID、SHA-256。证据文件另行保存在本地。
2. 在 `areas` 填区域 ID、名称、IFC 楼层 GlobalId（`level_id`）、不重复首点的平面边界 `footprint_xy_m`、高度区间 `z_range_m` 和 `evidence_ids`。只支持单环边界及统一高度区间，复杂区域不要用外包矩形代替。区域 ID 是工作表的局部标识；本体类型与正式实例身份独立处理。
3. 在对应 `connections` 任务中写 `endpoints`、`evidence_ids`。每端填 `role`、`area_id`、`point_xyz_m`。门端点用 `side_a` / `side_b`（不代表通行方向），楼梯用 `lower` / `upper`。有一侧证据时可以只填一侧，待核实的端点留空。

校验拒绝过期绑定、悬空引用、退化或自交边界、点落在所填区域外及楼梯上下倒置。完整只表示两个端点和引用均已填写且内部一致；工具不认证证据内容，也不判断端点是否确实位于对应门洞或楼梯接口、面积有无重叠或是否与现场一致。确认这些内容仍需人工核对。输出不包含已确认连接，不生成现场状态或设备通行规则。

Anoeta 真实来源已通过空表生成和回读：0 个已填区域、9 个待标注任务。真实填写优先选一扇门，标注两侧可辨识区域；再选一部楼梯，核对上下端标高与所属区域。需要可现场核实的原坐标标注、平面图或定位记录，点云无需重发。
