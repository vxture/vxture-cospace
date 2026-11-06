# F06a 消费请求、响应与拒答实验契约 0.1

日期：2026-10-28。schema_version=cospace.consumption/0.1。独立纯函数/内存实验，无 HTTP 接入、ROS适配或机器人运行授权。

## 1 请求与绑定

请求固定 source（场景、发布、真值、机视图身份及摘要）、运行包清单摘要、质量profile身份及摘要、frame、purpose、mode、max_age_s。最多256项，item_id唯一且顺序保留。

mode 分 historical / operational；仅历史 spatial_query 能得到合成查询结果。未知字段、未知版本、空批次、重复项身份或非法外层配置整次报参数错误。单项 point 故意不在外层 Schema 限制类型，以允许批量报告 invalid_point；点的有限三维数值检查由领域校验执行。Schema 单独通过不表示单项坐标合法。

InspectionConsumer 从F04快照读取固定质量profile与assessment，校验F05运行包来源。构造后会话持有固定字节，后续调用不因外部字典替换隐式更新；没有 latest 或当前指针切换。来源、包、profile、frame、用途或模式不匹配则整次拒答，不将版本错误编码为空间unknown。

## 2 时效和历史边界

调用者显式传入 now；UTC格式和未来观测检查沿用F03。最大陈旧度取请求与profile中非空值的最小值，请求省略数值时必须显式null，仍继承profile限制。历史profile两者均null时可读取旧快照。age使用最老观测起点，等于限值允许，超限整次拒答。

historical 不能选择 operational profile 绕过规则；mode必须相等。operational 无论数值条件如何均返回 runtime_authority_unavailable，不查询单元；可信时间、撤回、签名和有效性凭据尚未接入，不用合成门禁伪造运行许可。

响应分别提供 served_at、observed_from、observed_until、oldest_observation_age_s、有效max_age_s。valid_until固定null，表示没有可声明的运行授权有效期；不把数据时效截止冒充凭据截止。quality.grade_label来自固定规程；当前可为null，evidence_verified=false。

F03的几何/覆盖/语义声明指标不满足时整次quality_requirements_not_met；时效每请求重算，不沿用会话构造时陈旧度结果。汇总限值通过不证明单元证据可信，源几何与体素派生一致性仍未验证。

## 3 结果、完整性与错误

| 情况 | 项目表示 | 是否算作失败 |
|---|---|---|
| 空闲、占据 | result + observed_free/occupied | 否 |
| 未观测、退化、冲突、未分发块 | result + unknown +具体reason | 否，unknown计数增加 |
| 范围外 | result + out_of_scope | 否，out_of_scope计数增加 |
| 非法单项坐标 | error + invalid_point，无state | 是 |
| 读取器已知ValueError | error + query_failed，无state | 是 |
| 未预期程序异常 | 抛出，不生成成功响应 | 不伪装unknown |
| 全局来源/用途/时效/权限条件不满足 | refused，items=[] | 不生成单元结论 |

非拒答批次必须一项对应一个结果或错误。completeness.requested=returned+failed；unknown与out_of_scope是returned子集。status=completed/complete只表示传输响应完整，即使全部unknown也可完整，不是观测覆盖率100%。存在单项错误为partial；全局拒答为none，returned与failed均为0，表示没有尝试逐项计算。

响应带 source、package_sha256、profile_ref、frame、purpose、mode 和 usage=historical_inspection_only。始终authorized=false、robot_ready=false。validate_response可同时传请求，验证身份、顺序、来源、计数、时间、状态原因和成功响应质量/时效约束。它不替代签名、profile文件或网络端点认证。

## 4 样例与兼容

运行 `.venv/Scripts/python.exe -m experiments.scripts.generate_consumption_sample` 生成 examples/consumption 下历史与运行期两组请求/响应。历史样例包括正常空闲、冲突未知、缺块未知、范围外与非法坐标；运行期样例整次拒答。

不改变旧HTTP空间查询、agent-package、LocalPackages或文件安装器。新协议尚无HTTP状态码映射、订阅或事件通道。F06b将定义领域变更集及版本竞争前置条件，F06c定义事件与追溯映射；两者尚未实施。
