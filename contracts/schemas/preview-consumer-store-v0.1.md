# 本地预览消费库契约 v0.1

状态profile：`cospace.preview-consumer-store/0.1`。只适用于现有真实预览离线包`cospace.preview-offline/0.1`与`0.2`，与合成可信授权运行库互不迁移。

## 存储与绑定

一个显式新建的消费库绑定一个`space_id`。`null`仅代表人工指定的历史未关联范围，不能匹配有空间归属的包。空间归属核对不是用户权限授权。

本批为小包使用Python标准库SQLite：`preview-consumer.sqlite3`保存原始ZIP字节、安装引用和持久选择。包按SHA256标识；发布ID唯一绑定一个摘要。同一包重复安装先核对已存内容，不覆盖、不静默修复。单包继续受现有32 MiB及500,000单元上限约束，所有成员及模型/本体绑定沿用离线包读取器检查。

SQLite为本机消费端实现细节，不是交换格式。原ZIP、发布快照和离线0.1/0.2契约不变；不把整个数据库分发为机器人底图。安装后查询不依赖下载目录、原始图像、完整点云或在线服务。

固定引用字段：

| 字段 | 含义 |
| --- | --- |
| publication_id | 固定预览发布ID |
| package_sha256 | 完整ZIP摘要 |
| publication_model_manifest_sha256 | 发布所绑定的model.json摘要 |
| model_id | 模型候选ID |
| frame_id | 本包坐标系 |
| space_id / project_id | 包内归属，历史未关联为null |

## 操作

| 操作 | 前置与检查 | 保存状态 | 查询会话 |
| --- | --- | --- | --- |
| initialize | 新目录、明确空间或legacy范围 | 创建空库，revision=0 | 空 |
| install | 明确发布ID及摘要；检查完整包与空间归属 | 保存包，选择和revision不变 | 不变 |
| activate | 包已安装；expected_revision等于保存序号；重新校验完整包 | 原子保存引用，revision加1 | 打开新固定会话 |
| status / packages | 只读取现有库 | 不变 | 不创建 |
| restore | 人工提交保存的发布ID、摘要及revision；逐项匹配并重新校验完整包 | 不变，不增加revision | 显式打开固定会话 |

每次新建`PersistentPreviewConsumer`实例均没有活动查询会话；构造、状态读取和安装不会自动恢复。不得用“最新版”替代调用者指定的保存绑定。

激活和恢复通过SQLite写事务串行核对保存序号；激活提交成功后才替换本进程会话。失败回滚，不切换当前会话或保存引用。进程中已取得的旧会话保持固定内容；另一进程激活后，本进程旧会话不会自动追随。需要读取status并显式恢复新引用。旧包复查使用显式activate，是新的选择记录，revision继续递增。

## 状态响应

| 字段 | 语义 |
| --- | --- |
| revision | 持久选择序号；0表示尚未选择 |
| saved_reference | 已保存引用，未选择为null |
| saved_reference_check | 固定metadata_only，状态读取没有重新核对ZIP |
| session_reference / session_revision | 本实例当前固定会话，重启后为null |
| restore_required | 已有保存选择且当前会话缺失或与之不同 |
| quality / robot_ready | 固定unverified / false |

`restore_required=false`在空库中也可能成立，必须同时看saved_reference和session_reference。它不表示设备可运行。状态或安装列表中的摘要只是本地元数据，恢复/激活才重新核对包内容。

点、对象和范围查询继续使用既有响应字段，增加`consumer_revision`及`package_sha256`；所有结果固定在同一模型/发布。本体及对象快照随包恢复，不能读取服务端可变规则代替。范围超限仍返回零单元及`result_complete=false`，不能解释为空闲或未知。

## 拒绝与边界

- 保存序号变化：`consumer_revision_changed`；恢复请求不等于保存引用：`saved_reference_mismatch`。
- 包未安装或引用错误：`installed_package_missing_or_mismatch`；跨空间：`consumer_space_mismatch`。
- 同一发布换摘要：`publication_package_conflict`；安装元数据与包不一致：`consumer_reference_mismatch`。
- 包内容损坏沿用离线校验错误；拒绝回退到其他版本或自动修复。
- 库不存在时读取失败，不自动创建；初始化中断形成的不完整目录应人工保留排查或选择新目录，不自动接管。

本批验证普通重启、事务失败和事务提交前终止进程，不宣称物理断电可靠性。没有设备远程管理、签名信任、可信时效、撤回同步、生产授权、包清理或配额管理；已有预览数据不因此获得导航资格。

运行见[消费版本保存与恢复](../../docs/guides/预览消费版本保存与恢复.md)。
