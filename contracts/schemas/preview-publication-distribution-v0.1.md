# 固定发布分发控制 0.1

H3b已实现，适用于本机单服务工程预览。发布内容不可变；允许分发与否保存于独立生命周期账本。沿用[受控状态契约](preview-artifact-control-v0.1.md)的报告、修订、引用摘要、原因、Origin校验和追加历史。

## 对象与转换

目标为显式空间内的 `publication:preview-<16位小写十六进制>`。无控制记录默认为active/revision=0，读取不创建账本。

| 当前状态 | 操作 | 结果 |
| --- | --- | --- |
| active（分发中） | pause_distribution | paused（已暂停） |
| paused | restore | active，恢复同一固定发布 |
| active / paused | retire_publication | retired，停止新分发，记录退役原因与替代版本 |
| erroneous retired且无替代 | retire_publication | 补充替代，仍为retired |

使用 `GET /api/artifact-control?space_id=...&artifact=publication:...` 检查，再向 `POST /api/artifact-control/transitions` 提交预期修订、报告摘要、操作与原因。来源或内容证据缺口阻断操作，恢复不能跳过完整性检查。操作不修改publication.json、模型、资产或ZIP，不切换候选/消费版本，不级联改变上游资料或候选。

## 统一准入

HTTP中间件在路由、重定向、条件缓存及静态文件处理前检查 `/publications/{id}`。使用服务器已解码path，统一反斜线及重复斜线；检查所有方法与后缀，包含未知路径。请求准入时核对发布ID、保存归属、模型绑定摘要及控制账本。

| 路径或入口 | 暂停后的行为 |
| --- | --- |
| 无尾斜线、HTML入口、index.html | 409，不先重定向到内容 |
| api/preview、对象列表及详情、checklist、lineage | 409 |
| api/query、api/query-range | 409 |
| 所有成员文件、publication.json、offline.json、offline.zip | 409 |
| HEAD、Range、If-None-Match等条件请求 | 同样执行门禁，不返回304或206绕过 |
| /api/publication-comparisons | 比较任一端暂停时拒绝 |
| /api/publications、空间目录与详情 | 保留管理元数据，暂停项移除files、selection_review及分发URL |
| 成果目录 | 保留发布与来源包的历史条目、lifecycle_state/revision；resources为空 |
| 空间默认入口 | 最近发布暂停时publication_id=null、state=distribution_paused；不自动选择历史发布 |
| 逐空间流程 | 当前匹配发布暂停则发布/空间阶段blocked，下一步指向态势服务 |

所有发布路径及动态 `/api/` 响应设置 `Cache-Control: no-store`。禁止把发布目录或带publication.json的发布快照当作根静态目录启动，避免相同文件另有根路径别名。

| HTTP | 分发准入结果 |
| --- | --- |
| 409 | `publication_distribution_paused`：该发布已暂停 |
| 409 | `publication_retired`：已退役，附reason与replacement_publication_id，未登记替代时为null |
| 409 | `publication_distribution_unavailable`：归属、绑定、模型或账本损坏，停止分发 |
| 404 | `publication_not_found`：发布不存在或ID格式非法 |

非法ID由公共门禁先处理；旧lineage单端点的409预期统一为404。已准入请求仍按原端点契约响应。

## 管理读取与适用范围

生命周期报告保留引用、阻断、修订及历史，以便核查和恢复。内部快照读取用于影响检查，未新增公共内容旁路。工作空间候选与原始资料API属于独立工程访问，暂停某个发布不等于擦除候选或封禁空间。

没有空间归属的旧发布保持active/0，不能通过空间控制接口暂停；不追认或迁移归属。状态枚举与操作在0.1契约中扩展，旧记录仍有效，消费者需识别新的paused及能力标记。

门禁控制准入后的新请求；在暂停前已准入的响应可以完成。已下载、安装或缓存的字节不被追溯撤回，离线消费者可继续工作。重新下载须通过服务器门禁。`no-store`也不能消除此前已持有的副本。

底层工程服务使用本机预览身份；平台入口由认证与场景ACL约束，当前采用模拟身份源验收。控制不构成现场精度验收、生产发布授权或机器人安全放行。跨进程部署、CDN、远端副本撤回及租约另行设计。

## P20退役扩展

上述全路径门禁同样覆盖retired，包括HTML、查询、双视图资产、条件请求和离线导出；管理元数据保留退役原因、替代版本和历史，成果resources清空。退役项不提供日常打开、查询或下载按钮；直接URL返回409及替代标识，不自动重定向或替换请求版本。退役没有一般恢复入口。错误版可先停止分发，替代完成后只补充关联。

认证平台入口由场景权限约束，并记录服务端principal.subject；底层本机预览身份仅为兼容方式。当前验收仍使用模拟身份源，不能据此宣称生产认证已验收。已准入响应和已持有离线副本仍按上文边界处理。
