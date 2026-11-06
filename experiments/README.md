# 技术试验工作区

2026-10-28 最新完成[断点残差与空洞近邻对照](../docs/validation/NYU断点残差与空洞近邻对照-2026-10-28.md)：原输入与排除4px缺失近邻均为56/59条双向边、连续前缀57帧，远距离区域误差更大。106项相关测试、7项隔离运行时测试通过，两轮各191项和残差分区117项独立检查通过。下一步核验距离/量化模型，仍未可信融合或发布。

2026-10-28：已在独立 Python 3.12 / Open3D 0.19.0 环境完成 NYU 60 帧混合 RGB-D 里程计对照，共同前向几何检查 58/59、双向检查 26/59、连续前缀仅 1 帧，暂不融合或发布。见[验证](../docs/validation/NYU成熟RGBD里程计对照验证-2026-10-28.md)及[隔离运行说明](stack/rgbd-open3d/README.md)，证据为 `evidence/2026-10-28/nyu-open3d-002`。

内部交付整合验收入口为`python -m experiments.scripts.delivery_acceptance --output <新目录>`，必须执行31项CLI/真实HTTP检查，页面验收独立保存；见[手册](../docs/guides/内部交付流程验收运行.md)。最终证据在runs/p2-delivery-acceptance-002，不覆盖旧运行，不声明生产或机器人验收。

本地报告受控生成入口为`python -m experiments.scripts.delivery_generate`，见[归档运行](../docs/guides/交付报告归档运行.md)。证据在runs/p2-delivery-archive-001，浏览器脚本为scripts/delivery_archive_browser.js；无Web扫描或自动清理。

本目录用于公开资料核验、输入检查及后续算法试验。证据、试验配置、实现和执行结果分开保存，不将样例结果称为正式真值。

## 输入预检

2026-10-28：新增无需ROS运行时的 `python -m experiments.scripts.inspect_bag_offline`，依赖 `uv sync --locked --extra input`。新烟测为 `python -m experiments.scripts.smoke_bag_offline --output <全新目录>`，实际执行4组CLI容器读取，证据在 `runs/p1-offline-bag-002`；见[契约](../contracts/schemas/bag-preflight-v0.1.md)。下述旧ROS1脚本的历史运行状态不因新适配器通过而改变。

`scripts/inspect_rosbag.py`依赖ROS1 Python环境，接受PointCloud2和Imu话题，输出字段、时间统计、缺失及异常。它不支持Livox CustomMsg的直接检查；该消息需后续适配。它也不验证点时间单位、同步精度、外参、IMU坐标及姿态质量、资料许可或建图质量。

结构检查通过始终不等于算法就绪，报告中的`algorithm_ready`保持false，待更完整的输入审核后再在试验登记中确认。

## 合成日志冒烟验证

`scripts/smoke_rosbag.py`生成三个小型合成ROS1日志：结构正常、缺点时间、IMU时间倒退。它验证正常资料可读取及问题能被预检拒绝，不运行SLAM，不产生产品真值或独立质量结论。

PowerShell使用已下载的官方镜像摘要运行：

```powershell
./experiments/scripts/run-input-smoke.ps1 -Image 'ros@sha256:镜像摘要' -RunName input-smoke-001
```

脚本检查摘要格式，禁用容器网络，限制资源，以只读方式挂载脚本目录，仅写本次运行目录，不挂载设备、不启用privileged。新执行使用新的RunName，避免覆盖旧证据。

基础镜像采用ROS Noetic作为原ROS1候选的隔离兼容试验环境。其上游常规支持周期已经结束，不作为产品长期依赖选型结论；试验通过后仍需评估维护、迁移及安全更新路径。

## 目录

新增`scripts/delivery_audit.py`及`delivery_audit_evidence.py`，将现有文件/恢复审计和目标完整绑定关联为只读报告，见[设计](../docs/architecture/智能体只读交付核对设计-v0.1.md)及[手册](../docs/guides/智能体只读交付核对运行.md)。CLI固定UTF-8 JSON，不建立跨库快照或运行权限。

保存报告后续已接入[只读工作台](../docs/architecture/交付核对工作台设计-v0.1.md)，本批证据在runs/p2-delivery-workbench-001，浏览器断言脚本为scripts/delivery_workbench_browser.js。报告重读与底层重新核对是独立动作；未实现Web实时扫描或写操作。

J4第二批新增`scripts/recovery_concurrency.py`及`recovery_concurrency_evidence.py`，以真实子进程会话和明确屏障验证查询/恢复顺序，见[记录](../docs/validation/智能体查询恢复跨进程验证-2026-10-27.md)。门禁通过的在途响应可能晚于恢复返回，后续旧查询拒绝；不提供机器人动作门禁。

J4首批新增`scripts/recovery_session.py`、`recovery_audit.py`及`recovery_session_evidence.py`，组合固定文件快照与恢复代次，并提供只读元数据CLI，见[设计](../docs/architecture/智能体恢复与文件会话组合设计-v0.1.md)及[手册](../docs/guides/智能体恢复与文件会话实验运行.md)。15项专项通过，尚无真实机器人或维护授权入口。

J3新增`scripts/recovery_state.py`及`recovery_state_evidence.py`，独立新库完成历史重放、计划核对和原子恢复；30项专项通过，见[记录](../docs/validation/智能体恢复状态机验证-2026-10-27.md)。不自动升级J2/v1，不暴露生产维护接口；运行方法见[说明](../docs/guides/智能体恢复状态机实验运行.md)。

J2新增`scripts/recovery_journal.py`与`recovery_journal_evidence.py`，实现独立合成SQLite日志的prepare/apply和五处事务边界证据，见[实现说明](../docs/architecture/智能体消息留存与原子提交实现-v0.1.md)及[运行手册](../docs/guides/智能体消息日志实验运行.md)。原v1入口不变，没有解除未决状态的操作。

J1新增`scripts/recovery_lock_probe.py`和`check_recovery_lock.py`，11个独立Windows场景验证LockFileEx与模拟代次控制，见[记录](../docs/validation/智能体恢复锁与代次原型验证-2026-10-27.md)。要求新的合成证据目录；不接有效性门禁，不提供恢复解除。

R2b第四批`scripts/check_recovery_contract.py`核对设计草案的四类恢复记录结构，4正例、16负例通过，见[记录](../docs/validation/智能体恢复日志契约核对-2026-10-27.md)。不执行锁、验签或事务恢复；样例为占位数据。

R2b第三批增加`scripts/validity_audit.py`，只读观察有效性库和pending标记，摘要匹配不授予清理或恢复。见[运行手册](../docs/guides/智能体故障只读核对运行.md)和[人工恢复条件](../docs/architecture/智能体故障核对与人工恢复条件-v0.1.md)。

R2a的`scripts/trust_proof.py`与`ed25519_probe.mjs`使用Python契约校验及Node原生密码库，验证合成JWS而不授予使用能力。RFC向量、负向输入和依赖下载限制见[记录](../docs/validation/智能体测试证明验证-2026-10-27.md)；生产/机器人密码实现未冻结。

- `evidence/`：官方说明与许可快照、来源及哈希记录。
- `templates/`：试验资料登记清单。
- `scripts/`：输入检查和试验工具。
- `runs/`：每次执行的环境与结果。合成日志不可混入正式数据登记。

真实原始日志与大型镜像不提交代码仓库。后续试验以固定输入、实现、配置及环境关联结果。

## Windows进程所有权原型

`scripts/probe_windows_ownership.py`通过真实父/子进程测试原子Job Object关联、挂起创建、强杀收束及互斥锁。只支持Windows，要求新运行目录；不接入产品任务或数据库。7项首批试验及虚拟环境启动器限制见[验证记录](../docs/validation/Windows进程所有权原型验证-2026-10-26.md)。

`scripts/probe_worker_environment.py`在单进程限制下运行实际检查worker，绑定基础Python与venv、代码及依赖指纹，覆盖正常报告、强杀、环境缺失、指纹改变、非法输入和父环境污染。7项新增试验通过，见[环境记录](../docs/validation/检查worker环境绑定验证-2026-10-26.md)；尚未接入任务事务或恢复。

2026-11-03新增`scripts/verify_preview_lifecycle.py`：从闲置H1副本生成全新运行区，串联资料/批次/候选/发布控制，两次重启、来源缺失注入、两类真实重建及禁网消费恢复。成功结果含HTTP逐请求轨迹和各阶段报告，原区不写。见[复跑说明](../docs/guides/完整生命周期集成验收运行.md)和[验收记录](../docs/validation/完整生命周期集成验收-H3c-2026-11-03.md)。
