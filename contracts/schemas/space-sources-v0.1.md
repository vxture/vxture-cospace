# 空间资料来源配置 v0.1

本契约将服务端来源目录和具体空间的登记许可分开。服务端部署管理员通过原 `cospace.preview-sources/0.1` 配置审核路径与格式；空间管理员从该目录选择本空间启用的来源。浏览器只提交来源ID，不提交路径或适配器参数。

## 接口

| 接口 | 权限 | 内容 |
| --- | --- | --- |
| `GET /api/source-settings?space_id=...` | 本空间 `data.manage` | 修订、已启用来源；管理员另有完整可选目录和修改历史 |
| `POST /api/source-settings` | 本空间 `space.manage` + Origin/CSRF | 原子替换本空间启用来源集合 |
| `GET /api/registration-sources?space_id=...` | 本空间 `data.manage` | 只返回当前有效的启用来源，不返回路径和其它空间配置 |
| `POST /api/inputs` | 本空间 `data.manage` + Origin/CSRF | 重新读取空间来源许可，完整核验后登记 |

授权模式要求显式空间。查看者没有数据管理权限；工程师可以读取自己空间的已启用项，不能修改、查看未启用目录或管理历史。管理员可选择部署清单中全部已启用且可用的来源；部署清单应当仅包含这个服务实例内可供管理员分配的资料，不能将尚未授权分配的租户资料混入同一清单。此版本不提供逐来源的第二层分配ACL。

新空间默认没有启用来源；旧工程服务全局来源行为保持兼容。启停不追溯改变已登记资料、候选或固定发布，也不是采集批次/资料生命周期状态。已通过来源准入检查的请求可继续完成，下一次准入读取最新配置。

## 修改请求

JSON Schema由 `packages.data.space_sources.SourceChange.model_json_schema()` 生成，见同名 `.schema.json`。

```json
{
  "space_id": "space-0123456789abcdef",
  "expected_revision": 0,
  "catalog_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "enabled_source_ids": ["nyu-office-short"],
  "reason": "启用已封存的设备间资料"
}
```

全部必填，严格类型，额外字段拒绝。修订为非负整数，最多100个不重复来源ID，原因1–500字且不能为空白。空集合表示停用全部来源。事务内比较修订；集合及来源指向均未变化时不增加修订和历史。成功响应使用同一已提交快照。

`catalog_sha256` 是服务启动时可信来源ID、适配器、解析后的路径组合摘要，不是原始数据内容摘要。每条空间许可保存对应来源的同类指纹；同ID改路径/格式或删除来源，重启后该许可失效，管理员必须重新确认。清单变化导致旧修改请求409。修改标签不改变来源指纹。原始文件内容由登记、预检和构建的既有摘要机制另行验证。

## 响应与审计

读取/修改均返回 `space_id`、`revision`、`can_manage`、`catalog_sha256`、`sources`、`catalog`、`unavailable_source_ids`、`history`。所有响应为 `no-store`。

`sources`元素只有 `id`、`label`、`format`。管理用`catalog`另有`enabled`、`needs_confirmation`。工程师的后三个管理集合为空。历史包含修订、已验签actor、UTC `changed_at`、原因、启用ID集合前后值及当时目录摘要；存储的许可另保留来源指纹。审计中的ID列表不保存文件内容快照。

新登记资料增加可选`registration_ref`：

```json
{"source_id":"nyu-office-short","settings_revision":1,"catalog_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","actor":"usr_example"}
```

它记录实际登记准入来源，由服务端生成，随不可变登记记录和既有 `input_binding` 传入后续候选。重复登记同一资料返回原记录，不补写新来源修订、actor或名称；旧记录允许没有此字段。

| 状态 | 含义 |
| --- | --- |
| 200/201 | 读取/修改成功；登记复用/新建 |
| 401/403 | 身份、空间权限、CSRF或请求字段无效 |
| 409 | 修订/目录冲突，来源不允许或文件核验失败 |
| 503 | 配置存储/平台不可用，或未安装登记适配器 |

配置保存于目录根的 `registration-sources.sqlite3`，SQLite事务CAS和历史原子保存，损坏拒绝访问；无库表示尚未配置，不自动启用来源。适用单宿主单业务进程，未验收多节点存储或跨进程登记去重。新增来源文件和变更部署清单需受控部署与重启；启停空间许可按每次请求生效，无需重启。
