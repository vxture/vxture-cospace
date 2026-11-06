# 空间成果目录 v0.1

归属：构建 → 数据管理。`GET /api/artifacts?space_id=SPACE_ID`提供当前空间的只读目录，聚合登记资料、模型候选、固定发布及按需离线包入口。省略space_id仅查询历史未关联范围，不回退到任何已关联空间。响应结构见[JSON Schema](preview-artifacts-v0.1.schema.json)。

## 分类与标识

| kind | classification | 数据来源及语义 |
| --- | --- | --- |
| input | registered_source | 已登记封存来源；不是新采集批次或已通过本次预检的原文件 |
| candidate | geometry_candidate / semantic_candidate / candidate_unknown | 仅已成功任务形成候选项；实际模型语义快照决定几何/语义分类，损坏时不猜分类 |
| publication | fixed_publication | 独立固定发布快照，原候选丢失仍可独立完整 |
| offline_package | offline_export | 完整发布对应的按需导出入口，目录查询不生成ZIP，不表示已下载、安装或激活 |

每项`key=kind:record_id`。候选ID、发布ID仍使用原记录ID；离线包使用对应publication_id作为record_id，以kind区分。key是目录定位键，不替代模型摘要或包内容摘要。相同几何的多个语义候选、同一候选的多次发布保持独立条目，不按内容合并。

## 响应信封

| 字段 | 定义 |
| --- | --- |
| profile | cospace.preview-artifact-catalog/0.1 |
| space_id / project_id | 明确归属，历史未关联范围省略 |
| observed_at | 本次读取时刻；不是成果创建时刻，也不表示原数据新鲜度 |
| items | 四类成果条目，不包含失败、排队、运行中或中断任务 |
| relations | 当前目录内的来源关系及一致性状态 |
| counts | 四类实际条目数，包含不可用候选/发布；损坏发布不生成离线包入口 |
| job_counts | 各任务状态计数，读取保存文件，不轮询任务或推进状态 |
| selection_status | not_selected、matched、missing_or_mismatch；不更新所选候选 |
| consistency | request_time_file_reads_not_transactional；多文件请求时读取，不是事务快照 |
| source_files_rechecked / consumer_state_checked | 均false |
| quality / robot_ready | unverified / false |

条目字段包括key、kind、record_id、label、classification、state、created_at、integrity、problems、resources、selected，可选format和model_manifest_sha256。目录不返回原始资料的本机路径。

`created_at`仅采用已保存任务/发布记录的时间。现有输入登记没有时间，离线包尚未生成，均为null，不用文件mtime或页面读取时间补造。

## 完整性与可用性

| integrity | 含义 |
| --- | --- |
| record_only | 登记记录可读取，未复核原文件 |
| snapshot_verified | 当前模型或发布快照文件、声明及记录绑定检查通过；不是质量验收 |
| unavailable | 成员、记录或空间绑定不可用/不一致；problems给出分类码，隐藏预览/下载资源 |
| not_generated | 发布可按需导出，目录没有生成包或计算包摘要 |

候选校验包括模型成员摘要、模型与任务ID和空间、保存输入绑定一致性；选中标识还要求当前选择摘要与此候选清单摘要一致。固定发布复用发布快照读取校验，检查成员摘要与长度、模型/发布空间、候选ID、模型清单与几何来源绑定。

没有原候选或输入记录时，完整发布仍显示snapshot_verified，来源关系分别标为缺失。损坏候选保留不可用条目；损坏发布没有离线包入口。不可读取且无法判断空间归属的JSON记录导致整个请求409，不静默返回一个看似完整的目录。未提交的.pending任务目录排除在外。

## 来源关系

| relation | from → to |
| --- | --- |
| built_from | 候选 → 登记资料 |
| annotated_from | 语义候选 → 标注基线候选 |
| published_from | 发布 → 原候选 |
| sourced_from | 发布 → 快照保存的输入登记，独立于原候选是否仍存在 |
| exported_from | 按需包入口 → 固定发布 |

每项关系包含`from`、`to`、`relation`、`status`。两端以目录key表示。matched表示相关保存记录/摘要一致，不代表重新验证源传感器文件；missing表示已保存引用但当前范围无对应成果；unrecorded表示历史没有保存引用；mismatch表示当前记录、摘要或空间不一致。缺失、未记录或跨空间时to为null；跨空间引用不得变成可点击的其他空间链接。

登记绑定比较去除原始snapshot/tracking路径后的完整记录，并检查模型来源的snapshot摘要及轨迹摘要，或激光的bag摘要与selected_frame。语义基线比较candidate_id＋model_manifest_sha256及任务保存的基线引用；发布候选比较固定模型摘要。不会按路径、同名标签或相同几何猜测历史来源。

`exported_from=matched`只表示导出入口归属明确发布。调用已有offline.json/ZIP接口时才实际生成包内容与摘要；目录不保存导出历史或消费状态。

## 资源与页面

resources只提供服务相对URL：登记详情、固定清单、预览、包信息或包下载。页面结合space_id和record_id定位登记预检、构建任务、态势服务；固定空间在新标签页打开。

数据管理默认显示成果目录，登记资料保持原入口；`#data?space=...&artifact=kind%3Aid`定位成果关系，旧input链接仍打开登记预检。更换空间、刷新失败、错误空间响应时清空旧结果；中止旧请求防止迟到响应覆盖新空间。

404：空间不存在；503：未配置构建服务；409：目录基础记录无法读取或结构不合法。接口不创建选择目录，不轮询/修改任务，不复核原文件，不导出ZIP，也不初始化消费库。当前本机工程环境尚无真实身份与服务端空间ACL。

## H3a兼容扩展

显式空间目录的input/candidate项附加可选lifecycle_state（active/disabled/archived）和lifecycle_revision，不改变原state或来源。停用/归档项继续保留为历史目录；新使用门禁独立执行。无状态记录默认active/0，读取不创建控制账本。控制账本损坏时拒绝目录读取。见[受控状态契约](preview-artifact-control-v0.1.md)。

## H3b兼容扩展

固定发布与其来源offline_package项附加lifecycle_state（active/paused）及lifecycle_revision；包继承来源发布状态，不另设控制记录。暂停项保留来源与历史，resources为空；直接分发路径同样执行服务端门禁。见[固定发布分发控制](preview-publication-distribution-v0.1.md)。
