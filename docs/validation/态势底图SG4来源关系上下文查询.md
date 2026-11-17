# SG4 来源关系上下文查询

日期：2026-11-17。应用按坐标定位到构件后，需要进一步读取“它是什么，与哪些来源对象有关”。本增量对固定 IFC 结构声明提供有界关系邻域查询，Python 与只用内置库的 Node 消费端独立实现；既可使用单独下载的结构快照，也可读取离线包内的原始 structure.json 字节。没有新增服务端点、修改资料包格式或部署。

## 接入

宿主先取得可信结构摘要和 source pin。结构摘要必须对应实际字节，不能解析再自行序列化后冒用原摘要；从离线包读取时须先核验整包，使用已核验清单中的 structure_sha256 与外部可信 source。包自身声明不能建立独立信任。

```python
from packages.views.agent.ifc_declaration_context import query_declaration_context
result = query_declaration_context(
    structure_raw, expected_sha256=trusted_structure_sha256, expected_source=trusted_source,
    query={"element_id": hit["element_id"], "max_hops": 2})
```

```javascript
import {queryDeclarationContext} from './examples/scene-graph/consumers/query-ifc-context.mjs';
const result = queryDeclarationContext(structureBytes, {
  sha256: trustedStructureSha256, source: trustedSource
}, {element_id: hit.element_id, max_hops: 2});
```

hit 必须来自相同固定来源；使用其他版本的目录元素编号不能自动关联。返回 subject.entity_id 可与原命中 entity_id 再核对。离线包调用时，structure_raw / structureBytes 分别是已校验 loaded['members']['structure.json'] / loaded.members.get('structure.json')。本查询本身不读取网格、原 IFC、NPZ、文件路径或网络。

请求 Schema：`contracts/schemas/ifc-declaration-context-request-v0.1.schema.json`。element_id 必填，为 e 加五位数字；max_hops 默认 1，允许 1–4；relation_kinds 默认五类全部，允许显式非空且无重复的筛选列表。拒绝额外字段、不存在的元素和非法查询，不将错误当作空邻域。

## 原关系语义与查询范围

| kind | 原始方向 | 不代表 |
|---|---|---|
| aggregates | 整体 → 组成部分 | 所有组成关系都是空间包含 |
| contained_in | 被归属对象 → 所属空间结构 | 几何上已核实包含或传递归属成立 |
| opening_in | 开口 → 宿主构件 | 门两侧房间已确认 |
| fills | 填充构件 → 开口 | 当前开门、可通过 |
| space_boundary | 空间 → 边界构件 | 该边界有可用连接 |

为了查看相关资料，邻域沿所选来源关系双向展开；返回关系仍保留原始 kind、source_id、target_id 和 ifc_relation_id。hop_distance 是来源关系的最少跳数，不是米制距离、通行步数或空间归属等级。多种关系不能混作一种传递包含或空间连接。

返回 profile `cospace.ifc-declaration-context/0.1`，固定来源、结构摘要和规范化查询，附 subject、带 hop_distance 的实体、所选实体间全部符合筛选的原关系，以及 boundary_entity_ids / has_more。实体和关系保持固定快照内原有顺序；边界两端均已入选的原关系也会保留，不只返回遍历树。

边界实体是在当前筛选关系内仍连接到未选实体的对象。has_more=false 只表示当前筛选的来源关系邻域无外部引用，不表示现场物体、空间连接、完整 IFC 类别或其他关系已被完整覆盖。无关系的合法对象仍返回自身及空关系，不是失败。环路和多父声明原样保留，不替用户选择一棵“正确”的树，也不替代事实核对。

## 校验、预算与事实归属

先校验完整固定结构快照的字节、来源、规范编码、未核验标记、实体唯一、关系引用与预算，再执行查询。沿用 8 MiB、10,000 实体、20,000 关系上限；每次最多选中 512 实体、2,048 关系，超过则抛出错误，不返回截断结果或静默省略分支。当前构建临时邻接索引，无跨请求缓存，未做生产并发/最大预算内存承诺。

输出始终为 ifc_design_candidate / unverified；original_ifc_content_verified、geometry_included、alignment_verified、ontology_bound、real_release_ready 均 false。IFC 设计声明、本体映射、现场采用和动态观测继续分开：此接口不读取门状态、不生成空间端口、不声明机器人可达、不进行本体绑定。源身份与结构摘要的核对不能代替现场事实验收。

## 验证

两套现有固定资料各查询：门一层、门两层、楼梯段一层、楼层一层、上轮离线坐标命中构件两层；十组 Python / Node 结果逐字段一致，重复 Python 查询一致。未写入原 IFC、目录、正式快照或生产配置。

| 样本 | 门一层 实体/关系 | 门两层 实体/关系 | 楼梯段一层 | 楼层一层 | 坐标命中两层 |
|---|---:|---:|---:|---:|---:|
| Anoeta | 3 / 2 | 32 / 32 | 2 / 1 | 31 / 30 | 65 / 64 |
| Longyearbyen | 3 / 2 | 54 / 54 | 2 / 1 | 53 / 52 | 53 / 52 |

上述十组均有边界实体，正确提示仍可继续查来源关系；不能据这些数量认定现场有相同数量的房间或连接。原始结果留忽略目录 `output/sg4/declaration-context-01`。合成回归覆盖五种原关系方向、过滤、边界和诱导边、孤立对象、环路/多父、身份/摘要/来源错配、断裂引用、非法提升标记、重复 JSON、查询及结果预算、Node 稀疏数组/原型字段拒绝。

SG4 的设计资料消费链路由“坐标 → 构件”延伸到“构件 → 来源关系上下文”。SG3 真实单位/配准和空间连接核验、SG4 正式事实发布、SG5 厂家身份与上报仍独立验收；本功能不将它们标为完成。

新增上下文查询 27 项专项通过，相关既有回归 55 项通过、1 项因 Windows 创建符号链接权限跳过；仓库护栏与 ruleset 检查通过。
