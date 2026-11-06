# 成果使用状态控制 0.1

H3a与H3b已实现，适用于本机单服务工程预览。资料/候选/固定发布内容保持不可变，使用与分发状态写入独立账本。报告结构见[JSON Schema](preview-artifact-control-v0.1.schema.json)，发布路径见[分发控制](preview-publication-distribution-v0.1.md)；原[H2影响检查](preview-artifact-impact-v0.1.md)继续为只读接口。

## 状态与操作

| 对象及当前状态 | 可请求操作 | 结果 |
| --- | --- | --- |
| 资料 active | disable_input | disabled |
| 资料 active / disabled | archive_input | archived，并记录原状态resume_state |
| 资料 disabled | restore | active，提交前重新预检原资料 |
| 资料 archived | restore | 返回归档前active或disabled；返回active时重新预检 |
| 候选 active | archive_candidate | archived |
| 候选 archived | restore | active，重新检查快照与保存引用 |
| 固定发布 active | pause_distribution | paused，阻断新分发 |
| 固定发布 paused | restore | active，重新检查完整证据并恢复同一发布 |
| 固定发布 active / paused | retire_publication | retired，停止新分发，保留历史与替代关系 |
| 错误版 retired且未登记替代 | retire_publication | 仅补充同场景可分发替代版本，保持retired |

无控制记录时默认为active、revision=0、history=[]，不创建账本、不迁移原记录。归档不删除或移动文件，不级联影响既有派生候选、固定发布或消费副本。恢复不替用户选择候选、发布或消费版本。

P20增加退役：请求额外带`retirement_kind=superseded|erroneous`、可选`replacement_publication_id`。正常接替必须指定同场景、完整且分发中的替代发布；错误版可先退役后补充替代。禁止自引用、跨场景或不可分发的替代。退役无一般restore入口；补充替代不能改变原退役类型，不能重新激活。历史记录保留操作者、原因、替代发布及修订。相同操作者精确重放已提交退役，可返回已保存结果，不产生重复事件；其它旧修订仍拒绝。接替不替消费方切换版本。

## 只读报告

`GET /api/artifact-control?space_id=SPACE_ID&artifact=input:INPUT_ID`

artifact接受`input:input-...`、`candidate:build-...`或`publication:preview-...`。必须显式提供空间，并由保存归属核对目标；offline_package需转到其来源publication，不接受未成功候选。

| 字段 | 定义 |
| --- | --- |
| profile | `cospace.preview-artifact-control-report/0.1` |
| space_id / artifact | 当前空间和目标key |
| record | 当前状态及revision、resume_state、完整history；已有事件另含previous_state、operation、reason、updated_at、actor、checked_snapshot_sha256 |
| impact | H2原结构的引用影响证据，不赋予执行能力 |
| actions | 当前状态允许列出的操作、目标状态、blockers和allowed |
| snapshot_sha256 | H2引用摘要＋同空间所有保存控制记录及历史的摘要；不包含检查时间 |
| identity | 底层报告兼容值`local_engineer_unverified_identity`；实际执行者看事件actor，平台入口取服务端认证身份 |
| publication_control_supported | 当前true；兼容旧报告false |
| quality / robot_ready | unverified / false |

`allowed=true`只表示本次报告满足已保存规则；仍须经写接口重新核对。资料归档沿用活动批次、保存活动任务、当前选择依赖等阻断；候选归档沿用当前选择和保存活动任务阻断；任何来源缺口阻断全部操作（含恢复）。恢复为可用的资料可能在提交时因原文件预检失败而拒绝。

报告GET不创建空SQLite或锁文件，不轮询任务或重新预检源文件。报告为跨存储读，不承诺事务快照；执行请求使用下述互斥与重检。

## 受控提交

`POST /api/artifact-control/transitions`

```json
{
  "space_id": "SPACE_ID",
  "artifact": "input:INPUT_ID",
  "expected_revision": 0,
  "expected_snapshot_sha256": "64位报告摘要",
  "operation": "disable_input",
  "reason": "此次资料不再用于新的构建"
}
```

expected_revision为非负严格整数，拒绝布尔值；摘要为64位小写十六进制；reason为1—500字且去除空白后非空。未知字段、客户端actor或不支持操作均拒绝。遵循现有Origin检查，仅接受本机预览来源；这不能替代真实身份与空间权限。

服务按顺序获取运行区互斥锁、任务锁，再重新读取报告，比较revision与snapshot，检查操作和阻断。恢复资料为active前重新预检。随后在SQLite单个事务内CAS更新当前记录、追加一条修订事件；revision递增1，返回含完整history的`cospace.preview-artifact-control/0.1`记录。旧摘要/修订不会静默重试。

服务端身份固定为本机预览身份，不能由请求伪装已认证用户。历史同时保存前后状态、操作、原因、时间及执行前摘要；不改写原input/job/model/publication文件。失败事务不保留孤立事件。读取核对当前记录与完整事件序列，损坏时停止新使用。

P20认证入口补充：上述identity保留为底层报告的兼容字段。平台业务中间件实际写入时，操作者取认证principal.subject，按场景`publication.manage`等能力授权；替代版本也校验同场景发布权限，客户端不能指定actor。底层未认证工程服务仍使用原本机默认身份。验收使用模拟平台账户，生产身份源尚未验收。

## 门禁与并发

| 新使用入口 | 服务端检查 |
| --- | --- |
| 直接资料构建、批次构建 | 资料须active |
| 批次封存 | 每一成员资料须active；已停用批次/资料的成员记录仍保留 |
| 候选选择（含人工核对提交） | 目标候选须active |
| 语义、业务、关系派生 | 直接基线候选须active |
| 固定发布 | 所选直接候选须active；发布既有后续候选不受已归档祖先级联影响 |
| 已有发布的查询、资产及离线导出 | 发布须active，暂停时409，详见分发契约 |

状态变更、上述准入、批次调整和资料登记共用运行区`.preview-mutation.lock`。锁可在线程内重入，Windows使用msvcrt字节锁，其它本机环境使用flock；占用超15秒返回需刷新错误。任务列表的完成状态更新也在该锁内。锁文件保留供后续互斥，不是业务成果。资料、任务、批次目录应位于同一运行区下。

单运行区仍仅支持一个活动服务实例：OS锁保护协作写入，不把内存子进程调度器升级为多服务调度。执行顺序为运行区锁→任务锁→批次/控制SQLite，避免反向等待。已准入任务不追溯取消；其新任务记录会改变引用摘要，旧停用请求可能需重新检查后提交。人工直接改文件、原文件外部变动、网络共享盘和数据库外部写入不在协作互斥保证内。

## 返回与兼容

| HTTP | 情形 |
| --- | --- |
| 200 | 报告读取，或受控变更已提交 |
| 403 | Origin不允许 |
| 404 | 空间或该空间的目标不存在 |
| 422 | 请求字段、artifact或操作格式非法 |
| 409 | 原因空白、旧修订、摘要变化、引用阻断、非法状态转换、记录/账本损坏、锁忙或恢复预检失败 |
| 503 | 未配置构建服务 |

响应不确定或409时清除旧控件，先刷新读历史再操作，不能假定未提交。无控制记录不影响旧成果读取。既有成果目录可选附加`lifecycle_state`、`lifecycle_revision`，输入及构建列表附加lifecycle_state；原state及各自原契约含义不变。归档项仍在历史成果目录中，构建资料选择排除归档项；停用资料不可用于提交，归档候选不可选择。直接API检查独立于这些界面限制。

`preview-lifecycle.sqlite3`存于运行区根目录；history为追加记录，但不是签名审计或外部防篡改存储。该契约不包含删除、存储回收、既有消费副本撤回、消费端远程失效、精度放行或机器人授权。固定发布暂停仅控制新分发。
