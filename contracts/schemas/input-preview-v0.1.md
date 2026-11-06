# 资料与构建阶段显示抽样 v0.1

P17 实现，配套 `input-preview-v0.1.schema.json` 与 `build-preview-v0.1.schema.json`。

## 入口与授权

- `GET /api/inputs/{id}/preview?space_id=…`：`data.manage`，资料和场景归属必须一致；首版仅 PLY。先授权，后解码。
- `GET /api/build-preview?space_id=…&candidate_id=…&kind=model|human|agent`：`build.run`，候选、固定模型来源及场景归属一致。
- 固定模型已冻结即可查看；某类视图仅在其独立任务成功、产物摘要核验通过后可查看，不等待另一类视图。历史一体任务没有固定模型记录时不可用。
- GET/HEAD 只读；不得 poll、启动、重试、组合、选定或发布任务。POST 不开放。参数必须精确匹配，不接受路径、变换或可调预算。

能力接口 `/api/input-uploads?space_id=…` 增加可选 `input_preview`：profile 为 `cospace.input-preview/0.1`，formats 为 `['ply_pointcloud']`，max_points 为 10000。旧服务缺少声明时前端不请求资料几何。

## 绑定和几何

共同字段：明确 profile、space_id、input_id、source_sha256、米制声明及局部 frame_id/axes、appearance、quality=`unverified`、robot_ready=`false`、limitations。

资料响应另含 format=`ply_pointcloud`、snapshot_sha256；source_sha256 为原 cloud.ply 摘要。每次严格重读 PLY、坐标清单及可选来源收据，核对固定登记。

阶段响应另含 job_id、kind、manifest_sha256、task_id。source_sha256 为固定 spatial.npz 摘要；manifest_sha256 为 frozen.json 摘要；model 的 task_id 为 null，其他为独立视图任务 ID。人视图先核验真实 PLY 产物及任务，再显示其同源固定点与颜色；智能体显示实际 agent.npz 的观测表面单元中心 `(cell+0.5)*resolution_m`，其余空间未知。

`point_count` 是完整点／单元数，`bounds=[minXYZ,maxXYZ]` 从全量计算。`sampling` 为 file_index_stride，limit=10000，stride=max(1,ceil(point_count/10000))，count=ceil(point_count/stride)。points/colors 均为 count 个三元组，点必须有限且位于完整 bounds，颜色为 0—255 整数。客户端除 Schema 结构外必须检查这些跨字段约束和当前记录摘要。数组用于显示，不用于构建或判定精度。

固定最多 10000 显示点、JSON 编码后最多 2MiB；本机 PLY 原始预算仍为 32MiB／100 万点。坐标不变换；绘制中心偏移和相机朝向仅用于显示。本机未知单位在用户确认前不标为米。

## 异常与存储

401 未登录，403 无权或跨场景，422 多余／不合法查询。409 的 detail 为 `input_preview_format_unsupported`、`input_preview_evidence_unavailable`、`build_preview_invalid_request`、`build_preview_stage_not_ready`、`build_preview_evidence_unavailable` 或 `preview_response_budget`。客户端清除旧画面并可重试；渲染不可用仍显示数值并保留原业务操作。

响应 Cache-Control: no-store；不保存预览实体或缓存，不暴露本机路径，不创建批次、预检、构建、审核、选择或发布。已固定模型不依赖原资料继续存在；固定模型本身变化则拒绝显示。
