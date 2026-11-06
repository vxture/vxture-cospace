# F06c 事件与追溯实验契约 v0.1

日期：2026-10-28。Schema：[trace-events-v0.1.schema.json](trace-events-v0.1.schema.json)。实现：`packages/lifecycle/trace_events.py`。本版本仅支持 synthetic 候选构建与检查，独立于既有 API、发布和 agent 安装契约。

## 1 数据结构与格式选择

| 对象 | 格式与字段 | 校验责任 |
|---|---|---|
| 追溯归档 | JSON；schema_version、trace_id、scene_id、agents、entities、activities、events | 封闭引用图；责任主体/实体/活动 ID 全局唯一，资源无遗漏或额外项 |
| 事件信封 | CloudEvents 1.0 字段子集；specversion、source、id、type、subject、time、datacontenttype、data | 事件身份是 source + id；限定 urn 来源和两个候选事件类型 |
| 事件数据 | 独立 schema_version、trace/scene、activity/entity、correlation_id、causation | 绑定同一追溯与场景，subject 对应活动生成实体，事件时间等于活动结束时间 |
| 实体 | source_snapshot / change / candidate / inspection / evidence；member 的 path、bytes、sha256 | 检查原字节大小与摘要；同一资源不得重复登记 |
| 活动 | candidate_build / candidate_inspection；agent_id、used、generated、started_at、ended_at | 单一生成活动、使用时序、无环依赖；一个活动对应一个事件 |
| 责任主体 | person / software；id、label | 只记录责任声明，不验证人员或软件身份 |
| 血缘交换 | JSON-LD 的 PROV-O 映射子集 | Entity、Activity、Agent、used、wasGeneratedBy、wasDerivedFrom、wasAssociatedWith |

采用独立追溯归档，避免把投递记录回写进不可变真值/视图清单导致摘要变化。变更与来源清单保留原字节，作为被引用实体；归档无需替换业务对象的原格式。

两个事件类型为 `cospace.candidate.created.v1` 与 `cospace.candidate.inspected.v1`。`inspected` 表示检查活动结束，检查结果在报告实体内；事件名称本身不表示通过质量验收。未提供 accepted、release.published 或可执行授权事件。

## 2 因果、时间与投递

`correlation_id` 关联本轮作业，`causation` 指向直接触发事件的 source/id。活动 used/generated 表达完整多输入依赖，单个 causation 不替代全部父关系。封闭归档要求因果事件存在且对应直接输入依赖；有上游生成活动时不能省略 causation。UTC 时间必须显式以 Z 结尾；不推断本地时区。

`EventInbox` 只做进程内暂存。乱序到达可以先暂存，闭合归档再检查引用。规范化 JSON 内容相同且 source/id 相同视为重复；键顺序不影响去重。同一身份内容不同报冲突，不覆盖旧记录。更换 source 代表不同事件身份，不代表来源可信。所有接收结果的 business_applied 均为 false。

这不是持久化消息收件箱，不保证进程重启去重、事务投递、业务恰好执行一次或代理签名。后续接入需要持久化唯一约束、事务 outbox/inbox、失败重试与业务状态机；AsyncAPI 应随真实通道、投递和安全配置确定，当前不虚构传输绑定。

## 3 资源与边界

最多128个实体、128个活动、256个事件、32个责任主体；每个资源最多8MiB，全部资源最多32MiB。暂存器最多256个唯一事件。路径限定安全相对形式，拒绝大小写碰撞、路径穿越及 Windows 保留名。当前校验器只接收内存字节，不负责文件系统解包、符号链接处理或网络获取。

内容摘要与引用图完整，不证明实体正文的语义一致、控制点独立性或真实精度。`actor_identity_verified`、`evidence_semantics_verified`、`authorized`、`robot_ready` 始终为 false。JSON-LD 导出仅为有限 PROV 映射，未执行 RDF 推理或完整标准符合性认证；CloudEvents 字段子集也不构成消息系统认证。

## 4 可复现样例

从仓库根目录执行：

```powershell
.venv/Scripts/python.exe -m experiments.scripts.generate_trace_sample
.venv/Scripts/python.exe -m pytest tests/test_trace_events.py -q
```

`examples/trace-events` 包含 trace.json、prov.jsonld、validation.json 与14个实体资源。样例实际调用 F06b2 构建器和重建预览，封存来源清单及全部块、来源 pin、变更及全部输入、候选清单及全部块、检查报告。固定时间为合成时间，软件主体为合成声明；重建核对不等于独立测量校核。样例不产生新真值或正式发布。
