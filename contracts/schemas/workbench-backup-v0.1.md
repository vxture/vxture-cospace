# 工作台冷备份 Profile v0.1

范围：本机单服务工作台。运行交接操作，不新增场景业务对象。格式cospace.workbench-backup/0.1，ZIP容器，manifest.json加逐文件业务快照。

## 运行布局

```text
business-root/
  runtime/  场景目录、输入封存、批次、模型及视图、选择、发布、本体、台账、生命周期
  policy/   space-policy.sqlite3、场景创建必需标记
  setup/    sources.json、workspace-scenes.json
```

会话目录、客户端密钥、加密密钥、身份配置及软件环境单独保管，不放入此根目录。打包器只允许已知业务目录／配置文件，拒绝夹带policy/sessions、setup/client-secret等文件；不是按关键词猜测或清洗任意目录。操作系统ACL不在此Profile中，恢复后的文件访问权限由部署方设置。

受管理服务启动时持有runtime/.preview-service.lock，覆盖装配与运行阶段。备份只支持已采用该锁的启动器，锁文件必须存在；不能以旧未受管理启动方式运行后自行补标记冒充停服。冷备份必须停服且没有queued／running模型或视图任务。进程被强制停止但任务未完成时，先通过原服务恢复／核对中断任务并确认worker已停止，再停服备份。

## 清单与收据

manifest字段：profile、root（原绝对路径）、created_at（UTC）、actor、reason、restore_mode=same_machine_original_path、sessions_included=false、files。files为相对POSIX路径 → bytes、sha256。

runtime、policy、setup下业务文件按实际字节保存，包括SQLite数据库、规则私有目录及历史记录。排除临时进程／变更锁文件；发现.pending、.tmp、SQLite WAL／SHM／journal或故障标记则拒绝。SQLite只读quick_check，policy及两个配置另作格式校验。

资料登记的snapshot／tracking必须存在且位于原runtime内。启用的配置来源也必须位于原备份根目录。当前采用浏览器上传封存的场景满足此条件；外部路径拒绝并提示采用封存输入。不能把只复制索引当作完整资料备份。离线包是消费成果，不替代含资料和历史的运行备份。

CLI收据返回status、archive、sha256、files、bytes。外层ZIP的SHA-256需另存，verify／restore必须由操作者提供。它用于完整性与固定字节核对，不是签名、加密或来源认证。actor／reason是可信本机运维输入，不冒充平台登录用户。

## 备份准入与输出

- 取得停服锁及runtime／policy变更锁；逐文件清单、来源自包含、配置、任务和数据库检查。
- 输出必须位于根目录之外，文件名尚不存在。先写本次独占临时包，再核对源清单无变化与ZIP完整性，最后以不可覆盖方式公开输出文件。
- 最多100,000个业务文件，总展开字节上限2,000,000,000；超出拒绝，不形成不完整备份。
- 链接、junction、路径穿越、Windows设备名、大小写冲突和额外文件拒绝。边界只支持普通本机文件，不隐式追随外部目录。

## 恢复

1. 检查外部提供的ZIP摘要、Profile、完整成员集合、路径、大小、预算及逐文件摘要。
2. 目标必须是清单中的同一原绝对路径，且当前不存在。拒绝覆盖已有目录，含空目录。
3. 在目标父目录创建本次独占暂存区，逐项受限写出、复核摘要／配置／数据库／资料引用，再发布到目标位置。
4. 失败只清理本次暂存区；不删除或覆盖已有业务目录。原路径引用不重写，历史固定摘要不变。
5. 重新提供身份运行配置，保持原issuer与Workspace绑定，重新登录。恢复权限数据不等于恢复登录会话。

首版不支持跨机／换盘搬迁、不改写历史绝对路径，也不包含容灾调度或增量备份。软件版本和运行依赖应与备份兼容，软件环境不在业务快照内。
