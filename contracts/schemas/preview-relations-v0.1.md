# 空间对象关系 v0.1

归属：定义 → 语义本体（规则）、空间关联（实例）。本阶段是固定规则下的人工关系声明，尚非OWL推理、SHACL、几何包含检测或机器人路径连通图。所有实例confirmation=unverified，quality=unverified，robot_ready=false。

## 1. 本体规则与版本

旧本体profile `cospace.preview-ontology/0.1`及其Schema不变。新profile `cospace.preview-ontology/0.2`继承旧类型和字符串规则，增加relations；结构见[本体0.2 Schema](preview-ontology-v0.2.schema.json)。内置关系词表 `configs/ontology/indoor-equipment-v0.2.json`使用同一ontology_id=indoor-equipment、独立version=0.2.0，未改写0.1.0。

每种关系以稳定type_id定义title、source_types、target_types、family和symmetric。端点类型必须存在，数组不重复；family为containment时symmetric=false，parent_endpoint明确source或target为父端；connection时symmetric=true、两端类型集合相同且无parent_endpoint。关系规则最多16种。关系规则版本记录增加relation_count，旧记录不补写。

| 关系ID | 方向与端点 | 约束 |
| --- | --- | --- |
| contains | 设备间/走廊 → 设备间/走廊/设备柜/巡检点 | 来源为父空间 |
| located_in | 设备间/走廊/设备柜/巡检点 → 设备间/走廊 | 目标为父空间 |
| connected_to | 设备间/走廊 ↔ 设备间/走廊 | 对称、无向去重；不表示通行许可 |

通用约束：端点须存在于同一固定对象集、匹配所选规则类型和方向，禁止自身关系和重复关系ID。包含与位于统一归一为parent→child，拒绝反向等价重复、同一child多个直接父空间及联合循环。连接按type_id及排序后的端点去重。不同语义类型的连接不自动合并。

这是首版受限规则配置：所有containment规则共用单父、无环政策，暂无可选基数表达式、跨空间端点、传递关系物化或关联冲突自动解决。多个对象指向同一父空间允许；没有关系不推断不存在关联。

## 2. 草稿校验与候选请求

`POST /api/ontologies/{id}/{version}/validate`继续兼容原objects请求，可额外提交relations数组（0至200项）。先检查1至100个对象草稿，再校验关系；附加relation_count，问题包含code、path、relation_id、object_id和message。只校验客户端提交的草稿，不保存、不绑定真实候选；saved=false。缺少关系规则的旧词表不能校验关系集，即使为空。

`POST /api/relation-candidates`严格请求见[实例Schema](preview-relations-v0.1.schema.json)：

```json
{
  "space_id": "space-0000000000000000",
  "base_candidate_id": "build-0000000000000000",
  "base_manifest_sha256": "实际model.json的64位SHA256",
  "ontology_ref": {"ontology_id": "indoor-equipment", "version": "0.2.0", "sha256": "实际固定规则的64位SHA256"},
  "relations": [
    {"relation_id": "cabinet-location-001", "type_id": "located_in", "source_id": "cabinet-001", "target_id": "room-001", "note": "人工声明，待现场核实"}
  ]
}
```

示例ID和摘要为占位，必须替换为实际引用。关系ID及端点ID为1至160字符的受限ASCII稳定标识；type_id最长64字符；note为1至500字符且不能全空白。最多200条；不接受客户端confirmation、自动发布或其他字段。

基础须为同空间、摘要匹配且完整的语义候选。可显式选择新的固定本体版本；全部原对象须仍符合新版本类型/属性规则。不做自动迁移或latest解析。服务端从固定基础重建同一对象及模型点锚点，并重新校验完整关系集。

relations是完整集合，`[]`表示新候选解除全部对象关系。生成不改变当前选择，不发布。页面要求先校验、再确认完整集合，候选生成时服务端仍重新校验。之后沿已有人工核对→选择→独立发布。

普通对象修订自动保留两端仍存在的关系；移除对象时移除其相关关系。改类型或换规则导致保留关系不合法时，整批拒绝，不能静默丢失关系。设备台账绑定独立保留，两者使用同一新对象快照摘要。

## 3. 固定快照

模型新增relations.json，profile=`cospace.preview-relations/0.1`，含model_id、space_id、project_id、objects_sha256、ontology_ref、relations及confirmation。每条关系为请求字段加confirmation=unverified。model.json新增object_relations={path:relations.json,relation_count:整数}；members声明字节摘要与大小。

读取验证文件完整性、模型ID、空间/项目、对象摘要、本体引用、计数及全部关系约束；孤立成员（有文件声明却没有object_relations）拒绝。发布封存完整成员，旧发布不读取最新规则或关系。

## 4. 查询、比较与离线包

含关系快照的对象查询profile=`cospace.preview-object-query/0.3`，沿用既有objects及可选business_links，并增加顶层relations。全部对象查询返回完整关系集；单对象查询仅返回与其相接的边，另一端对象可用稳定ID另行查询。空快照返回relations=[]；旧对象0.1/业务0.2响应不补关系字段，以区分未记录和已记录为空。

候选及固定发布比较新增relations：base_available、target_available、added、removed、modified；按relation_id比较完整记录，note变化也属修订。规则版本变化另列ontology变化。新人工核对摘要涵盖关系，历史保存核对记录不改写。

离线包profile=`cospace.preview-offline/0.4`，固定成员为package.json、publication.json、model.json、agent.npz、objects.json、ontology.json、relations.json；若有业务快照则另含business.json。发布、模型、成员、对象、规则及关系引用均检查。读取器兼容0.1/0.2/0.3；0.4不含完整几何，不能独立重算几何包含或模型点位置。

双视图从同一固定响应展示关系，可点击关联端点切换对象。没有运行时图搜索、路径下发或外部本体服务请求。

## 5. 错误与运行边界

请求结构错误422；关系候选规则失败422，detail含issues；固定基础/空间/摘要/规则缺失等错误409；Origin不允许403；服务未配置503。失败不产生新候选。草稿规则失败为200＋status=failed，旧本体没有关系规则为409 ontology_relations_not_available。

服务默认封存内置0.1.0和0.2.0两版规则；`--ontology-seed`可重复指定自定义固定文件，显式指定时仅封存所列文件，不自动加入默认源。已有库内规则保留。未接入真实身份/空间ACL或外部同步，记录和人工说明不是认证审批。
