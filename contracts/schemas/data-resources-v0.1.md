# 平台数据资源目录 v0.1

状态：D02 目录、项目视角和显式资源登记已接通；D03a 扩展固定版本共享 / 参考关联，D03b 增加独立于场景的项目级 / 共用资料上传。

## 资源与来源

`GET/HEAD /api/data-resources` 读取当前可信工作区内、当前身份具有场景 `data.manage` 权限的资料和成果元数据，不读取点云、模型等几何载荷。稳定 `resource_id` 为 `resource-` 加 32 位小写十六进制，由可信 `(issuer, org_id, workspace_id)` 作用域和来源身份计算。相同内容的不同来源不自动合并归属或许可。

输入、参考附件、已有模型及双表达可以成为资源。已有 `ply_pointcloud` 输入归空间成果，其余受支持采集输入归采集资料，附件归参考资料。基础数据是登记用途标记，保留原资源类型。任务、预检和批次仅在处理记录查询中出现，无资源身份；发布操作和未生成离线导出入口不计入资产。

旧资源未登记时 `registered=false`、`owner_project_id=null`，不按场景所属项目推断管理归属。登记保存在既有 `business-projects.sqlite3` 的 `data_resources` 和 `resource_changes` 表；初次写入建表，读取不创建数据库。旧场景、输入、构建及发布的来源文件保持不变。

## 读取契约

参数：`category=all|base|acquisition|reference|result|process`，可选 `project_id`、`space_id`、`search`，`offset` 默认 0、最大 10000，`limit` 默认 20、最大 100。标识必须符合项目 / 场景稳定 ID 格式，检索最多 100 字符；未知参数拒绝。

响应 profile：`cospace.data-resources/0.1`。返回 workspace_id、category、project_id、space_id、items、spaces、total、分页、can_manage、observed_at 和 status/issues。`status=partial` 表示部分来源无法读取，不能把缺失视为完整空目录。继承既有目录的 10000 条扫描预算，超限返回 503；本批尚未建立面向更大规模的独立查询索引。

资源行包含来源定位、类型、来源场景、当前场景主项目、独立管理项目、基础用途、资源登记修订、已登记版本数量、当前来源版本是否已登记及可管理资格。项目筛选同时纳入该项目管理资源和该项目当前关联场景的可读资料；场景重新关联不会转移已登记管理归属。这里的场景业务关联不等同于 D03 的资源使用授权或使用记录。

`source_version.version_id` 是来源元数据的固定摘要，`reference_kind=source_metadata`；形成时间、格式、大小只取现有元数据，缺失为 null。无效字段不返回为可用资源，并标记 partial。`source_files_rechecked=false` 明确没有重验载荷字节，也不据此声明现场质量或空间精度。来源元数据变化显示待登记，旧版本摘要和记录保留；不自动升级任何消费方。

项目目录与登记内容在同一数据库读取事务中关联；来源元数据和授权按当前请求读取，不承诺跨文件和授权系统的原子快照。项目选择器包含当前可管理场景关联的项目及可读资源管理项目；不显示其他工作区的项目。

## 写入与权限

`POST /api/data-resources`：resource_id、request_id（32 位小写十六进制）、expected_revision（单资源登记修订，初始 0）、expected_version（64 位元数据摘要）、owner_project_id、is_base（布尔）、reason（非空白，最多 500 字符）。

必须通过中央会话、同源 Origin/CSRF、workspace_manager，以及来源场景 data.manage / space.manage 检查。项目管理资格和资源登记都不扩大场景访问权限；登记项目必须为同一作用域的 active 项目，已登记管理归属不能在此直接转移。

一次事务原子写登记、版本快照和含可信 actor / reason / before / after 的审计。以 scope + actor + request_id 幂等，相同命令重试返回原结果和 replayed=true；参数变化拒绝。旧版本不覆盖，资源登记与项目归档共享同一个事务写锁；仍管理资源的项目不能归档。

422：结构或参数不合法。403：权限或可见范围不足。409：登记修订冲突、来源摘要变化、管理归属转移、目标项目无效、请求标识复用。503：目录超预算或存储不可用。错误不覆盖旧登记。

## 页面与后续

固定导航按资源分组，项目及场景位于内容操作行；不增加项目树、对象菜单或查看 / 编辑 / 发布导航。项目维护、场景关联及资源登记采用抽屉；旧场景工具收进对象操作菜单并保留旧直链。列表分页及项目检索在服务端执行，不下载几何数据。

D02 仅展示待登记、基础数据等有实际依据的标记。D03 接通授权和实际引用后再显示已共享、外部引用和平台共用；不把调整场景关联冒充共享。资源与审计都在已有 checkpoint 项目库中，回退应保留数据库，不能删除新表来重写历史来源。


## D03a 兼容扩展

资源行可增加 is_shared、external 和 uses。external=true 的接收项目行以 resource_id 作为 key / record_id，href、space_id、space_name 为 null，can_manage=false，uses 只包含当前身份可见的实际 active 引用及准确授权状态，不暴露来源场景定位。固定引用版本逐条保存在 uses 中；列表 source_version 为其中一个固定版本摘要，多个版本应从详情逐条核对。接收方解除引用后从资产清单移除，引用记录页仍可查历史。尚未使用的共享授权不计项目资源数量。授权范围、冻结原件及使用契约见 [resource-sharing-v0.1.md](resource-sharing-v0.1.md)。


## D03b 独立资料扩展

资源增加 owner_kind=project|workspace|unassigned，旧已登记场景来源按 project 兼容，未登记为 unassigned。新 resource_file 行不具有来源场景 URL，可明确归项目或工作区共用。维护登记增加 owner_kind（旧调用默认 project），共用时 owner_project_id=null；仍不允许归属转移。读取增加 placement 与 ownership 筛选。新上传、原件下载、权限、存储及恢复边界见 [项目级与共用资料](resource-files-v0.1.md)。


D04c 补充 `lifecycle=all|active|archived|disabled` 请求 / 响应范围与每项 `lifecycle_state`。独立原件来自事务治理状态，场景 input / candidate / 表达复用既有成果状态；未接入治理的附件和外部参考返回 null。按状态过滤时不将未知状态视为 active。治理与处理链的具体边界见[处理血缘与参考原件归档](resource-processing-governance-v0.1.md)。
