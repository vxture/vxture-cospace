# 契约规范

本目录保存跨进程、离线交付及消费端共享的数据与接口规范，是交换格式的唯一规范源。设计解释见[最小数据与服务发布契约](../docs/architecture/最小数据与服务发布契约-v0.1.md)。

D1新增[固定预览范围查询契约](schemas/preview-range-v0.1.md)与JSON Schema，约束坐标系、半开范围、表面单元、返回上限及在线/离线一致性。仅适用于本机真实样本预览，不代表正式发布或机器人运行协议。

- schemas：真值、视图、服务发布及关联记录的数据模式。
- api：网络协议选定后按需创建。
- compatibility：出现契约升级需求时创建，记录兼容与迁移规则。

商业制单资料的本地校验见 [subscription-plan-proposal.schema.json](schemas/subscription-plan-proposal.schema.json)。该 Schema 仅约束本仓套餐策划草案，不定义平台 API，也不提供运行时授权。

契约保持语言无关。语言绑定由规范生成或以一致性校验约束，不能在不同模块手工维护互相冲突的字段定义。正式契约中的真值身份仍使用truth语义，视图种类仍为human或machine；目录名spatial、agent不自动改变交换格式。

P17 增加[资料与构建阶段显示抽样契约](schemas/input-preview-v0.1.md)及两份 JSON Schema。仅用于受权、受预算约束的只读预览，沿用实验流程的 human／agent 字段，不替代构建或正式交付格式。

当前已建立合成服务包的实验性子集说明、JSON Schema结构规范及专用校验器；尚无正式发布格式或网络接口规范。

R0新增[智能体运行包合成契约0.1](schemas/agent-package-v0.1.md)及Schema，支持固定来源与组件依赖校验；仍为synthetic子集，未实现可信分发或机器人交付。

R2的内容证明、能力凭据、状态快照及信任配置仍处于[设计阶段](../docs/architecture/智能体可信分发与离线有效性设计-v0.1.md)，待R2a建立独立契约与测试向量，不改写R0的合成有效性声明。

R2a首批已新增[测试证明与测试公钥配置契约](schemas/trust-proof-v0.1.md)及Schema，实验验签和绑定检查已通过，正式根委托、时效、撤回和授权仍待R2b及后续实现。

R2b第二批增加[测试根单层委托契约](schemas/test-delegation-v0.1.md)及Schema，明确子密钥角色、场景、期限和撤回约束；仅为合成格式，未实现正式根轮换或动态信任迁移。

R2b第四批新增[恢复日志交换契约草案](schemas/recovery-journal-v0.1.md)，定义intent、commit_receipt、recovery_plan与recovery_result。只完成结构核对，不是可导入旧门禁的恢复命令；运行状态机、OS锁及原子提交另行验证。
