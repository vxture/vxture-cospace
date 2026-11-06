# 预览构建重试接口 v0.1

`POST /api/build-retries`，同源请求、有效平台会话与CSRF。需要原场景的 `build.run` 以及原资料的 `data.manage` 权限；以服务端保存的任务和资料归属为准。

请求：

```json
{"space_id":"space-…","retry_of":"build-…","request_id":"0123456789abcdef0123456789abcdef"}
```

只允许上述字段；`request_id` 为32位小写十六进制。同一场景内，同一请求ID与父任务对应一个已受理的新任务，跨并发和服务重启保持。若同请求ID指向不同父任务则409。200表示找回已受理记录，202表示本次创建；响应均为 `{"created": true或false, "job": 已保存任务记录}`。

新任务增加 `retry_of`、`retry_request_id`，保留原 `input_binding` 和 `batch_ref`。仅原任务为 `failed` 或 `interrupted` 且属于现有RGB-D／单帧激光几何路线时允许。新准入重新检查输入摘要和状态，以及原批次ID和原准入修订；不得自动使用新修订。旧请求的重放只找回既有记录，不再发起新构建，也不自动选择／发布该记录。

业务拒绝返回409及既有资料、生命周期或批次错误码；本接口将文件不可读错误归为 `retry_input_file_unavailable`，不返回文件路径。格式422、未登录401、无权或CSRF失败403；服务未装配503。客户端在网络／服务异常后使用原请求ID核对 `GET /api/builds?space_id=…`，按 `retry_of` 与 `retry_request_id` 找回记录；未找到只能沿用同请求ID重发。

这是现有本机预览任务契约的增补，未改变固定模型或发布格式，也不支持语义／业务／关系派生任务重试。
