# 项目级与工作区共用资料 v0.1

状态：D03b。扩展既有平台数据目录与 D03a 共享引用，不建立独立平台、不创建占位场景。

## 归属与权限

`owner_kind=project` 时必须指定当前可信工作区内 active 的业务项目；`owner_kind=workspace` 时 `owner_project_id=null`，表示工作区共用管理归属。它不同于 `target_kind=workspace` 共享授权，后者不改变原管理归属。

上传和维护登记要求既有 `workspace_manager`，不从前端传入 workspace、actor 或场景。项目级原件可由管理者及当前拥有该项目场景 `data.manage` 权限的身份读取；未关联场景的项目由工作区管理者维护。首版没有新增项目成员权限模型。共用原件由管理者直接管理；其他项目经有效共享授权与显式使用关联访问，未引用的授权不计项目资产。

## 上传

`POST /api/data-files`，正文为 `application/octet-stream`；查询参数为 name、owner_kind、可选 owner_project_id、is_base、reason、request_id、expected_revision=0。request_id 为 32 位十六进制；reason 非空白、最多 500 字符。拒绝未知 / 重复参数与无效名称，沿用参考资料 PDF、PNG、JPG、JPEG、CSV、TXT、IFC 白名单，保存不透明原件，不执行内容、不解析 IFC、不自动注册构建输入。

通过中央会话、同源 Origin/CSRF、工作区管理和目标项目校验后流式接收；声明长度与实际字节均限制为单件 32 MiB、非空。接收完毕重新核验会话、主体 / 工作区、平台准入和当前业务权限，提交事务内再次核验目标项目。中途撤权或目标归档不提交原件。

单作用域原件总量 512 MiB、1000 份为首版存储与查询安全上限，不是商业额度。原件、固定元数据摘要、资源登记与审计同事务写入 `business-projects.sqlite3`：新增 `data_resource_files`，复用 `data_resources` / `resource_changes`。资源 ID 由可信 scope、actor、request_id 生成；重试相同命令及内容返回 200 / replayed=true，不新增资源，改变参数或字节拒绝。新上传返回 201、resource_id、登记及审计结果，无原件正文和私有路径。

原件不覆盖；相同文件的不同新请求是独立资源，不自动合并管理归属。管理归属上传时明确，维护登记只允许调整基础用途并留存原因，不支持在此转移项目或变成共用资源。

## 目录与下载

目录行 `kind=resource_file`、`resource_type=reference`，key / record_id / resource_id 相同，space_id / space_name / href 为 null；项目级上传不伪造来源场景或旧场景资料 URL。source_version 仍为 source_metadata，其固定摘要包含受校验的原件 SHA-256 与字节数。目录不读取 BLOB，`source_files_rechecked=false`；上传和下载重验字节，不将文件完整性等同于空间精度。

`GET/HEAD /api/data-files/download?resource_id=...&version_id=...` 核验当前权限与准确版本后重验 SHA-256 / 字节，返回 no-store、attachment、nosniff、sandbox。HEAD 正文为空，Content-Length 为真实长度。跨项目接收方使用既有 `/api/data-sharing/download` 与准确授权修订，不开放原件端点。共享首次冻结此版本原件并沿用 D03a 的独立快照预算、撤销、到期及引用历史规则。

`GET/HEAD /api/data-resources` 增加 `placement=all|project|scene` 与 `ownership=all|owned|external|workspace`，响应回显两项。项目级筛选纳入无场景资料及项目级引用；场景筛选按真实引用范围处理。先应用筛选再去重，避免自身可读来源遮蔽外部引用筛选。工作区共用资料只有实际引用后才进入接收项目清单。

## 恢复与范围

原件与登记沿用既有项目数据库 checkpoint；回退保留数据库及新增表。损坏的文件元数据、登记归属、字节或摘要失败关闭。首次拒绝事务留下的空 SQLite 文件按未初始化处理，部分缺失业务表仍失败关闭。

本批不包含采集大文件导入、文件版本升级、物理删除、归属转移、空间自动应用或服务发布。D04 承接版本升级、血缘及归档影响治理。

422 参数无效；403 权限不足；409 目标无效、管理归属转移、幂等命令冲突或总存储安全上限；413 文件大小超限或空文件；415 正文类型不支持；503 存储或完整性不可用。

原件与冻结共享快照的真实保留字节纳入既有平台 storage.bytes 事实统计。data_resource_scopes 在可信写入事务记录主体的 issuer / org_id / workspace_id 与摘要映射，使无场景项目或共用原件也可归属；用量查询只读取 BLOB 长度，不读取原件正文。未知或损坏作用域停止本次观察。平台继续拥有商业额度与订阅规则。
