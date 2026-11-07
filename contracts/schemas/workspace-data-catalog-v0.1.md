# Workspace 共用数据目录 v0.1

`GET /api/data-catalog`（兼容 HEAD）是授权工作台的只读元数据投影，profile 为 `cospace.workspace-data-catalog/0.1`。不改变已有 `/api/inputs`、`/api/artifacts` 等按场景接口。工程预览服务不配置平台授权时不开放此新目录；页面显示服务不可用，不回退为无授权全量读取。

## 请求及授权

可选 `space_id`（明确筛选）、`category=all|original|process|result`、`search`（最多100字符）、`offset=0..10000`、`limit=1..100`（默认50）。未知参数422、重复参数403。工作区只来自当前验证身份，不接受浏览器指定 Workspace。

每次读取重新加载策略并执行订阅和会话校验。候选场景须具备 `data.manage`；显式场景无权限直接403，不能回退其他场景。无可管理场景返回 ready 和空列表，不代表可查看者有数据管理权限。任务还须有 `build.run`，发布还须有 `space.preview`，离线交付入口还须有 `space.export`。已有数据接口的授权保持原状，目录 href 不授予目标操作权限。跨 Workspace 绑定、未绑定和历史未归属记录不进入目录。

## 对象与生命周期分类

| category | kind | 读取依据与定位 |
| --- | --- | --- |
| original | input | 既有登记与说明；保留输入ID，定位场景资料详情。已有模型作为构建输入时仍在本分类，界面称“原始与输入”，不伪称传感器原始采集 |
| original | attachment | 场景配套原文件记录；定位该场景配套资料列表，再选择具体原文件 |
| process | batch | 既有封存／草稿／停用批次及其ID，定位该批次 |
| process | preflight | 最新保存的预检证据；投影 record_id 为 input_id@sequence，通过check固定序号定位原输入的历史记录；登记变化标 registration_changed，不重新预检 |
| process | job | 直接读取保存 job.json，含运行中、失败和中断；不调用 jobs.list/poll；定位原任务 |
| result | candidate | succeeded 任务的候选记录声明，不读几何或声称快照可用；定位既有场景版本详情 |
| result | human_view / agent_view | 同源 model.json 中的视图声明；保留其模型ID及父级定位，key 用 kind 区分，不复制文件或构造新业务身份 |
| result | publication | 固定发布保存记录；定位原固定发布。记录存在不等于当前分发可用 |
| result | offline_package | 有导出权限的发布交付入口，state=export_on_request；不是已生成包或导出历史，点击进入原服务页面执行原门禁 |

本批查询原始／过程／成果的现有可访问对象。未持久化的算法中间产物、点云显示分块的全量资产化、跨场景复用写入、导出历史和消费设备状态未新增。N12已补资料详情的[完整预检历史](preflight-history-v0.1.md)，目录仍仅索引最近一条。IFC 原文件可作为配套资料管理；IFC 构件解析结果仍在原关联工作面，目录不将其伪造成已登记构建输入。

## 响应与完整性

`spaces` 仅包含本次授权管理范围的 id/name；`items` 含 key、record_id、space_id、space_name、category、kind、label、state、created_at、integrity、href。key=`space_id/kind:record_id` 是投影定位键；原ID和固定引用不迁移。href 为已授权记录的站内模块链接，无文件路径、原始错误日志、账户凭据、模型几何或内容下载。

所有条目 `integrity=metadata_only`；目录不验证几何成员摘要、输入原文件或固定发布内容，不能用于构建／发布／分发准入。详情继续执行原完整性与生命周期门禁。候选与视图可以同时出现，计数是条目数，不是文件去重数或存储用量。

`counts` 为当前范围和搜索结果下三类计数，先于 category 筛选；`total` 是 category 筛选后的总数。按 key 稳定排序，`offset/limit/next_offset` 提供有界分页；请求间新增／删除可能移动位置，非事务快照。`workspace_id/space_id` 明确范围，`observed_at` 是读取时间。

保存记录不可读时返回 `status=partial` 与成功读取条目，`issues` 仅含 source、可确认且有权的 space_id 或 null、通用错误码；不能确定归属时不暴露具体记录ID、路径或数量。无法确定完整目录不能显示“全部完成”或“确认无数据”。认证／策略不可用沿用503；请求预算超限503 `catalog_budget_exceeded`。扫描保存记录最多10000项，每份 JSON 最多256KiB，输出最多10000项，单页最多100项；超限不静默截断为完整结果。

`consistency=request_time_metadata_reads_not_transactional`，`source_files_rechecked=false`，`consumer_state_checked=false`，`delivery_history=not_recorded`，`quality=unverified`。不创建数据库、目录、任务、选择、检查、发布或包。批次和附件读取沿用其只读校验；底层内容相同不改变跨场景归属。

## 页面范围

`#data` 独立打开全部授权场景的数据；普通模块跳转仅带场景时，将其作为可清除的初始筛选。`scope=all` 明确共用工作面，`filter_space/category/search/offset` 保存在 URL；`space` 可作为返回上下文，不能替代实际 filter_space。`#data?space=...&tab=inputs` 及已有记录深链仍进入原场景操作页，提供返回共用目录入口。

语义本体独立工作面不再依赖场景目录读取。共享模板与 Workspace 私有规则继续由既有 ontology-authoring 授权维护，场景仅为返回关联的上下文。固定规则引用不随切换自动替换。
