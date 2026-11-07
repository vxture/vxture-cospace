# 保存预检历史 v0.1

`GET /api/inputs/{input_id}/preflight/history`，兼容HEAD，仅在平台授权业务入口开放。须有该资料所属场景data.manage，当前会话和订阅有效。客户端可提供space_id进行一致性约束，不能指定Workspace。

参数：`limit=1..100`（默认20），`before_sequence=正整数`或`sequence=正整数`二选一。序号不超过JavaScript安全整数；未知参数422、重复参数403；POST拒绝。记录序号只在当前资料范围解析，其他资料的同库序号返回空列表，不泄露外部记录。

响应含`input_id`、`items`、`next_before_sequence`、`current_files_checked=false`及`consistency=saved_records_not_current_file_validation`。items保留保存报告、sequence、registration_matches和current_files_checked=false；按sequence倒序。列表多取一条决定是否有下一页，next_before_sequence为本页最小序号；指定sequence只返回0或1项。无数据库时不创建，空列表与不可读503明确区分。每个返回报告不超过256KiB。

读取不触发预检、文件校验、任务推进或任何业务写入。registration_matches仅比较登记JSON摘要；源文件必须在构建准入时重检。固定历史序号不代表最近通过，不代替资料生命周期、场景权限或实时准入。

UI深链为`#data?space=...&tab=inputs&input=...&check=...`，原资料ID与序号不变化；普通板块／场景切换不携带check。共用目录最近预检条目增加check，旧链接继续打开原资料详情。错误／不存在的指定记录不得回退最近记录。
