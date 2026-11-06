# 当前空间参考流程 v0.1

`GET /api/workflow?space_id=SPACE_ID`。可选 `input_id`（授权工作台资料准备）、`job_id`（明确跟进任务）、`publication_id`（明确查看发布）。归属空间预览，汇总三类六入口的已保存记录，不新增模块、工作流执行引擎或发布门禁。

## 范围与绑定

工程模式 space_id 必填，缺失422、不存在404。授权工作台先检查平台身份、Workspace与空间能力，无权请求在读取记录前拒绝；匿名401、越权403。异常记录或读取期间选择指针变化返回409 `workflow_unavailable_refresh_required`，调用方须清除旧报告并刷新。工程模式的空间归属检查不代替平台ACL。

只采用显式保存且摘要一致的当前选择，不自动选最新候选。匹配发布必须同时具有相同candidate_id和model_manifest_sha256；仅在这些匹配发布中按保存时间及ID排序。新选择未发布时publication_ref为null，不借用历史发布。当前选择变动会使整个报告重新读取。

报告读取不是事务快照，`consistency=request_time_reads_not_transactional`；读取前后检查当前选择指针，但不承诺跨文件事务一致性。observed_at为读取时间，不是采集时间或数据有效期。

## 响应

profile为`cospace.preview-workflow/0.1`，包含project_id、space_id、observed_at、selection_status、candidate_ref、publication_ref、counts、stages、next_stage、next_action。

- candidate_ref：candidate_id、model_manifest_sha256，或null。
- publication_ref：publication_id、model_manifest_sha256，或null。
- counts：成果目录计数，以及当前候选的objects、business_bindings、object_relations。
- 每阶段：id、title、module、status、detail、basis、action，可附加 `optional=true` 表示按需增强；不提供该字段的阶段默认必经。action包含label、module和values；values传递space及必要的input、job、publication或固定本体三元引用。授权工作台附加 action.allowed；报告含 business_authorized=true，不代表现场质量验收。

导航约定（P8）：构建action的values带 `tab=flow`；态势服务action保留当前候选的 `job`，有匹配发布时另带 `publication`。消费action另带 `from=consumer`，页面据此展开该发布的说明。客户端必须先确认发布属于当前场景，缺失目标不得打开其他发布的说明。此参数只控制展示目的地，不表示安装、激活或设备状态，也不授予权限。点击与响应读取之间选择可能变化，发布前仍须校验目标候选与当前选择，服务端继续校验修订。

| 阶段id | 模块 | 判断依据 |
| --- | --- | --- |
| data | 数据管理 | 空间资料登记记录与当前候选来源绑定；不重新预检源文件 |
| build | 构建中心 | 当前选择完整性与已保存人工核对绑定，或任务保存状态 |
| ontology | 语义本体 | 当前候选嵌入的固定本体引用与规则 |
| association | 空间关联 | 当前候选对象、业务绑定与关系快照 |
| delivery | 态势服务 | 与当前候选及摘要匹配的固定发布 |
| space | 空间预览 | 匹配发布与人视图成员绑定；智能体成员随模型检查 |
| consumer | 态势服务 | 始终unobserved，服务不观察外部消费库 |

| status | 含义 |
| --- | --- |
| ready | 当前选择/核对或双视图预览的内部条件具备，不是精度验收 |
| recorded | 已保存的对应记录或快照具备；不代表现场核实 |
| pending | 当前参考流程尚缺记录或显式操作 |
| blocked | 选择、核对、来源或视图绑定异常 |
| in_progress | 保存的任务记录为queued/running；本接口不轮询实际进程 |
| unobserved | 服务不掌握消费端实际状态 |

next_action 优先第一个 blocked 阶段，其次第一个非 optional 的 pending/in_progress 阶段，均无则指向 space，打开匹配的固定空间。**P12修正了此前正常结束仍指向consumer的行为**；consumer保持unobserved，不因服务端完成而伪造设备状态。ontology 与 association 现标记 optional=true：无记录仍保留 pending，不虚报完成，页面显示“可选增强／未补充”；缺项不阻断几何双视图发布与使用。已嵌入的规则／对象绑定损坏仍不能跳过。空关系集及历史发布继续兼容。未来用途需要强制语义时应增加明确的用途契约，不能把这两个增强默认当作所有场景门禁。

P12页面默认显示紧凑摘要，完整流程在“流程明细”中按需展开。完整阶段明细仍跟随当前选择及匹配发布；摘要可同时呈现明确跟进任务、当前查看发布与固定发布可用性，不用于代替历史固定发布大屏。

## P12只读摘要

新增 `summary`，profile为`cospace.scene-progress/0.1`。从同次读取的目录与流程投影；不持久保存另一套状态，不改变发布准入。

| 字段 | 定义 |
| --- | --- |
| work | 工作提示：status、label、detail、action。优先明确job，其次明确input，未指定时围绕当前选择；没有明确目标，不把最新任务自动当作用户跟进任务。无工程权限时为null |
| candidate_ref | 当前所选候选；不是当前查看发布的来源候选。无工程权限时为null |
| service_status | complete／pending／needs_attention，表示当前选择的服务端流程。只有非可选阶段（consumer除外）均为ready／recorded才complete；不是生产或质量验收 |
| tracked_job | 明确请求的job_id、保存state、is_current，或null。不轮询进程，不自动重试 |
| viewing_publication | 明确请求的固定发布：publication_id、candidate_id、status、matches_current，或null。不指定时不擅自补最新发布 |
| publications | 当前场景发布的固定引用、available／paused／unavailable及与当前选择的关系；不可读不计可用 |
| available_publication_count | 上述available数量；某个版本可用不表示目标暂停版本可自动替代 |
| primary_action | 明确查看发布时打开该版本；暂停或不可读时进入该发布核查，否则采用work.action。无权动作不提供可执行链接 |
| consumer_status／consumer_state_checked | 恒为unobserved／false，服务不掌握外部安装或启用状态 |

明确跟进失败任务时，work可为needs_attention，service_status仍可complete，历史发布也可available。明确跟进已发布的历史候选不会被误报为需要重新核对的新候选。查看历史发布时matches_current=false不代表该版本失效。

授权在读取明确任务／发布之前校验所属场景及能力：job_id须build.run、input_id须data.manage、publication_id须space.preview；跨场景拒绝。查看者仍可浏览已授权固定发布，但摘要不返回准备记录、跟进任务或当前工程选择。工程模式错误目标或损坏记录返回409；授权模式无权或外场景目标返回403。

资料预检仅代表保存的历史检查。明确input的主动作使用其准备记录；实际构建仍重新核验。前端携带明确批次时继续保留batch导航参数，提交时由原批次准入校验修订与成员。

读取前后检查选择指针，包括从无到有的并发变化；可检测到的变化拒绝拼接结果。仍不承诺跨目录、生命周期和文件的事务快照。前端对空间、明确job与publication响应绑定进行校验，并在错误或重新读取时移除旧摘要和旧主动作。

## 副作用与结论边界

不执行构建、不轮询任务、不解析外部源文件、不导出离线包、不安装或恢复消费库、不写当前选择。`source_files_rechecked=false`、`consumer_state_checked=false`、`jobs_polled=false`。

`scope=reference_flow_not_publication_gate`、`quality=unverified`、`production_ready=false`、`robot_ready=false`。报告不计算完成百分比，不从下载推断消费激活，不把保存核对解释为认证人员签署。

固定发布核对接口仍为`/publications/ID/api/checklist`，会构造包并执行同进程在线实现/离线读取器对照；它与本接口职责不同，不能把这类对照称为HTTP或跨进程断网验收。
