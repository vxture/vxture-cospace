# 恢复日志交换契约 0.1

日期：2026-10-27。状态：设计草案，仅合成结构。依据[恢复协议](../../docs/architecture/智能体恢复独占与提交日志协议-v0.1.md)。[Schema](recovery-journal-v0.1.schema.json)约束交换记录，不是数据库迁移、远程授权或恢复执行接口。

J2实现进展：实验JournalStore已导出符合本Schema的真实合成intent和commit_receipt，并验证事务关系，见[记录](../../docs/validation/智能体消息留存与原子提交验证-2026-10-27.md)。recovery_plan/result仍仅格式草案，没有恢复执行入口；原占位样例保持仅结构用途。

J3实现进展：新RecoveryStore已生成真实合成recovery_plan/result，见[记录](../../docs/validation/智能体恢复状态机验证-2026-10-27.md)。完成时control代次再次推进，receipt/result保留处理时代次；读取最终结果不要求结果代次等于读取对象当前代次。begin/resume/提交接口仅实验Python方法，不是远程维护授权。上段J2边界与原占位样例保留为阶段历史。

四类记录共用store_id、固定context_sha256和generation；schema_version固定cospace.test-recovery-journal/0.1，test_only=true、authorized=false、robot_ready=false。UUID采用小写标准连字符形式，计数使用不超过2^53−1的非负整数，generation从1开始；数值溢出拒绝，不环绕。

| record_kind | 内容 | 结构检查以外必须核验 |
|---|---|---|
| intent | 原字节JWS及摘要、消息种类、身份/binding摘要、准备时状态版本 | 原字节摘要、签名/角色、完整binding、唯一ID不可换消息 |
| commit_receipt | intent/消息引用、结果及前后版本/状态摘要 | 与实际状态变更同事务、唯一最终记录、版本和摘要链一致 |
| recovery_plan | 恢复ID、期望状态、完整未决集合摘要、目标摘要及逐项动作 | 锁与代次、所有比较条件、无漏项/重复ID、签名及撤回证据 |
| recovery_result | 恢复ID、计划摘要或null、blocked/reconciled及最终状态 | reconciled必须有真实计划和原子提交，不能由导入JSON创建成功凭据 |

intent中的token保留原始ASCII JWS，不解码后重编码；Schema只约束三段形态和长度，不保证Base64url规范性、签名正确或payload有效。所有SHA-256均小写十六进制，含义以协议定义为准。plan_sha256是完整recovery_plan对象的canonical摘要，该对象自身不含plan_sha256字段。

计划items按intent_id排序，唯一且与完整未决集合一一对应。pending_set_sha256对每项的intent_id、message_kind、identity、token_sha256四字段组成的排序数组做canonical摘要；action/reason不计入该集合摘要，但计入完整计划摘要。retain_blocked表示不能完成恢复，不是可以忽略的软告警。

applied对应一次实际状态改变，after_revision=before_revision+1；idempotent/rejected的前后版本及摘要必须相同。多项恢复按items顺序逐项建立receipt链，最终版本和摘要必须与计划目标匹配；计划不指定最终版本时由执行器按实际applied项数计算。正常接收的receipt与准备代次一致；恢复receipt使用处理时当前代次，并核对原intent所属store/context。

结构校验不会计算这些关系，也不执行锁、写事务、验签、时间判断、历史重放或CAS。导出样例只能用于格式讨论，不能导入现有ValidityStore。旧v1标记和库没有足够历史，不适用v2的“无receipt即尚未最终处理”推论。

样例与结构证据见[验证记录](../../docs/validation/智能体恢复日志契约核对-2026-10-27.md)。正式迁移、密钥配置变更、历史日志裁剪及硬件防回滚均未定义为本契约能力。
