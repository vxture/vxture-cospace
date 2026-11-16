# SG2：真实 IFC 结构候选提取

SG2 复用隔离 IfcOpenShell 和现有 IFC 几何检查器。新增候选部分从同一次原生解析读取实体 GlobalId、实际 IFC 类、结构角色、几何目录引用和明确声明的关系，不调用点云配准、不写入场景或发布。外部 IFC、目录和网格只放忽略的本地输出。

结构子清单为 `cospace.ifc-structure-candidate/0.1`，嵌入 `ifc.json`，继承其原 IFC SHA-256、米制局部世界坐标和网格摘要。支持建筑、楼层、空间、门、楼梯/梯段、洞口、墙、楼板和专用类型配电柜。几何引用指向 IFC 产品目录；有引用不一定有网格，必须检查 geometry_status。

| 关系 | 方向 |
|---|---|
| aggregates | 整体 → 部件，如建筑 → 楼层、楼梯 → 梯段 |
| contained_in | 构件 → 声明归属空间 |
| opening_in | 洞口 → 被开洞构件 |
| fills | 门等填充构件 → 洞口 |
| space_boundary | 空间 → 其声明的边界构件 |

关系保留原 IFC 关系 GlobalId，仅保留本批选中类型的端点。同一个关系可产生多条边。没有空间端点或边界声明时不合成门两侧连接，也不以楼梯所在层猜测另一层。候选仍标为设计资料、未核实，不是现场事实或设备通行结论。

| 样本 | 结构实体 | IFC 声明关系 | 结构实体网格 | 缺少显式类型 |
|---|---:|---:|---:|---|
| Anoeta | 168（3 楼层、7 门、2 楼梯） | 173 | 162 有网格、6 无表示 | IfcSpace、IfcElectricDistributionBoard |
| Longyearbyen | 157（2 楼层、22 门、3 楼梯） | 176 | 151 有网格、6 无表示 | 同上 |

两份资料均已核对原文件与报告中的来源摘要、目录摘要、选中实体的网格长度与摘要。Longyearbyen 全产品目录另有 2 项网格提取失败，均不在本批的结构实体中。两份目录均明确 alignment_verified=false。源文件未修改。

从仓库根目录重跑（使用未占用的 run ID）：

```powershell
$env:COSPACE_SCENE_INPUT_ROOT='D:/Work Space/SampleSpace/激光点云数据集/sum4re'
uv sync --project experiments/ifc-tool --frozen --no-build
experiments/ifc-tool/.venv/Scripts/python.exe -m experiments.scripts.inspect_ifc_structure Anoeta/Anoeta.ifc anoeta-native-02
experiments/ifc-tool/.venv/Scripts/python.exe -m pytest -q tests/test_ifc_native.py
```

SG3 优先核实点云与 IFC 的对应点或可靠坐标变换，以及房间/楼道边界（可由平面图、几何标注或现场复核补足）。配电柜若进入样板，再补其资产引用、可识别图像或位置确认。没有这些依据时仍可独立浏览 IFC 结构候选，不升级为已对齐的真实态势底图。

## 独立本体映射

SG2 增加 `packages.ontology.ifc_mapping.propose_ifc_types`。它读取固定摘要的原始 IFC 目录和已指定的本体定义，校验本体 ID、版本、摘要与显式类型规则；输出绑定三者的独立提案。只按原 IFC 类精确匹配，未配置的类保留为未映射。旧结构目录不变，既不补造本体类型，也不映射关系、核验实例必填属性或发布。

现有设备间词表不能充当通用建筑结构本体。用于真实场景前，应选用或补齐已核对的建筑结构词表，并按用途配置映射；IfcSpace 不直接归为设备间。空间关系的本体映射与现场实例核验是独立工作。

本机以临时词表和单条 IfcDoor → 门规则对照两份固定目录：Anoeta 7 条提案、161 项未映射；Longyearbyen 22 条提案、135 项未映射。输出独立保存于忽略目录，未登记本体或采用实例。专项 10 项通过，包含原 IFC GlobalId 的美元符号、版本/摘要不符、重复规则、未定义目标和歧义 JSON 等边界。
