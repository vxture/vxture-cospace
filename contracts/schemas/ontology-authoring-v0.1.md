# 独立本体编制与版本服务 v0.1

日期：2026-11-20。B04a 服务内核与参考存储端口。实现为 `packages/ontology/kernel/authoring.py`，独立包导入 `vxture_ontology.authoring`。B09e 将可选 SQLite 适配器收敛到 `vxture_ontology.adapters`，保留 CoSpace 的兼容导入、数据库文件名和数据格式；当前由 CoSpace 注入身份与权限，不运行第二套本体服务。

同日 B04b 增量：已通过宿主适配器接入 `/api/ontology-definitions` 与详情页 DS 业务表单、版本/发布抽屉；以下 B04a 纯服务与存储协议保持不变，HTTP 细则见本文末尾。目录日期改为真实发布记录，不影响定义内容成熟度。

## 边界与装配

`DefinitionAuthoring(port, authorize=..., clock=...)` 通过显式注入的存储事务端口和授权函数提供编制用例。内核不导入 SQLite、HTTP、平台身份、场景、地图或商业权益；存储端口可替换。独立 wheel 提供可选的 SQLite 适配器，既可复用也可替换为符合端口的实现。

授权函数 `authorize(scope, actor, action)` 仅返回严格 True 才允许；action 为 read/edit/submit/review/publish，由宿主把真实可信身份与权限映射到该接口。scope/actor 必须由认证宿主提供，绝不信任浏览器提交的用户名称或自由构造的作用域。每次操作和幂等重放均重新检查权限。示例和测试中的角色名称只是测试数据，不是生产权限策略。

时钟默认 UTC，可显式注入可信时钟便于测试；不接受浏览器指定发布时间。此处的 scope 是存储分区，不是平台订阅或商业配额。

## 操作契约

| 操作 | 输入要点 | 结果 |
| --- | --- | --- |
| save | scope/actor/request_id、module_id、expected_revision、bundle、base_reference? | 保存当前草稿，返回修订、摘要、定义包、来源基版、时间与操作者 |
| read_draft | scope/actor/module_id | 当前草稿副本 |
| validate | scope/actor/module_id/revision | 当前修订的 valid、draft_sha256、可定位 diagnostics |
| compare | scope/actor/module_id/revision | 与显式基版的结构差异：path 和 added/removed/changed |
| submit | scope/actor/request_id、module_id、expected_revision | 固定提交快照及摘要的 pending 审批单 |
| read_review | scope/actor/review_id | 含原始提交定义包的审批单，可在草稿后来修改后继续查看当时内容 |
| decide | scope/actor/request_id、review_id、decision=approved/rejected、reason | 绑定原修订及摘要的审批结果 |
| publish | scope/actor/request_id、review_id、expected_revision | 发布记录，冻结完整依赖包 |
| read_release | scope/actor、精确 reference | 不可变发布记录和定义包 |
| list_releases | scope/actor/module_id | 该模块版本及真实发布时间，按数值版本降序 |

request_id 为 32 位小写十六进制。相同作用域中同一请求 ID，只允许同 actor/action/规范化 payload 重放；不一致返回 request_conflict。每个请求结果持久保存，不因网络重试重复送审、修改修订或发布。返回深复制，调用方不能直接修改存储状态。

## 草稿与校验

每个作用域每模块一个当前草稿，首次 expected_revision=0，其后必须匹配当前整数修订。None、布尔值和字符串不能绕过并发控制。相同修订的并发写入只能一个成功，失败返回 revision_changed。没有新增“修改记录”页面。

草稿允许语义不完整的中间编辑，例如暂时失效的上位概念或关系引用；保存仍要求 JSON 可规范编码、1 MiB 内、正确库载体、模块 ID 不重复、目标唯一且具有合法版本/status=draft。完整字段、概念/属性/关系、依赖和继承由单独 validate 检查；不能把保存成功显示为校验通过。

validate 调用独立 Catalog，必须是目标模块及其准确依赖闭包，不允许混入无关模块。此处是定义校验，不是 B03 的现场实例包校验。差异比较是结构比较，不声称自动证明实例兼容；依赖变化、删除或必填变化需后续消费方影响评估。

## 审批与发布

送审前再次完整校验，并确认所有依赖已在本作用域中按准确版本和摘要发布。内置候选定义不是自动发布的版本；如需导入，必须显式执行保存、送审、审批和发布流程，先依赖后目标。

审批单存提交时的定义包、修订和摘要。审批者必须与送审者不同；自审拒绝。草稿改动后旧 pending 审批无法批准，旧 approved 审批无法用于发布。驳回后要重新送审，不能修改旧审批单来变成通过。实际权限角色由宿主决定，测试用虚拟审批不构成真实专业审核。

发布前再次校验、检查审批、修订和摘要，并要求新版本在数值上高于该模块所有已发布版本。模块 ID + version 唯一，已发布版本不能覆盖；即便内容相同也只能用原请求 ID 重放取得相同结果。发布记录包含精确 module reference、定义及依赖闭包、bundle_sha256、发布时间/操作者与审批快照。读取时检查定义及整包摘要，错误引用明确失败，不返回最新版替代。

新草稿可以基于明确的历史发布 reference：版本必须推进，base_reference 一般保持不变。一个当前草稿完成发布后，可以把刚发布的版本设为下一轮基版；只有该基版内容与当前草稿摘要相同才允许这一切换。这样既保留当前编辑并发修订，也保留旧发布记录。

发布 envelope 的 `state=published` 表示经过上述治理流程并冻结了一个可取回工件；定义 profile 0.1 的 `status=draft` 仍表示内容语义成熟度为候选，两者分离，不改动内容字段伪称专家签核或外部标准正式等价。CoSpace 当前目录没有接入这些发布记录，继续显示“草案/未发布”；B04b 必须明确展示工件发布状态与内容成熟度，不得仅因有时间字段就自动把全部候选概念标成正式标准。

## 存储端口

`AuthoringPort.transaction(scope)` 是上下文管理器，yield 当前分区的可变字典。port 必须串行化该作用域所有修改，成功时原子提交，异常时完全回滚。状态含 drafts/reviews/releases/receipts 四个映射；端口受信任，服务返回值与其内存状态隔离。不能把无锁进程内字典当作并发持久存储。

SQLite 参考实现使用注入 root 下的 ontology-authoring.sqlite3；scope 用 SHA256 转为分区键，BEGIN IMMEDIATE 串行事务、10 秒等待。单分区 JSON 状态最多 16 MiB，超过时回滚并返回 state_budget。该限制是参考适配器保护，不是商业权益限制。它不提供海量版本索引、跨进程审批通知、分片、备份恢复或收据清理；生产大规模存储应替换适配器，并保持相同事务语义。

端口和文件系统仍由宿主保护；摘要不是数字签名，不能抵御有数据库写权限者同时伪造内容和摘要。原有旧 preview 版本库、场景核验及正式发布链路保持兼容，未在本批迁移。

## B04b 接入要求

对象页中区分查看、编辑、送审、审批和发布，不添加数据导航或二次导航。编辑概念/属性/关系采用现有 DS 表单/抽屉，不把 JSON 原文编辑器作为普通业务入口。HTTP 必须先认证授权并验证 CSRF，再把可信 scope/actor 注入上述服务；分页目录须按真实发布记录显示日期，历史定义按准确引用读取。页面接入前不能启用假保存或假发布按钮。

## B04b 已实现的宿主 HTTP

`GET|HEAD /api/ontology-definitions?module_id=...` 返回 `vxture.ontology-workbench/0.1`：can_manage、source_bundle、draft、releases、reviews、validation、comparison。普通业务用户只能读取已发布/内置候选定义与发布版本摘要；私有草稿、审批和基版差异仅工作空间管理者可读。source_bundle 来自准确发布快照，未发布模块使用原内置候选定义。

`GET|HEAD /api/ontology-definitions?module_id=...&version=...&sha256=...` 返回准确发布版本的定义与依赖闭包，保持现有目录响应格式，供 parseLibrary 消费。准确匹配的原内置引用仍可读；其他不存在的引用明确失败。

`GET|HEAD /api/ontology-definitions?review_id=...` 仅管理者可读取当时送审的固定定义包，与当前草稿分离。该端点不把 rejected/pending 草稿开放给普通读取者。

`POST /api/ontology-definitions` 接收 action：save/validate/submit/decide/publish，字段与上表相同，未知字段拒绝；validate 不接收 request_id，其余操作必须有。所有写方法沿用平台认证、工作空间管理权限、Origin/CSRF 和会话有效性检查。scope 由可信 issuer/org/workspace 编码，actor 来自主体，不接收浏览器指定身份或分区。此首版管理者可执行各治理操作，但不能批准自己的提交；更细的编辑/审批/发布角色可由宿主后续映射，不在纯内核硬编码账号。

所有响应 Cache-Control=no-store。未认证 401、无权/CSRF 不满足 403、字段非法 422、修订/审批/版本冲突 409、存储或定义损坏 503。错误不携带私有文件路径。重复 query 沿用宿主统一拒绝。

目录 `/api/ontology-resources` 在可信作用域内叠加各模块最新已发布版本，只把它用于摘要显示；不能把多个各自依赖旧版核心的目录条目拼成一个可解释定义包。`/definition` 始终通过对应发布快照返回自身闭包，因此通用核心升版不会使旧领域版本改用新核心。草稿保存不改变目录共享定义或发布日期。

首版业务表单从现有模块进入，支持元数据与概念/属性/关系新建、编辑、从草稿移除，依赖选择仅引用已发布版本。整体新模块创建向导、任意文件导入、批量编辑、依赖影响分析、正式专业标准成熟度工作流不在本批范围；不宣称完整行业标准治理平台。

## B09a 便携工作台接口

`vxture_ontology.workbench.DefinitionWorkbench(port, scope, actor, authorize=..., templates=None, clock=None)` 将受信上下文绑定到接口。可注入 `Catalog` 作为宿主模板；省略使用内置库。它暴露 `read(module_id)`、`change(command)`、`released_library()`、`definition(reference)` 和 `review_definition(review_id)`。这些方法复用本章的字段、响应和精确版本规则；`released_library` 是目录视图，不能当成可互换的依赖闭包。

读取目录、模块与固定版本先校验 `read`；草稿、验证细节和送审记录还要求工作台权限 `read_private`。工作台 `can_manage` 表示可查看编制信息，`can_decide` 还要求 `review` 和可审批状态。写命令按既有操作逐一校验，宿主可区分编辑、送审、审批和发布。底层 `DefinitionAuthoring` 是可信宿主接口，其原有 `read` 语义包含私有操作；客户端接入应使用工作台或实现同等的额外授权。CoSpace 继续把原管理权限映射到 `read_private` 和各写操作，URL、响应及存储兼容。

工作台模块详情从一次作用域事务中读取，返回的一组草稿、审批摘要、诊断与差异基于同一快照。支持读取已冻结的历史版本，不能把模板当作已发布依赖；独立宿主也必须使用不同的可信审批者，不能以表单字段代替身份。
