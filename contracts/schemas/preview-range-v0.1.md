# 固定预览发布的智能体范围查询 v0.1

本契约是D1小型真实样本的只读查询能力；[JSON Schema](preview-range-v0.1.schema.json)定义请求和固定发布响应的结构，以下语义检查仍由共享实现执行。现有点查询、对象查询及离线包0.1/0.2保持兼容。

## 请求与选择规则

`POST /publications/{publication_id}/api/query-range`：

```json
{
  "bounds_m": [[-4.45, -0.25, 0.94], [-3.94, 0.26, 1.45]],
  "frame_id": "os1_16/os_sensor",
  "limit": 1024
}
```

调用者必须知道固定发布的坐标系，frame_id必须完全匹配；不做隐式坐标变换。bounds_m是二维数组，依次为最小XYZ和最大XYZ，单位米。六个坐标必须有限、绝对值不超过1,000,000，每轴最小值严格小于最大值。数字字符串和布尔值拒绝。limit须为严格整数，1～4096，省略时1024；未知字段拒绝。输入/坐标系错误HTTP 422；固定发布绑定或成员核对失败沿用HTTP 409。

对整数单元索引 `(i,j,k)` 和分辨率r，中心为 `((i+0.5)r,(j+0.5)r,(k+0.5)r)`。只选择中心在 `[min,max)` 半开包围盒内的单元；不表示整个体素被包围盒包含，也不表示体素与包围盒相交的全部单元。该接口不是碰撞检测或导航净空裁剪。

边界计算采用输入数字与分辨率的十进制声明，转换为整数索引边界，避免负数与0.1分辨率的浮点边界偏移。不枚举未知体素；只扫描已有表面单元。返回按X、Y、Z升序排列，无重复、无随机抽样、无分页游标。

## 响应与上限

响应profile为 `cospace.preview-range/0.1`，包含固定publication_id、publication_model_manifest_sha256、model_id、source_model_sha256、frame_id及已有空间/项目归属，另含请求范围、分辨率、实际limit和max_limit。

| 字段 | 完整返回 | 数量超限 |
| --- | --- | --- |
| status | complete | limit_exceeded |
| result_complete | true | false |
| matched_cells | 范围内实际匹配数量 | 实际匹配数量，不是抽样估计 |
| returned_cells | 等于matched_cells | 0 |
| cell_indices | 全部匹配单元，数量不超过limit | 空数组，不返回前N个 |
| unlisted_state | unknown | null，不提供缺失单元判断 |
| action | none | shrink_bounds_or_increase_limit_within_max |

超限仍为HTTP 200的明确业务结果，调用者必须检查status与result_complete，再消费单元。不能从超限空数组得出“没有障碍物”或“没有表面”的结论。缩小范围或在4096以内提高limit后重查；相邻范围按同一中心规则可拼接，本批不提供自动分块调度。

范围内匹配0个单元且result_complete=true时，表示此次枚举完成、没有表面证据；未列出位置仍为unknown。result_complete只说明**固定表面证据枚举完整**，不是空间观测完整度或质量等级。cell_state统一为surface_candidate，coverage为surface_evidence_only，quality保持unverified，robot_ready保持false。没有自由空间、已确认占据、ESDF距离或机器人运行授权。

数组长度/returned_cells/matched_cells/limit之间的关系、坐标顺序和固定来源摘要关联属于语义约束，不能只依赖JSON Schema结构校验。旧未关联记录可能没有空间/项目字段；不得猜测归属。

## 在线与离线

`PreviewModel.query_range(bounds_m,frame_id,limit=1024)`与`OfflinePreview.query_range(...)`复用同一选择实现。离线读取器先验证既有包与固定发布身份，再返回与HTTP相同的结果及版本绑定。无须下载图片、人视图或完整空间点云；离线包内容、profile与摘要不因新增读取能力而改变。

CLI新增与point/objects/object-id互斥的模式：

```powershell
.venv/Scripts/python.exe -m experiments.scripts.query_preview_offline PACKAGE.zip --publication PUBLICATION_ID --sha256 PACKAGE_SHA256 --bounds -4.45 -0.25 0.94 -3.94 0.26 1.45 --frame-id os1_16/os_sensor --limit 1024
```

`--frame-id`为bounds模式必填，`--limit`只用于bounds。CLI输出相同JSON，完整返回退出码0、超限退出码3、输入/完整性错误退出码2。输出空结果本身不能替代退出码及result_complete判断。

本批没有可信时间、数据新鲜度证明、签名授权、持久消费引用或分块流式传输；固定预览不能据此提升为机器人可运行地图。
