# Workspace 本体维护与模型选点 0.1

P21实现。维护定义与场景实例分开：规则属于平台Workspace，实例属于一个场景空间中的候选模型。发布和离线包继续固定规则版本及SHA-256。

## 1. 规则维护

| 接口 | 用途 |
| --- | --- |
| `GET /api/ontology-authoring` | 当前Workspace、can_edit、已保存草稿及修改历史 |
| `POST /api/ontology-authoring/validate` | `{definition: {...}}`；校验现有本体0.1／0.2规范，不保存 |
| `POST /api/ontology-authoring/drafts` | 保存同一草稿的下一修订，或精确请求重试 |
| `POST /api/ontology-authoring/seal` | 将已保存且通过规则校验的固定修订保存为不可覆盖版本 |

草稿保存请求见[JSON Schema](ontology-draft-change-v0.1.schema.json)，固定版本请求见[JSON Schema](ontology-draft-seal-v0.1.schema.json)。维护请求使用既有平台会话、Origin和CSRF检查。Workspace归属由已验证身份的issuer、org_id、workspace_id共同确定；actor取服务端subject，客户端不能提交或指定归属。

首版只有平台`workspace:owner`可维护，场景manager不隐式获得工作区规则编辑权。认证用户可读取当前Workspace规则；应用规则仍需对应场景的association.edit权限。共享预置模板只读，不能用同ID同版本覆盖。

保存字段：`draft_id`为`draft-`加32位十六进制；新草稿`expected_revision=0`，后续必须匹配当前修订；`request_id`为32位十六进制；`definition`为JSON对象；`reason`为去空白后非空、最多500字。定义最多64KiB。校验未通过的定义可以保存为草稿，不能保存为固定版本。

草稿响应含revision、sha256、完整definition、history、sealed。历史事件保存服务端操作者、UTC时间、原因、请求摘要、上一事件摘要与当前事件摘要。读取校验连续修订、定义摘要、事件链和Workspace归属；损坏时停止读取。相同请求ID、内容及actor重试不新增修订；内容或修订冲突返回409。固定版本请求还必须匹配草稿摘要，不能覆盖同ID同版本的不同内容。

已固定草稿只读。修改规则可复制到新草稿、显式保存新版本；不会自动迁移任何场景、候选或发布。固定版完全相同的重试返回原记录及原审计信息。

类型、字符串属性长度／必填，以及包含／连接关系沿用[本体0.1 Schema](preview-ontology-v0.1.schema.json)和[本体0.2 Schema](preview-ontology-v0.2.schema.json)。端点类型存在、长度区间、包含单父／无环、连接双向及重复等检查继续使用已有规则。首版没有新增复杂属性类型或OWL／SHACL转换。

固定版本继续通过`GET /api/ontologies`及`GET /api/ontologies/{id}/{version}?sha256=...`读取。列表scope为shared_template或workspace_rules；单版读取返回同类scope和原record／definition。固定记录authoring包含Workspace、actor、草稿ID／修订、原因、保存时间与草稿事件摘要。

私有定义存于`preview-ontologies/.workspaces/{workspace_hash}/{id}/{version}/`，草稿存于该Workspace目录的`drafts.sqlite3`。这些是本机审计资料，尚非外部签名审计服务。

## 2. 模型画面选点

`GET /candidates/{candidate_id}/api/anchor-preview`。权限为当前场景association.edit，响应见[JSON Schema](anchor-preview-v0.1.schema.json)。

返回固定模型摘要、原spatial.npz摘要、场景、局部坐标轴／frame、原模型点数、完整范围及有界点／颜色抽样。最多10,000点，最多2MiB；抽样方法file_index_stride，`stride=max(1,ceil(point_count/10000))`。抽样第i点对应原模型索引`i*stride`。缺少三轴声明返回409，不填造坐标语义。

双击画面中投影附近的实际模型点后，调用既有`GET /candidates/{id}/api/anchor?point_index=...`重新读取原模型位置。前端再次核对候选、模型摘要、坐标系与索引；切场景或模型清空位置并忽略迟到响应。拖动旋转和背景双击不建立位置；渲染失败仍可用原模型索引读取锚点。

对象提交继续走`POST /api/semantic-candidates`；关系继续走`POST /api/relation-candidates`。服务端按固定模型重新取坐标并校验固定规则。锚点属于几何证据，不能证明所填对象类型或关系属实；所有confirmation=unverified，robot_ready=false。新候选仍需人工核对选择、再单独发布。

401／403表示会话或权限不满足，422表示请求格式错误，409表示修订、规则或固定证据不满足；读取不属于当前Workspace的私有本体返回404。业务错误不能触发覆盖或自动迁移。
