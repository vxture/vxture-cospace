# 成果生命周期影响检查 0.1

状态：H2已实现，只读。JSON结构见[Schema](preview-artifact-impact-v0.1.schema.json)，规则标识为`cospace.preview-lifecycle-policy/0.1`。仅用于本机工程预览。

## 请求与响应

`GET /api/artifact-impact?space_id=SPACE_ID&artifact=KIND:RECORD_ID`

space_id必须显式提供；artifact仅接受`input:ID`、`candidate:ID`、`publication:ID`。离线包没有独立生命周期目标，调用方应检查其来源`publication:ID`。只读取目标空间的记录，不接受跨空间目标。

| 字段 | 定义 |
| --- | --- |
| profile | 固定`cospace.preview-artifact-impact/0.1` |
| policy_version | 本次评估采用的规则版本 |
| space_id、project_id | 已核对的成果归属；不等于用户访问授权 |
| target | 目标key、kind、record_id、label、state、integrity和selected |
| checked_at | 本次检查时间，UTC RFC3339 |
| snapshot_sha256 | 所读取保存记录的内容摘要，排除checked_at；不是授权、签名或提交令牌 |
| references | 按key去重的后续成果、相关保存任务及资料所在批次；kind区分batch/job/candidate/publication/offline_package |
| reference_counts | 五种引用的独立计数；任务和候选可能描述同一次构建，不能相加当成独立成果数 |
| selected_dependencies | 当前所选候选中，目标自身或依赖目标的候选key |
| issues | 空间级来源缺口的code和key；存在缺口时所有操作计划阻断 |
| plans | 操作名称、规则判定、blockers、未来生效范围、保留内容及建议处理步骤 |

所有响应固定`mode=impact_preview_only`、`mutation_supported=false`；每项plan固定`executable=false`。`quality=unverified`、`robot_ready=false`。这些字段不能由客户端改成可执行。

`references[].distance`是匹配成果依赖的反向图遍历距离。保存任务是单独补入的关联记录，自身任务距离0，其余关联任务和批次距离1；不代表完整图的最短路径，也不代表空间距离。reference中的state是现有记录状态，不是本次新增的生命周期状态。

## 判定规则

`blocked`表示存在保存记录层面的阻断；`eligible_by_saved_records`仅表示本次规则检查未发现阻断，不能解读为允许执行、质量合格或允许机器人运行。

| operation | 除空间级记录缺口外的阻断 | 未来操作范围（H2尚不执行） |
| --- | --- | --- |
| disable_input | 无额外阻断，受影响引用仍完整列出 | 阻止新的资料构建，含批次入口；不取消已准入任务 |
| archive_input | 整理中/封存批次成员；保存的排队/运行任务；当前选择依赖此资料 | 从新建资料选择范围移出并阻止新构建；保留历史详情和文件 |
| archive_candidate | 候选是当前选择；相关保存任务仍排队/运行 | 阻止新选择、以其派生关联候选或固定发布；已有后续成果保留 |
| pause_distribution | 无额外阻断，提醒核对入口和替代发布 | 停止此发布的在线查询、资产和离线导出；保留快照及已有消费副本 |

blockers取值：`dependency_records_incomplete`、`active_batch_membership`、`saved_active_build_attempt`、`current_selection_depends_on_input`、`candidate_is_current_selection`。

issues取值包括`artifact_unavailable`、`reference_missing`、`reference_mismatch`、`reference_unrecorded`、`selection_binding_unavailable`、`active_job_source_unresolved`、`batch_member_missing_or_changed`。任何一项都可能隐藏入向引用，因此即便缺口不直接属于目标，也保守阻断本空间全部计划。

## 读取与一致性边界

先读取已有成果目录，沿`status=matched`引用反向遍历，再补入同空间保存任务和批次成员。包含失败、中断及排队/运行记录；不轮询进程，不把保存的running解释为进程当前存活。停用批次仍列出，但不再作为“活动批次”阻断。

不重新预检源文件、不生成ZIP、不查询消费端、不写入业务记录或创建空SQLite。原始来源绝对路径不返回。固定发布的offline_package记录仅为导出入口，不能由此判断曾下载或已激活。

`consistency=request_time_reads_not_transactional`：多文件和批次读取不构成一个跨存储事务。检查前后比较当前选择文件，变化则拒绝整份报告；其他记录仍可能并发变化。摘要用于报告对照，不能解决执行时并发。H3必须在写入边界重新检查并与任务准入、候选选择、发布排序。

## 失败语义

| HTTP | 情形 |
| --- | --- |
| 200 | 返回完整报告；业务阻断由plans表达 |
| 404 | 空间不存在，或目标不在该空间目录 |
| 422 | 缺少必填参数、非法artifact或不支持的kind（含offline_package） |
| 409 | 来源记录无法读取/损坏、批次存储不可用，或读取中当前选择变化；应刷新后核查 |
| 503 | 构建/发布服务尚未配置 |
| 405 | POST该只读端点；本阶段没有生命周期写接口 |

界面刷新先清除旧报告；失败或响应目标不匹配时不保留旧判定。空间、成果切换及关闭检查均清除报告。

## H3a之后的使用边界

该GET报告仍保持mutation_supported=false、计划executable=false，不承担写操作。资料/候选的状态提交已由独立[artifact-control契约](preview-artifact-control-v0.1.md)实现，并合并引用摘要及控制账本修订进行执行前重检。H2单项规则未按当前生命周期状态裁剪，不能把它当作可提交操作列表；实际列表读取artifact-control。固定发布分发控制仍待H3b。
