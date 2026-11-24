# 固定版本共享与参考关联 v0.1

状态：D03a。同一可信 issuer / org_id / workspace_id 内，归属、共享授权、实际引用分别记录。项目级上传和工作区共用归属留在 D03b。

## 接口

- GET/HEAD `/api/data-sharing`：`view=available|grants|uses`，可选 project_id、resource_id、search（最多 100 字符）、offset（0～10000）、limit（1～100，默认 20）。未知参数拒绝。available 必须指定有效接收项目；grants 必须指定资源并具备来源管理权限；uses 必须指定可访问项目，已归档项目的历史允许管理者核对。
- POST 同路径：公共字段 request_id（32 位小写十六进制）、expected_revision（授权或引用当前修订，初次 0）、reason（非空白，最多 500 字符）。中央会话、Origin/CSRF 与业务权限同时核验。
- GET/HEAD `/api/data-sharing/download`：grant_id、project_id、grant_revision。每次核验有效授权、接收项目权限、准确授权修订、下载许可与冻结原件字节；返回 no-store、attachment、nosniff、sandbox，HEAD 无正文且长度为真实载荷长度。原来源场景端点不因共享而放开。

响应 profile 为 `cospace.resource-sharing/0.1`，含 workspace_id、view、project_id、resource_id、items、total 和 next_offset。分页只包含调用者可访问的范围，不披露不可见场景及全局引用数量。

## 命令

| action | 字段与行为 |
| --- | --- |
| grant | resource_id、version_id（64 位固定元数据摘要）、expected_resource_revision、target_kind（project / workspace）、target_project_id（project 时必填，workspace 时 null）、allow_download、expires_at（可选，必须有时区且晚于当前时间）。来源 workspace_manager 且来源场景 data.manage / space.manage 才可授予；版本须已登记，管理及接收项目有效，不能共享给自身管理项目。 |
| revoke | grant_id；当前授权变为 revoked，阻止后续访问与新引用，保留审计及旧引用。 |
| use | grant_id、expected_grant_revision、project_id、可选 space_id、purpose（非空白，最多 200 字符）、use_mode=reference。接收项目须可管理；指定场景还须 data.manage 且当前属于接收项目。spatial_application 返回 409，不能凭坐标名称猜测可叠加。 |
| unlink | use_id；核验接收项目及指定场景权限，标记 unlinked，保留历史。 |

授权以资源 + 固定版本 + 目标范围生成稳定 ID；引用以资源 + 项目 + 可选场景生成稳定 ID。更换授权修订不会让旧引用自动恢复，access_status=grant_changed，接收方须明确重新关联。新源版本不会升级已有引用。

以 scope + actor + request_id 保持幂等，同 request_id 改参拒绝；先重验当前权限，再返回重放结果。修订检查、快照、状态变更和 before / after / actor / reason 审计在同一 SQLite 写事务完成。授权撤销与下载已开始传输之间不承诺取消在途字节。

## 固定数据与存储

共享首次冻结经过白名单挑选的公开元数据，接收方不获得来源场景 ID、原始记录 ID、私有路径或来源可点击链接。旧 D02 只保留摘要的历史版本，若当前来源已变化且没有共享快照，则拒绝重建该历史版本。

参考附件共享时重验原件 SHA-256 / 字节数并保存固定原件；单件沿用 32 MiB 限额，同作用域冻结原件总量上限 512 MiB。每资源版本只保存一次。其他输入、模型和表达目前仅支持元数据参考，不能开启原件下载，也不宣称可直接用于构建或服务发布。

授权、引用、共享快照和原件存入既有 business-projects.sqlite3 的 data_resource_grants、data_resource_uses、data_shared_versions、data_sharing_changes；沿用已有数据库 checkpoint 备份。损坏记录或载荷失败关闭。共享记录扫描预算 10000 条，超限返回 503。本批没有物理删除或回收接口，保留旧快照与审计。

## 目录与页面

已有共享授权但未引用的数据只在“关联已有数据”抽屉出现，不计入项目资产数量。实际 active 引用纳入项目清单，按资源去重；撤销 / 到期引用仍保留且显示当前授权状态。平台列表优先保留自身可读来源，跨项目引用不重复计资产。

来源有有效授权显示“已共享”，接收项目显示“外部引用”。workspace 范围授权不改变项目管理归属，不显示为“平台共用”。引用记录导航展示固定版本、用途、关联范围及状态；操作仍在清单菜单及抽屉中，不变成流程导航。

项目归档同时检查主场景关联、管理资源及 active 引用；解除全部引用后可归档，历史记录仍保留。

422：参数无效；403：权限不足、授权撤销 / 到期或下载修订不匹配；409：修订冲突、目标无效、源版本不可用、下载类型不支持、需空间核验或存储预算达到；503：存储 / 快照损坏或查询超预算。原业务资料、构建、发布绑定不改写。
