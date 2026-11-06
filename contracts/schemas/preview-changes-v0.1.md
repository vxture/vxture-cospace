# 候选更新比较与人工核对 v0.1

工作面归属：空间关联编辑对象；构建中心比较与确认候选；态势服务另行发布。当前仅针对本机内部预览，不包含现场变化识别或生产审签。

## 请求

`POST /api/candidate-comparisons`只生成比较结果，不保存候选选择或发布：

```json
{"space_id":"space-example","candidate_id":"build-target","expected_revision":3}
```

基准是该空间当前所选候选，不自动改用最近固定发布；首次选择时base_ref为null。不同空间及未关联历史范围不可混用。请求禁止额外字段，序号为非负严格整数，不接受布尔值。

`POST /api/candidate-reviews`提交人工核对并选择目标候选：

```json
{"space_id":"space-example","candidate_id":"build-target","expected_revision":3,"comparison_sha256":"0000000000000000000000000000000000000000000000000000000000000000","acknowledge_unverified":true,"note":"说明本次修改和核对依据"}
```

摘要必须使用实际比较响应；上例全零仅展示字段。note去除首尾空白后须非空，最多500字；acknowledge_unverified必须明确为true。请求Schema见[JSON Schema](preview-changes-v0.1.schema.json)，严格输入校验由Pydantic执行。JSON数值在Schema中无法区分整数表示1与1.0，运行时仍执行严格整数检查。

## 比较响应

profile：`cospace.preview-candidate-comparison/0.1`。

| 字段 | 定义 |
| --- | --- |
| space_id / project_id | 明确空间归属；历史未关联响应不包含这两项 |
| selection_revision | 本次比较的所选版本序号 |
| base_ref / target_ref | candidate_id与model_manifest_sha256；基准可为null |
| coordinate | same_frame核对frame_id、axes、unit声明相同；same_resolution核对网格尺寸；不进行配准 |
| geometry.same_source_model | spatial.npz摘要相同；字节相同而非几何等价判定 |
| geometry.base_surface_cells / target_surface_cells | 两版本表面单元数 |
| geometry.cell_comparison | comparable，或坐标/分辨率变化导致不可比较 |
| geometry.added_surface / removed_surface | 可比较时给数量、前20个排序单元样例及cell_bounds_m；不可比较为null |
| geometry.unlisted_state | 固定unknown；移除表面证据不表示空闲 |
| ontology | 两方固定本体引用及changed标识；未带本体时引用为null |
| objects | 新增、移除、修改、未变数量及两方是否有标注快照 |
| dual_view_impact | 人视图采用目标几何/对象快照，智能体视图采用目标表面/对象快照；非画面差异计算 |
| comparison_scope | 仅基于坐标声明比较，不代表独立配准或现场变化检测 |
| review_allowed | 坐标声明和分辨率兼容；不是质量通过标志 |
| comparison_sha256 | 不含本字段的整个响应的规范JSON SHA256 |
| quality / robot_ready | 固定unverified / false |

摘要规范：UTF-8、ensure_ascii=false、键排序、无多余空白、拒绝NaN，以Python `json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)`编码。不含生成时钟，绑定空间序号、双方模型及实际内容。客户端原样提交服务端摘要，不重建算法以避免数字编码差异。

单元比较按索引集合差，最多500,000单元/候选，分别取差后排序。cell_bounds_m为差异单元覆盖的米制包围盒，不是对象包围盒、精确变化轮廓或完整观测范围；无差异为null。坐标或分辨率不同则不生成单元集合差，也禁止通过本核对路径直接选择。

对象以稳定object_id匹配：新增/移除给完整固定对象；修改给fields、before、after。fields覆盖type_id、properties、anchor_m、evidence和confirmation。属性是完整字典比较，不是RFC 6902补丁。对象移除表示该版本不再包含此标注，不证明设备被拆除。缺少语义快照明确标为不可用，不能称现场无对象。本体引用变化单独报告，稳定ID不等于语义含义自动兼容。

## 确认与记录

提交时先重新生成比较；序号或比较摘要变化则拒绝。选择锁内再次读取双方完整快照并核对比较内容，随后使用已有原子选择指针流程提交。确认只改变该空间所选候选，仍须人工单独发布。

成功选择新增selection_review：完整comparison、note、acknowledge_unverified、reviewed_at、reviewer和purpose。reviewer固定为local_engineer_unverified_identity，当前未接入真实身份，不能作为生产审签人。purpose明确仅为预览候选选择。选择历史及当前指针保存记录，新固定发布将其原样保存至publication.json；离线包继续沿用0.1/0.2，将携带该发布记录。

旧候选、旧发布、原始资料不改写。旧选择及发布没有核对记录时不补造。兼容工程API `/api/selection`仍保留，可能产生未记录核对的选择；本批统一Web入口走核对路径，不声称后端所有路径均强制审签。发布也不以该预览记录替代精度或权限验收。

## 拒绝与限制

- 输入无效422；不允许Origin为403；服务未配置503。
- selection_changed_refresh_required：空间所选序号变化。
- comparison_changed_refresh_required：双方摘要/内容或所核对差异变化。
- coordinate_or_resolution_review_blocked：坐标/网格声明不兼容。
- manual_review_acknowledgement_required：未明确知悉限制或说明为空。
- 模型/成员/本体绑定损坏、跨空间引用沿用校验失败409。

修改或失败后重新读取、重新填写依据并确认，不自动重试或合并。当前无自动配准、变化检测、三方合并、现场确认、多角色审签或待审任务队列。全部对象仍待核实。


F3新增独立relations差异（按稳定relation_id的added/removed/modified及两方是否有快照），新核对摘要覆盖关系；旧已保存报告不补写。见[关系契约](preview-relations-v0.1.md)。
