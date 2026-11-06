# 任务只读接口 v0.1

日期：2026-10-26。仅用于合成检查工程核对，没有任务提交、运行、取消或发布的HTTP写接口。任务来源spec见[任务契约](check-job-v0.1.md)。

## 路径与内容

| GET路径 | 返回 |
|---|---|
| /scenes/{scene_id}/jobs?limit=20&offset=0 | scene_id、items、limit、offset、has_more；每项为job_id、state、revision、requested_at、sha256、spec |
| /scenes/{scene_id}/jobs/{job_id} | scene_id、完整任务规格及其摘要、状态/修订、提交时间及操作者声明、attempts、events |
| /scenes/{scene_id}/jobs/{job_id}/input | scene_id、job_id、spec_sha256、dataset_sha256及固定dataset manifest |
| /scenes/{scene_id}/jobs/{job_id}/report | scene_id、job_id、spec_sha256、已核验artifact清单和检查report |

limit范围1..50，offset范围0..10000；越界422。列表按requested_at、job_id倒序，仅当前场景，空场景返回空列表。offset分页是每次读取结果，不提供跨页快照保证；并发新增任务时可能重复或移动，刷新从第一页重新读取。当前没有跨场景检索、总量统计或日期过滤。

详情读取在事务中锁定job行，避免状态与attempt/events在不同提交之间混读；这不是内容修改操作。输入接口复核固定dataset及实际封存字节。报告接口仅对succeeded开放，复核artifact文件大小/摘要、job/attempt/spec/dataset绑定。历史成功任务的内容损坏不改写原执行状态，报告读取明确失败。

404：job_not_found（含场景不匹配）、dataset_not_found。409：artifact_unavailable表示尚无成功报告。503：content_corrupt、storage_error，或内容文件无法读取；未配置读取依赖时job_reading_unavailable。错误体保持detail.code/message，不输出存储路径或凭据。

任务属于构建工程历史，不依赖当前服务发布。撤回空间发布不会修改或隐藏任务记录，也不代表任务报告仍可作为正式消费服务；任务页面没有采用资格。后续认证与项目访问控制须分别覆盖这些工程接口，不能把场景过滤当作授权。当前仅本机开发用途，无身份认证。

前端先核对scene_id、job_id、spec_sha256及dataset摘要，再显示关联输入或报告。修改场景重置工作面，修改任务、切换任务或读取详情失败清除旧输入/报告；每次内容刷新先清除相应旧结果。任务状态是最近一次读取，手动刷新，无自动运行、恢复或实时状态承诺。
