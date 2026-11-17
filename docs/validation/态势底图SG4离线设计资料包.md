# SG4 离线设计资料包

日期：2026-11-17。将结构声明及其全部已提取构件网格放进一个固定、可独立校验的下载单元。复用既有结构和几何协议，没有创建现场事实快照、正式发布或机器人通行规则；未部署。

## 业务入口与调用

IFC 构件资料 → 结构声明 → “下载资料包”。仅在结构读取成功时显示，下载当前固定目录版本。单独的声明和构件网格导出继续用于小范围读取。资料包不包含原 IFC、点云、服务器路径、本体映射提案或实时观测，不混合不同的核验状态。

`GET /api/scene-ifc/design-package?space_id=…&catalog_sha256=…`，支持 HEAD。沿用 `association.edit` 场景权限，鉴权先于文件读取。服务端先验证绑定、固定目录和原 IFC，检查所有几何的预算，再逐个核对 NPZ 摘要、成员预算、数组与范围。构建后再次核对来源/配置，变化则拒绝整包。下载成功不改变构建、发布、实例采用或本体状态。

响应 `application/octet-stream`、`no-store`、`nosniff`；准确 SHA-256 在下载文件名及 `X-Content-SHA256`。非法请求 422、未授权 401/403、来源/几何损坏、缺失或超预算 409；不静默生成缺少网格的“完整”包。HEAD 仍执行完整生成和核验，无正文，不承诺低成本。没有 POST，不接受路径、任意成员列表或客户端给定来源。

本轮导出在内存完成，不创建服务器临时包、不缓存结果。没有跨存储事务快照；固定摘要保证成员内容，并在完成前重验原来源。后续下载若原资料已变更会拒绝。源文件在完成核验后被更改不会改变已经返回的包字节，但也不代表来源签名或永久可追溯存储已建成。

## 包格式

`cospace.ifc-design-package/0.1` 为简单顺序容器，避免 ZIP 解压路径及压缩炸弹：

| 顺序 | 字节内容 |
|---|---|
| 8 字节 | ASCII `CSIFCP01` |
| 4 字节 | uint32 小端，后续清单字节数 |
| 清单 | UTF-8 排序键、紧凑规范 JSON，最多 1 MiB |
| 成员载荷 | 按清单顺序拼接准确成员字节，无间隙或尾部数据 |

清单 Schema：`contracts/schemas/ifc-design-package-v0.1.schema.json`。固定 source、准确结构快照摘要、geometry_coverage、成员名/字节数/SHA-256。候选、未核验、未对齐、未绑定本体、不可作为真实发布的标记固定不变。

首成员必须是 `structure.json`，使用既有结构声明快照；后续严格按构件编号排序，名称为 `eNNNNN.bin`，使用既有构件几何协议。必须恰好覆盖结构中所有 geometry_status=extracted 的实体，不能缺失、多出、重复或替换身份。no_representation/extraction_failed 的实体保留在声明中，不伪造网格；这不代表原 IFC 全部类别或现场物体已覆盖。

整包最多 32 MiB、512 个几何组件；清单每成员最多 10 MiB，实际结构消费者另限 8 MiB。每网格仍最多 200,000 顶点、400,000 三角形。导出预检使用保守的清单/头空间上界，可能拒绝接近边界但实际略小的包，不静默截断。消费者先验证整包和布局、再逐成员验证结构和几何。字节预算限制输入，Python/Node 读取仍有复制和解析开销；未验证最大预算下并发峰值内存，不作生产容量承诺。

## 消费者接入

宿主从可信下载或独立记录取得准确包摘要及 source pin。把包自身 source 复制出来不建立信任。当前没有数字签名。

Python：

```python
from packages.views.agent.ifc_offline_package import read_design_package
loaded = read_design_package(raw, expected_sha256=trusted_sha256, expected_source=trusted_source)
summary = loaded['summary']
structure = loaded['structure']
geometry_bytes = loaded['members']['e00001.bin']  # 实际编号须来自结构声明
```

Node（只依赖内置库）：

```javascript
import {readPackage} from './examples/scene-graph/consumers/read-ifc-package.mjs';
const loaded = readPackage(rawBuffer, {sha256: trustedSha256, source: trustedSource});
const structure = loaded.structure;
const geometryBytes = loaded.members.get('e00001.bin');
```

两端返回完整验证后的清单、结构、成员字节及概要，宿主可用既有 `inspect_geometry_component` / `readGeometry` 进一步取得选中网格数组。概要接口为 `inspect_design_package` / `inspectPackage`。没有文件解压和任意路径访问；宿主负责有界读取、下载授权及展示。包内门状态或本体结果不可被推断，因为包没有这些组件。

消费端核对整体与成员字节、规范清单、来源、成员闭合、构件对应、坐标/数量及三角索引。几何在 IFC 米制坐标；不证明点云单位或对齐，不代表封闭占据实体。original_ifc_content_verified 和 original_mesh_content_verified 为 false，表示离线端未取得原 IFC/NPZ 重验，不能仅凭声明摘要提升。

## 真实资料实跑

本机验证场景，原 IFC、目录和生产配置未修改。两套来源均重复导出字节一致，Python 与 Node 对全部组件校验及概要一致：

| 样本 | 字节 | 结构实体 / 关系 | 网格 / 无几何 | 顶点 / 三角形 |
|---|---:|---:|---:|---:|
| Anoeta | 906,576 | 168 / 173 | 162 / 6 | 14,966 / 28,788 |
| Longyearbyen | 992,398 | 157 / 176 | 151 / 6 | 17,022 / 32,808 |

Anoeta 包 SHA-256 `5d6d83991d97f8655c544ccc5a7798dbeec10311b28203ed0e73fb8dd36b2b62`；Longyearbyen `952011d8b05dc8afcb15fc3a46b91623ce1496d3776cb869a7722b0ef6f0ee52`。本机单次导出分别约 1.76 s、1.57 s，Python 完整校验约 409 ms、378 ms；包含本机存储/摘要及既有校验路径，使用测试目录读取适配器，排除真实会话、场景授权和网络，不是生产延迟验收。每个几何重复核验固定结构，当前优先复用一致校验逻辑，后续性能优化需保持相同边界。

原始包、绑定配置及报告只留忽略目录 `output/sg4/ifc-offline-package-01`。合成回归覆盖固定摘要、权限先于读取、完整性、缺失/多余/重复/改序/路径成员、伪造发布标记、重复清单键、越界三角索引、预算先于几何加载及批次中原 IFC 变化。

## 验收状态

SG4 具备真实设计资料的一次性离线分发与两个独立消费者，不等于已核实现场底图或正式用途发布。SG3 仍需实测对齐、区域和连接证据；SG4 正式发布生命周期及生产性能、SG5 厂家观测和真实变化仍独立验收。资料包不包含实际设备导航或作业规则。

资料包消费后可进一步使用[离线坐标查询](态势底图SG4离线坐标查询.md)，Python / Node 独立执行最近三角表面查询；不改变资料包格式和设计候选边界。
