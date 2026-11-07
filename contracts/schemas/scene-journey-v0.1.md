# 场景四步流程投影 v0.1

`GET /api/workflow?space_id=...` 的 `summary.journey`，profile 为 `cospace.scene-journey/0.1`。沿用原接口授权与显式 input / job / publication 参数；没有新增写入或发布门禁。

- `target: {kind, id}`：固定发布优先，其次明确任务、明确准备资料，最后当前选择候选或场景概况。未指定任务时不选最新任务。
- `steps`：固定顺序 data（资料准备）、build（模型构建）、review（核对确认）、delivery（发布交付）。每项含 id、title、status、detail、action；action 可为 null，非空沿用业务模块、明确引用和 allowed 授权。
- `status`：complete（证据已具备）、pending（待完成）、in_progress（保存任务排队或运行记录）、needs_attention（失败、不可读、暂停等需处理）、unknown（没有针对该目标核验）。complete 不表示现场质量通过或设备已启用。
- `current_step`：依次第一个 needs_attention / in_progress / pending；全部具备或只能表达未知时为 null。
- `optional_enhancements` 为 ontology、association；`consumer_status` 固定 unobserved；basis 为 saved_records_not_live_execution。

## 目标与依据

| 目标 | 处理 |
| --- | --- |
| 明确准备资料 | 依据该资料预检与当前准入投影；后续步骤待完成，不套用旧候选 |
| 明确非当前任务或未成功任务 | 读取同场景任务及该任务可读候选；前置资料与匹配交付未核验，核对待完成 |
| 当前选择候选 | 来源绑定、可读固定模型、保存人工核对、匹配固定发布各自投影；有发布不代替缺失的核对记录 |
| 查看固定发布 | 前三步为未知，明确不套用当前工作进度；交付步骤依据该固定发布完整性与生命周期 |
| 无候选 | 仅为场景流程概况，提供选择明确资料／任务入口，不把任意运行任务视为用户目标 |

原 `summary.service_status`、publications 和 available_publication_count 仍独立表达现有固定发布。新目标失败不撤销历史服务；暂停、退役不回退到旧版本。语义修订仍产生新候选。

HTTP 层逐项授予 action.allowed；无 build.run 的查看者不返回 journey（null），延续已有工程记录脱敏。浏览器只展示投影，不计算第二套业务状态，不触发预检、任务推进或导出。
