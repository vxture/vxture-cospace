# 合成检查任务契约 v0.1

状态：CLI与内部任务持久化的实验性契约。Schema见[check-job-v0.1.schema.json](check-job-v0.1.schema.json)。

spec固定kind=synthetic_check、executor=synthetic_check/0.1、dataset_id、dataset_sha256、scene_id、超时/日志配置及环境。环境包含Python实际版本、操作系统、执行相关源码/Schema/uv.lock指纹和关键Python依赖版本；不是容器镜像或完整可复现系统镜像承诺。job.sha256绑定完整spec。actor与requested_at属于提交记录，不代表已认证签署。

状态：queued、running、succeeded、failed、cancelled。revision从0开始，每次认领、终结或取消增加1。认领与queued取消使用同一状态及revision条件；失败返回state_conflict，不隐式重试。当前每job仅一个attempt，数据库唯一约束防止重复创建。中断与恢复尚未实现，失去监督的任务可能停在running。

attempt保存开始/结束时间、诊断或产物引用。events保存queued、running、终态，状态与事件事务提交。失败诊断包含stage、code、message和attempt_id；字段级诊断及完整退出日志先保存在本地attempt目录，后续再形成公开读取契约。

成功产物绑定job_id、attempt_id、spec_sha256、sealed_at和固定文件的路径/大小/摘要。报告schema_version=cospace.check-report/0.1，包含dataset_sha256、validation、data_kind=synthetic、candidate_created=false、truth_created=false，以及not_executed清单。validation只表示输入合成包规则一致，不表示算法或真实消费质量已通过。

本轮产物读取返回检查报告，不暴露宿主绝对路径。无成功终态时报artifact_unavailable；摘要变化报content_corrupt。预检环境变化environment_mismatch、输入变化input_mismatch、执行超时timeout、日志超限log_limit、非零退出executor_failed、报告不绑定上下文invalid_output。API网络错误映射待I3定义。

产物先封存后数据库提交，提交失败不产生成功任务。已生成的文件不得被静默当作成果采用；历史job成功与后续产物可读取健康分开。正式候选/真值/视图/服务发布契约不因此发生变化。
