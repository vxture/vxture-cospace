# CoSpace 平台上线与用量接入

更新日期：2026-11-07。此记录取代早期套餐策划中“未批准、未发布”的当前状态描述；早期 proposal JSON 保留为历史策划输入，不作为平台配置或运行时权限数据。

## 已完成的平台登记

- CoSpace 独立 L2，认证留在 accounts.vxture.com，正式域名 cospace.ruyin.work。
- 应用位于 worker02，正式端口 3260；3261 预留。发布必须经过 GitHub PR、必需检查、release tag 和 production Environment 审核。
- Admin 已发布三个套餐 v1，页面标记 V1.20261106，用户已确认价格和额度：

| 项目 | Pro | Business | Enterprise |
| --- | --- | --- | --- |
| 月付 | ¥399 | ¥1,499 | 联系销售 |
| 年付 | ¥3,990 | ¥14,990 | 私有化部署合同 |
| 成员 | 1 | 5 | 按合同 |
| 场景空间 | 3 | 10 | 按合同 |
| 存储 | 20 GiB | 100 GiB | 按合同 |
| 每月 AI 点 | 500 | 2,500 | 按合同 |

三档均包含六个软件模块，不包含地面采集处理工程。Enterprise 无公开结账价格，不使用邀请订阅替代联系销售。席位、商业额度和加油包均由平台负责。

- Atlas chat/default 模型路由授权、Runos k-dense-ai.geopandas（read）授权已登记；此事实不代表产品已调用这些服务。
- Webhook 地址与签名设置已登记；密钥只在私有运行配置，不进入 Git。

## 产品用量实现

首次使用同时修正：经过平台 C2 授权的 Workspace 所有者可直接创建本 Workspace 的场景，不要求在本机重复登记商业白名单。普通成员仍需要产品内的创建授权，预置来源资料仍受独立配置控制，不能因订阅自动读取其他 Workspace 的场景或工程样例。工程预览模式保留原来的显式配置规则。

生产组装启动两个互不依赖的后台任务：开通记录对账、存储快照上报。两者启动即运行，随后每 300 秒重试。单次存储统计失败不发送部分结果；某个 Workspace 发送失败不阻止其他 Workspace 上报，也不影响用户业务请求。

存储使用 `PUT /usage/gauge`，通过 CoSpace 自己的 Workspace 绑定 S2S 票发送：

- `product=cospace`、`metric=storage.bytes`、实际非负整数字节数、UTC `observed_at`。
- 归属来自可信场景 policy binding；包括该 Workspace 场景的原始输入载荷、tracking 文件、保留的构建目录、发布目录。历史/退役但仍存储的文件继续计入。
- 同一路径在同一 Workspace 只计一次；发布复制文件是独立存储，分别计入。统计逻辑字节，不使用磁盘块分配大小。
- 排除全局元数据、共享本体、认证状态、日志系统、容器镜像、上传暂存和无归属的工程样例。构建目录内的运行日志作为场景文件计入。
- 零字节只对存在可信场景绑定且完整扫描成功的 Workspace 上报。没有绑定的 Workspace 不推断为零。
- 遇到丢失文件、跨根路径、符号链接、跨 Workspace 共用同一路径等歧义，整轮扫描失败并等待重试，避免错误归属或假零值。
- 绝对值快照允许真实占用减少；`applied=false` 是合法的旧快照响应。下轮重新测量，不累加重放。

`UsageTransport.consume` 按平台协议支持 `POST /usage/consume`、持久业务操作提供的幂等键、`intent=report`，把 `gated` 作为返回信息。当前没有调用这个方法的几何业务操作，也没有新增商业计数指标。不得为点亮上线检查而调用测试指标、发送零消费或虚构 AI 用量。未来实际计数操作必须先定义平台指标，并在该业务操作中持久保存重试键。

`storage.bytes` 永不进入 consume；`member.max`、`scene.max` 是授权数值，不能当累计消费。Atlas/Runos 负责其真实调用的计量，产品不得重复上报 AI 点数。产品不因上报结果建立本地额度门控。

## 上线与验收边界

用量上报实现已随 v0.1.4 正式部署：PR [#14](https://github.com/vxture/vxture-cospace/pull/14) 已合并，提交 `b0e55b46596dc02a90e631d5a8275de863dc58b5`。main 检查通过，JUnit 记录 2,038 项，失败／错误为 0，跳过 116 项；CodeQL、SonarCloud 检查通过。用户批准 production Environment 后，[部署运行 42217913743](https://github.com/vxture/vxture-cospace/actions/runs/42217913743) 成功。

只读核验 worker02 `/srv/md0/cospace`：`cospace-app` 健康，3260 端口，VERSION 与 OCI revision 均对应上述提交。镜像摘要为 `sha256:8810eb27c157b29a9bd23c8b7df33faf2ed2f0dc71b55036be11f1f55d2be2df`。本机核验记录为 `output/worker02-v014-release-acceptance.json`，不提交运行证据或私有配置。

2026-11-06 15:52 UTC，使用无 Cookie、无认证、禁止跟随重定向的客户端检查正式域名，8 项通过：

| 路径 | HTTP | 核验内容 |
| --- | --- | --- |
| `/` | 302 | 首页跳转响应 |
| `/workbench/layout.html` | 200 | 工作台静态页面可读 |
| `/api/auth/config` | 200 | 认证、业务授权、订阅授权均启用 |
| `/api/auth/session` | 200 | 未认证，`authority_state=signed_out` |
| `/api/subscription` | 401 | 需要认证 |
| `/api/spaces` | 401 | 需要认证 |
| `/api/workspace-scenes` | 401 | 需要认证 |
| `/auth/callback`，无参数 | 400 | 拒绝无效认证回调 |

所有响应均有 `Cache-Control: no-store` 与 `X-Content-Type-Options: nosniff`。本机记录为 `output/v014-public-boundary-acceptance.json`。这些检查只确认公开入口及未登录边界，不代表已完成正向登录、订阅或所有安全项验收。

Opera 环节 2 是实现准备的人工确认；环节 4 是真实租户观测。不能把代码测试、套餐发布或存储 gauge 等同于已产生真实 consume 事件。平台当前环节 4 只识别 consume 事件，对仅存储 gauge 和委托服务计量的产品可能存在检查适用性问题，应如实记录，不能伪造上报补齐。

2026-11-06 时产品仍为草稿，Opera 无法登录，尚未发生订单、付款或正向订阅业务验收。该日独立推进的 Anoeta 本机样本验收见 `docs/validation/Anoeta-HL2流程验收-2026-11-06.md`。以下为恢复登录后的更新。

## 2026-11-07：v0.1.6 部署与平台上线

用户批准 production Environment 后，[部署运行 42353962377](https://github.com/vxture/vxture-cospace/actions/runs/42353962377) 成功，正式版本为 [v0.1.6](https://github.com/vxture/vxture-cospace/releases/tag/v0.1.6)，提交 `efa0ac139631faff7baca01a8eb87b0826f8b39a`。应用仍位于 worker02 `/srv/md0/cospace`，端口 3260；`cospace-app` 健康，VERSION 与 OCI revision 匹配。镜像摘要为 `sha256:08be2f481a69d52915f3202c99f3fd6b8108e9005d8bed65fce12187d91043f8`。

部署验收记录：20 项公开 HTTPS、认证配置与匿名访问边界检查通过；7 个既有静态／配置文件匹配，3 个 SQLite 数据库 quick-check 通过。运行证据存于忽略目录 `output/`，不作为源码提交。这些检查不等同于付费订阅后的业务验收。

平台操作结果：

| 项目 | 实际状态 |
| --- | --- |
| Opera 产品生命周期 | 用户完成 TOTP 后，“确认上线”成功，产品显示“已上线” |
| 接入检查环节 1–3 | 登记配置、上线前接入准备、发布套餐已完成 |
| Admin 成熟度 | 公测版；官网中文主张、价值说明、正文已保存 |
| 官网定价页 | 三档可见；Pro 与 Business 的月付、年付价格符合上表 |
| Enterprise | 显示“定制／团队 · 私有化／联系销售”，没有线上订阅按钮 |
| 正式域名登录 | 统一登录成功；未订阅 Workspace 被正确挡在业务入口外 |
| 正向订阅验收 | 等待用户在平台完成订阅；尚未确认订单、付款、开通回调或业务成功 |
| 正式版门槛 | 尚未满足：仍需真实有效订阅及适用的用量验收 |

已核验官网入口：<https://vxture.com/zh-CN/pricing?product=cospace>。用户选择自行完成 Ruyin Studio / default workspace 的 Pro 月付订阅；准备的结算页金额为 ¥399，自动续费关闭。记录结算页不代表订单已提交或支付成功，付款和 TOTP 均由用户本人处理。

平台将产品生命周期与成熟度分开管理：“已上线”不等于“正式版”。预览版不开放新订阅，公测版允许订阅；真实订阅并使用后，Opera 复验记录才能作为 Admin 转正式版的依据。不得绕过门槛直接写数据库或把人工准备确认当成真实使用。

本次只读核对平台实现，确认 C3 接入信号查询的是 `metering.usage_events`，未查询存储 gauge。CoSpace 当前真实上报为 `PUT /usage/gauge`；因此即使存储上报成功，也不能据此宣称 C3 检查通过。这个适用性差异须由平台明确处理，产品不发送虚构消费、不新增重复 AI 计量，也不在产品侧实现商业配额管理。

后续验收顺序：平台确认有效订阅 → 正式域名重新检查权益 → 确认真实开通／回调与回执 → 同一 Workspace 创建场景、上传资料、构建和交付 → 核验真实存储上报 → 平台复验并按适用结果转正式版。
