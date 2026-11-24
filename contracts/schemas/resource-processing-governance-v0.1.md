# 处理血缘与参考原件归档 v0.1

D04c 在数据详情内读取实际保存的处理绑定；独立参考原件的可恢复归档与原件、版本、引用共用业务项目数据库。不增加导航或独立平台。

## 处理血缘

`GET /api/data-processing?resource_id=resource-<32hex>`；支持 HEAD，不接受 project_id、客户端工作区或文件路径。需要来源管理权限；场景处理还须具备该场景 build.run 和 publication.manage。接收方不能通过参考授权查看源处理链。

响应 profile 为 `cospace.resource-processing/0.1`，包含可信 workspace_id、resource_id、focus、nodes、edges、issues。节点类型为 input、job、candidate、human_view、agent_view、publication；边包括 consumes、produced_by、expresses、derived_from、published_from。任务保留保存状态；仅成功任务且模型元数据与固定输入绑定相符时建立模型产出。表达节点只表示 manifest 中记录的表达及 member 摘要，不表示载荷已检查。

输入按登记及坐标修订历史的固定记录匹配；派生核对基础候选及 manifest 原始 SHA256 与任务绑定；发布同时核对来源候选、发布记录与发布目录内冻结 model.json 的摘要和归属。离线包导出入口不是已生成成果，不能计入血缘。缺失、损坏、跨场景或摘要不符标记 unresolved / partial；不返回外域节点标识、绝对路径、任意来源链接。独立参考原件及附件尚无构建消费契约，返回 not_applicable（未记录处理关系），不从名称或时间推断。

响应只保留与当前资源连通的处理图。扫描每类最多 10000 个元数据文件，单件最多 256 KiB、总节点最多 10000；超过安全预算返回 503。仅做请求时元数据读取，非事务快照；source_files_rechecked=false、jobs_polled=false。GET 不轮询任务、不加载 geometry / 点云、不导出或创建目录。

## 可恢复归档

`GET /api/data-governance?resource_id=...` 返回 `cospace.resource-governance/0.1`：active / archived、独立治理 revision、snapshot 摘要、全工作区关联引用与有效共享是否存在（布尔值，不披露全局数量或不可见项目）、archive / restore 许可、最近操作。与资源登记修订号分别维护。

`POST /api/data-governance`：resource_id、action=archive|restore、32hex request_id、expected_revision、64hex expected_snapshot、非空 reason（最多 500 字符）。登录、CSRF、可信工作区及来源管理权限均重新核验；不接受删除、归属转移或级联操作。

归档仅适用于场景外的独立原件。使用相同 SQLite 写事务检查整个可信 scope 的所有引用与授权：仍有关联引用（即使授权已撤销或到期）或有效共享时禁止归档；记录损坏 / 超预算时拒绝。状态、影响快照变化返回 409，不能凭可见引用统计放行。归档状态及前后审计同事务保存；相同 request_id 与内容返回原结果，改内容拒绝。

共享授权、参考关联、显式版本升级、原件追加和登记维护的新写入在同一数据库写锁内检查 active；撤销和解除继续允许。归档不删除原件 / 历史、不改变旧构建及发布、不释放存储。当前 / 历史下载保持原权限。恢复允许后续新用途，不自动共享、关联、构建或发布。新表随既有业务 SQLite checkpoint 备份。

场景 input / candidate 及两个表达仍复用原 artifact-control 状态与依赖引擎；本接口拒绝场景资源，不能绕开场景生命周期检查。目录附加 lifecycle_state；筛选 lifecycle=all|active|archived|disabled。未接入状态的附件 / 接收引用为 null，不虚称可用；状态筛选不含这些未核验项。

权限不足 403；参数无效 422；状态 / 影响变化及依赖阻止 409；证据损坏、预算超限或服务不可核验 503。全部响应 Cache-Control: no-store。
