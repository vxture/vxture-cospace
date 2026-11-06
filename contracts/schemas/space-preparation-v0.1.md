# 空间构建准备与预检记录 v0.1

授权工作台沿用 `GET /api/workflow?space_id=...`，增加可选 `input_id` 和 `batch_id`（批次要求明确资料），用于明确跟进某份已登记资料；不自动选择最新登记，不改变当前候选或发布。只有本空间 `data.manage` 可以指定input并读取`preparation`；查看者仍可读已有成果参考流程，但不获取工程准备记录。每个操作的`allowed`根据当前空间能力计算，仅用于界面指引，接口自身仍逐请求授权。

## 保存预检

- `POST /api/inputs/{id}/preflight`：要求资料所属空间的`data.manage`、Origin和CSRF。执行原有完整文件预检，并将结果追加到独立`preflight-records.sqlite3`。actor取已验签身份；checked_at为UTC。
- `GET /api/inputs/{id}/preflight`：相同数据读取权限，返回`last_check`或null，`current_files_checked=false`；不读取原始源文件。

原预检字段保留，保存记录增加`actor`、全局递增`sequence`和规范化完整登记记录的`registration_sha256`。读取增加`registration_matches`。最新失败覆盖页面上的旧通过结论；登记记录变化时标为不匹配，不能借用旧结果。执行前后登记指纹不同时拒绝保存并返回409。原登记记录不改写；文件可能在检查结束后变化，因此结果不代表当前文件状态。

缺失/损坏的预检库区分：不存在表示尚无历史；库损坏503，不当作未检查。暂不可用的可选适配器503，不记录伪造失败结果。保存使用SQLite事务和追加序列，顺序代表记录提交顺序，不声称多进程同时检查的严格现场时间顺序。

## 构建准备字段

`preparation`包含：

| 字段 | 含义 |
| --- | --- |
| source_revision / enabled_source_count | 当前空间来源许可修订与有效启用数量 |
| selected_input_id | 本次明确跟进资料，未指定时null |
| inputs | 空间登记资料及其保存状态 |
| inputs[].check_status | not_checked / passed / failed / registration_changed |
| inputs[].checked_at / check_sequence | 最近保存的检查时间与序列 |
| inputs[].lifecycle_state | 资料当前active / disabled / archived状态 |
| inputs[].saved_build_counts | 与该完整登记绑定一致的queued/running/succeeded/failed/interrupted/views_failed数量；只读保存任务，不轮询；views_failed表示模型已冻结、至少一类视图未就绪 |
| selected_batch_id | 明确指定批次；未选择为null，不默认最近批次 |
| can_submit | 仅表示保存预检匹配、资料启用及只读批次条件满足，不是实时准入保证 |
| inputs[].route | 当前格式的类别、所需信息、处理结果说明 |
| inputs[].batch | status、choices、issue、selected_batch_id、can_submit、current_files_checked=false；只读登记与批次记录 |
| inputs[].issue | 预检失败的通用原因与处理建议；无本机路径异常泄露 |
| next_action / detail | 针对本次资料的建议与对应模块链接 |

没有资料时引导导入资料（next_action.intent=import）；上传资料包不依赖来源配置。已有资料但未指定时引导明确选择。指定资料上次通过且当前启用时，继续判断批次：未加入任何批次为not_required；已加入批次但未选择时为selection_required（至少一个可用）或blocked（均不可用）；明确选择为ready或blocked。单个封存批次也不自动代选。批次复用提交时的状态、成员摘要和完整登记摘要判据，但摘要读取不打开源数据、不轮询worker、不写入数据库。条件满足可前往构建中心；有成功/进行中任务时提示查看核对或刷新。失败、未检查、登记变化或资料停用时，引导资料详情和预检。来源停用不使既有登记失效。

这是参考步骤，不是新建图执行引擎或发布/构建许可。构建提交沿用既有源文件、生命周期、归属与批次核验；不要求存在本页面预检记录。原先匹配当前候选与固定发布的流程结构保留，准备新输入不替换它们。响应声明`current_files_checked=false`和`jobs_polled=false`，保持请求时多次读取，不是跨库事务快照。工程模式原预检仍为即时只读检查，不增加认证持久能力。


## P15 补充（2026-11-05）

`batch_id`不在当前场景中返回409；该场景内的错误批次不静默替换，返回blocked及原selected_batch_id。明确批次的修订在最终构建请求中提交并实时检查。停用／整理中批次、成员不匹配、登记摘要变化分别保留原因。批次成员只读`choices`不包含本机路径。

前端准备区采用“导入资料 → 检查整理 → 用于构建”；构建页换资料时仅清除不属于新资料的偶发旧选择，明确直链中的错误引用保留并阻断。资料详情、场景摘要、构建准备调用同一只读解释。前端引导先预检；直接API仍沿原准入重新验证文件，不新增“必须持有保存预检”的后端门槛。
