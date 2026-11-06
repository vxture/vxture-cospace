# 空间基本配置 v0.1

本接口只更新空间目录的名称与用途描述，不修改空间ID、项目归属、坐标、几何、语义候选、固定发布或权限。授权工作台使用；无认证工程预览不开放同名写入口。

## 读取

`GET /api/space-settings?space_id=space-0123456789abcdef`

需要当前有效平台身份及该空间的 `space.preview`。响应 `Cache-Control: no-store`：

```json
{
  "space": {"id": "space-0123456789abcdef", "name": "设备间", "description": "巡检设备区", "project_id": "project-0123456789abcdef"},
  "revision": 1,
  "can_manage": true,
  "editable_fields": ["name", "description"],
  "history": [{
    "revision": 1,
    "actor": "usr_example",
    "changed_at": "2026-11-03T07:00:00+00:00",
    "reason": "确认空间名称",
    "before": {"name": "样本空间", "description": ""},
    "after": {"name": "设备间", "description": "巡检设备区"}
  }]
}
```

`space` 同时保留目录记录原有的其它字段。无覆盖配置时 `revision=0`、`history=[]`；读取不会创建配置数据库。没有 `space.manage` 时 `can_manage=false` 且不返回修改历史。

## 修改

`POST /api/space-settings`；JSON Schema 见 `space-settings-v0.1.schema.json`，生成源为 `SpaceSettingsChange.model_json_schema()`。

```json
{
  "space_id": "space-0123456789abcdef",
  "expected_revision": 0,
  "name": "设备间",
  "description": "巡检设备区",
  "reason": "确认空间名称"
}
```

全部字段必填。严格类型、禁止额外字段；`expected_revision` 是非负整数，不接受布尔值；name 1–100字符、description最多500字符、reason 1–500字符。name/reason不能仅为空白；保存时移除三个文本字段的首尾空白。

每次请求按当前平台身份和当前空间策略检查 `space.manage`，并校验同源Origin与会话CSRF。actor从已验签身份获取，浏览器不可指定。SQLite事务内比较修订并保存完整新记录和修改历史；无实际字段变化时不递增修订、不追加历史。成功返回本次提交的同一配置快照，字段与修订保持一致。之后的并发提交不会混入该响应。

| 状态 | 含义 |
| --- | --- |
| 200 | 当前读取/提交快照 |
| 401 | 未登录或访问凭据失效 |
| 403 | 未获空间权限、CSRF失败或请求字段无效；沿用现有业务门禁约定 |
| 409 | `space_settings_revision_changed`，重新读取、核对后再提交 |
| 503 | 配置存储或平台/策略暂不可用，不回退匿名或缓存权限 |

存储为目录根下 `space-settings.sqlite3`。覆盖值用于空间目录读取；原空间JSON和已发布快照保持不变。这不是模型版本：修订代表目录展示信息更新，不代表模型重新构建或发布。当前为单宿主部署，不提供分布式存储、自动合并、删除配置或浏览器授权编辑。
