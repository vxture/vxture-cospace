# 参考原件版本与显式引用升级 v0.1

状态：D04b，扩展项目级 / 工作区共用资料与既有固定版本共享。只追加独立 `resource_file`；场景输入、附件、构建成果继续由原模块负责。

## 原件追加

`POST /api/data-files/versions`，正文 `application/octet-stream`，查询参数：`resource_id`、`expected_version`（当前原件摘要）、`expected_revision`（资源登记修订，至少 1）、`name`、`reason`、`request_id`。拒绝归属、场景、工作区及其他未知 / 重复参数；名称、32 MiB 非空单件上限、CSRF、流式接收与提交时会话重验均沿用首次上传。

要求当前工作区管理者及有效管理项目。保持资源标识、管理归属、基础用途；原件旧版本写入 `data_resource_file_history`，替换当前投影、追加登记版本并保存前后审计，全部在同一 SQLite 事务提交。新版本摘要包含文件 SHA-256、名称、实际字节、形成时间及既有归属。版本摘要不同不代表测绘精度提高，也不推断文件内容语义。

首次成功 201；同作用域 / 主体 / request_id 的相同命令与内容重放 200，不再追加。回放仍要求当前管理权限；不同参数 / 内容、当前版本或登记修订不匹配返回 409。并发相同预期修订只能有一个新版本成功。

原件预算同时计算当前与历史保留字节 / 份数：512 MiB、1000 份为技术安全上限；共享快照沿用独立预算。所有真实保留字节计入平台 `storage.bytes` 事实统计，不实施商业额度。旧数据库按需创建历史表；不迁移或重写全部原件。项目数据库 checkpoint 包含当前及历史原件。

原 `/api/data-files/download` 可按准确历史 version_id 下载，经当前原件归属授权后核验保存元数据、版本归属、SHA-256 及字节。接收方仍只走准确授权修订的共享下载接口。历史原件可以在追加后首次共享，不要求事先存在共享快照。新版本不会自动共享，也不会改写既有授权、使用关联、构建或服务。

## 已授权版本比较

`GET/HEAD /api/data-reference-upgrade?use_id=...&offset=0&limit=20`，limit 1–100。响应 `profile=cospace.reference-upgrade/0.1`、可信 workspace_id、当前 use、current 快照、candidates、total、offset、limit、next_offset。候选沿用 available 共享白名单，前端比较名称、格式、字节、形成时间与版本摘要；不加载原件正文，不宣称内容差异或坐标兼容。

项目 / 资源 / 场景均从持久化 use 推导，不接受客户端伪造的 project_id / resource_id。要求有效目标项目、当前项目权限；若引用关联场景，该场景仍须属于此项目且当前身份具备 data.manage。只允许 status=active 的引用；旧授权撤销或到期不妨碍通过新有效授权升级。候选必须是同一资源、目标项目有效授权且不同于当前版本的固定快照。不会披露源场景位置、未授权版本或其他项目引用。

## 显式升级

`POST /api/data-sharing`：`action=upgrade`，`use_id`、新 `grant_id`、`expected_grant_revision`、`expected_revision`（当前 use 修订）、`expected_version`（当前 use 版本）、`reason`、`request_id`。

事务内重验引用目标、场景、同资源的新有效授权及准确授权修订、登记版本和保存快照。只更新此 use 的版本、授权、授权修订、引用修订和更新时间；保持 use.id、project_id、space_id、purpose、参考用途与未应用坐标状态。前后引用完整记录写入 `data_sharing_changes`，旧原件和旧授权不删除。允许显式选择其他已授权历史版本，不按时间自动挑选。缺失 / 损坏快照返回 503，原引用不变。

幂等按作用域 / 主体 / request_id 处理；回放仍重验当前目标与新授权权限。不同命令、过期修订、同版本或已解除引用拒绝；跨项目 / 跨资源授权、撤销或到期授权拒绝。升级不改写处理输入、空间基准、模型和服务发布。

页面沿用现有三点操作、上传抽屉、共享设置和引用详情中的内嵌比较区，不增加导航或独立版本平台。关闭含未保存升级原因的详情使用既有离开提醒。处理血缘、归档与删除治理留给 D04c。
