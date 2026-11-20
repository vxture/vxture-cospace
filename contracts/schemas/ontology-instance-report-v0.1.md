# 独立实例校验报告 v0.1

日期：2026-11-20。实现 `packages/ontology/kernel/instances.py`，入口 `validate_instances(raw_bytes, catalog, rule_set=None)`。Catalog 由调用方显式提供；内核不自动获取定义或现场事实。只接受 bytes、有效 Catalog 和 None / park-baseline 规则选择，不接收宿主服务、路径或数据库句柄。

返回字段：

| 字段 | 含义 |
| --- | --- |
| profile | 固定 `vxture.ontology-instance-report/0.1` |
| valid | 无 error 时 true；不是发布、合规、真实性或访问授权结论 |
| instance_sha256 | 按 canonical_bytes 计算的输入文档摘要；解析/预算失败前未算得时为 null |
| library_sha256 | 调用方提供 Catalog 的完整库摘要；非法 Catalog 为 null |
| schema_sha256 | 随包实例 Schema 的规范编码摘要 |
| rule_set | 未选规则为 null；选定时为 rule_set_id/version/sha256 |
| diagnostics | 按 path/code/severity 排序的诊断数组 |

每条诊断为 `{code,path,severity,state,related_paths?}`。path 与 related_paths 使用 JSON Pointer，不携带客户原值、名称、来源内容或本地路径。severity 为 error/warning/info；state 为 not_recorded/unknown/conflict/unsatisfied。

- `geometry_not_recorded` 是 info/not_recorded；允许实体无几何。
- `incomplete_coverage` 是 info/unknown；不完整覆盖不等于对象不存在。
- `disputed_assertion` 是 warning/conflict；保留争议但不用于满足必需关系。
- 规则违反、非法输入、引用缺失等是 error/unsatisfied。该状态描述校验约束，不等同领域事实的真/假。

不是所有领域矛盾都能自动识别。超过基数的不同有效目标返回 cardinality_violation，原始争议必须由来源显式标注 disputed；不能宣称引擎已自动完成证据真伪或所有业务冲突裁决。没有任何 coverage 声明时不推断完整，也不自动生成实体不存在结论。未实现面向地图的查询 API。

## 检查顺序

1. 有界 JSON 解析，拒绝重复键、非有限数值、错误字节、过深/过大输入。
2. 随包 Schema 的封闭子集结构校验，明确检查有效 UTC 日历时间，不依赖可选第三方格式插件。未知 Schema 关键词拒绝，禁止网络解析远程引用。
3. 固定模块版本/摘要和依赖闭包；只在锁定模块中解析概念与关系。额外 Catalog 模块不能补齐未锁定引用。
4. 集合 ID 唯一、来源/证据/实体/坐标系/几何引用；继承属性的必填、类型、非空字符串、最小值、准确单位和量种；关系端点接受声明类型及其子类；有效区间和几何绑定类型检查。
5. 显式选用 park-baseline 时，执行角色有效期、时态基数、空间层级单父及无环规则。引用或端点等前置检查有 error 时不继续推导图结论，避免从坏边产生误导诊断。

角色关系覆盖以半开区间边界逐段检查；同一时段指向同一目标的多份报告不重复计数。角色出向有效关系不得超出指派有效期。非角色完整性在其存在活跃报告的区间检查，不推断对象未声明的存续时间。空间环只在同一时间片判断，不以跨时间合并图代替当前图。

图诊断可能含多个相关位置；缺失关系定位到需要该关系的实体。诊断只承诺指出可核查的位置，不假装缺失输入仍有实体可点击。预算失败可以提前终止，不承诺单次报告穷举所有错误。

## 预算与使用限制

4 MiB 原始字节、32 层深度、Schema 集合上限、250000 工作计数、200 条常规诊断；预算用尽会附加 budget 错误，报告至多 201 条。工作计数为内部资源保护，不是业务配额或产品商业限制；结构上限内的复杂输入也可能因时态图工作量超限而拒绝，调用方应按独立命名空间/时间窗口提供较小自包含包，不能把未完成校验标成通过。

当前无单位换算、地理转换、几何包含/相交推理、观测过期策略、真实来源核验或任意自定义规则执行。图数据库、HTTP、认证、商业权益、实例存储均不属于本接口。

CLI：`vxture-ontology --instances FILE [--library LIBRARY] [--rules park-baseline]`。通过退出 0；校验失败退出 1，报告输出 stdout；定义/文件不可读取时安全错误输出 stderr，不输出本地文件路径。--instances 不可与 --module 同用，--rules 必须与 --instances 同用。
