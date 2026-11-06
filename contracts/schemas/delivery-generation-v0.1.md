# 交付报告生成上下文 v0.1

日期：2026-10-27。配套[JSON Schema](delivery-generation-v0.1.schema.json)。用于cospace.test-delivery-audit/0.2的必填generation字段；外层0.1继续兼容，不允许携带非null的generation。它不是签名、运行授权或正式交付证明。

| 字段 | 语义 |
|---|---|
| report_id | 每次scan新建规范UUID4；刷新保存文件不产生新批次，不承诺全局注册或去重 |
| producer | 固定名称cospace.delivery-audit，版本0.2；声明而非认证身份 |
| interval.started_at/finished_at | 生成端普通系统时钟，UTC微秒字符串，以Z结束；包围扫描及上下文计算，不含输出文件写入 |
| interval.elapsed_ms | 本进程单调计时差，整数毫秒；不与普通时钟差值强行相等 |
| interval.wall_end_before_start | 结束时钟早于开始时钟时为true，保留原始时间；只能发现端点倒序，不能检测所有时钟跳变 |
| interval.clock/consistency | 固定system_utc_untrusted及independent_readonly_snapshots；不声明可信UTC或跨库快照 |
| limit | 本次扫描采用的1至200限额 |
| binding_sha256 | requested_binding规范JSON摘要 |
| payload_sha256 | 外层报告移除generation后全部内容的规范JSON摘要，包含schema_version及完整组件原报告 |
| sources.files/journal.locator_sha256 | 生成端normcase(abspath(root))字符串的规范JSON摘要，原始目录不输出；不解析成物理设备身份 |
| sources.files/journal.component_report_sha256 | 对应组件原报告的规范JSON摘要，不是整个库或文件系统的摘要 |
| sources.journal.control | 从原恢复组件报告提取的store_id/context/generation/mode/revision/state_sha256；不可读或格式无效为null |

规范JSON复用packages.data.imports.canonical：UTF-8、键排序、紧凑分隔符、不转义中文、不接受非有限数字。所有SHA-256为小写64位十六进制。Schema检查结构；运行校验另检查日期真实存在、UUID规范及版本、时钟倒序标志、绑定/内容/组件摘要、日志身份与原组件一致。Schema单独通过不代表这些领域检查通过。

保存报告读取先校验原始对象及关联摘要，再做Web投影，不以过滤后的组件重新验算。API仍使用cospace.saved-delivery/0.1封装，新增report.generation可空字段；source.read_at只表示读文件结束，source.observed_at保留null，因为多个组件没有单一观察时刻。时间区间在generation.interval内展示。

摘要是无密钥校验，编辑者可整体重新计算；不能认证来源或检测有意伪造。目录指纹相同不证明未换库，迁移目录会改变指纹；字典猜测路径也可能恢复指纹来源，不承诺匿名化。组件及日志身份仅说明报告当时读到了什么。日期晚于读取端、时钟偏移或长时有效性本批不判断，不自动显示有效/过期或解除门禁。

本批没有追加数据库字段、持久批次注册、报告选择器、Web生成或历史迁移。旧报告缺上下文必须显示未记录；不得从mtime、HTTP时间或读取时刻推导。
