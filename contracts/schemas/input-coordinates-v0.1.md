# 同资料坐标说明修订 0.1

P20实现。场景内资料ID保持不变，原始清单、来源收据与点云字节保持固定；有效坐标说明通过内部修订保存。接口依附原资料详情，不创建新的资料条目。

## 适用范围与权限

首批支持附带有效`source.json`、`basis=user_declared_file`的严格PLY。允许修改`frame_id`、三轴语义`axes`、`scope=sensor_local|scene_local`。`unit=m`、`scene_alignment=unverified`固定。修改说明不执行单位换算、坐标变换或配准，也不证明场景对齐或精度。

认证服务入口由Workspace／场景归属和`data.manage`授权；操作者取服务端身份，客户端不能提交actor。请求遵循现有会话、Origin与CSRF规则。查看者无权编辑。

## 读取与保存

`GET /api/inputs/{input_id}/coordinates?space_id={space_id}`

返回`cospace.input-coordinates/0.1`，含`input_id`、`space_id`、`supported`、`revision`、当前`coordinates`和`history`。无修改时revision为0。非当前支持格式返回supported=false，界面不显示编辑入口。无历史的只读请求不创建修订数据库。

`POST /api/inputs/{input_id}/coordinates`

请求结构见[JSON Schema](input-coordinate-change-v0.1.schema.json)：

```json
{
  "space_id": "space-0004d0e3c133f5fb",
  "expected_revision": 0,
  "request_id": "f36cf64876a14d55a7d28ac203e72fc42",
  "coordinates": {
    "unit": "m",
    "frame_id": "os1_16/corrected_local",
    "axes": ["sensor_x", "sensor_y", "sensor_z"],
    "scope": "sensor_local",
    "scene_alignment": "unverified"
  },
  "reason": "修正局部坐标系标识，保持原始点云数值"
}
```

修订必须匹配，原因去空白后非空；三轴为不同的有效标识。重复的同一request_id与相同请求返回当前状态，不追加事件；同一request_id内容变化或旧修订冲突返回409。不改变说明的保存不产生新修订。保存需要资料可用，且重新验证原文件。

历史事件含前后值、修订、服务端actor、UTC changed_at、原因、原始清单／点云摘要、请求摘要及事件摘要。读取校验连续修订和前后值，损坏时停止使用。事件存于`preview-inputs/input-coordinates.sqlite3`；这是本机追加审计记录，不是签名或外部防篡改存储。

## 贯穿处理流程的绑定

1. 资料列表、预览和事实展示当前有效说明；列表仍只有一个input_id。
2. 旧预检与新有效修订不匹配，须重新预检；旧封存批次保留原成员指纹，不能直接准入当前修订。新修订通过新的明确批次封存引用进入构建。
3. 构建请求`input_revision`显式确认当前修订，修订过的资料须有匹配且通过的保存预检；不匹配时拒绝。
4. 每个job/model的`input_binding.coordinate_revision`冻结本次有效说明及事件。旧任务不读取当前说明替换其固定输入；列表提示历史任务需重建才能采用当前修订。
5. `source_receipt.coordinates`继续表达最初文件接入时的收据；模型顶层坐标字段和冻结`input_binding`表达本次实际解释。两者可不同，不得把最初收据误认为模型当前解释。读取模型前先验证原始文件，再验证冻结修订与来源摘要。
6. 同原点云、仅说明修订且几何摘要一致时，允许人工核对新候选；不跨不同坐标语义宣称物理变化。其他坐标不一致仍阻断直接几何比较。
7. 固定发布、双视图与离线包携带模型当时的修订。离线消费不联网取最新说明，也不自动切换版本。

历史修订可用于核对旧来源和旧封存记录；新构建准入始终核对当前有效修订。重复上传原包复用原始身份，不因有效说明已修改而新增资料卡片。

## 错误与边界

请求字段非法422；无认证401；场景／角色不允许403；目标不存在404；修订冲突、停用、原文件变化或说明非法409；审计库不可读503。接口响应不缓存。保存不自动构建、选择候选、发布或退役；后续动作按既有权限分别执行。
