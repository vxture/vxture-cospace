# 场景资料说明与来源事实 v0.1

P13实现。资料归属继承服务端核验的Workspace／场景绑定，全部接口要求`data.manage`；写请求还需平台会话、Origin及CSRF。操作者来自验签身份。路径ID必须属于明确的`space_id`。

## 1. 说明

`GET /api/inputs/{id}/description?space_id=…`返回`cospace.input-description/0.1`：

```json
{
  "profile": "cospace.input-description/0.1",
  "space_id": "space-0000000000000000",
  "input_id": "input-0000000000000000",
  "original_name": "固定登记名",
  "display_name": "当前显示名",
  "description": "备注",
  "intended_use": "用途说明",
  "revision": 0,
  "history": []
}
```

没有说明记录时读取返回修订0、原登记名和空说明，不创建数据库。数据库不可读或记录损坏返回503，不当作未填写。

`POST /api/inputs/{id}/description`接受：

| 字段 | 条件 |
| --- | --- |
| `space_id` | 必须与固定资料归属一致 |
| `expected_revision` | 严格整数，≥0；匹配后才能保存 |
| `display_name` | 1—100字符，不可空白 |
| `description`、`intended_use` | 各0—500字符 |
| `reason` | 1—500字符，不可空白 |

拒绝额外字段。文本首尾空白被清理；修订一致且内容无变化时返回原记录。真实修改在同一SQLite事务中检查修订并保存完整历史，包含前后值、服务端UTC保存时间、真实操作者和原因。

409 `input_description_revision_changed`表示并发冲突；422 `invalid_input_description`表示请求字段不合法；503 `input_descriptions_unavailable`表示存储无法确认。客户端须显式重新读取，写请求不自动重放。

说明库为`preview-inputs/input-descriptions.sqlite3`。不修改原`input-*.json`、批次封存成员、预检指纹、构建`input_binding`、模型、双视图、发布或离线包。

授权`GET /api/inputs?space_id=…`为每条资料增加`presentation`，仅含`display_name`、`description`、`intended_use`、`revision`；原`label`保留固定含义。工作流`preparation.inputs[]`同样增加独立`presentation`。历史任务和成果继续显示当时保存的名称。

## 2. 来源事实

`GET /api/inputs/{id}/facts?space_id=…`返回`cospace.input-facts/0.1`，只支持现有NYU RGB-D＋已有轨迹和ROS1首帧路线。

- `fields`：字段到`{value,status,evidence_ref,basis}`的映射；`status`为`known|unknown`；未知值为`null`。
- `basis`：来源声明、适配器解释或文件名时间解释；`known`只说明该值有来源，不说明测量或现场关系已确认。
- `evidence_ref`：固定逻辑成员和字段位置；`evidence`另列本次读取的清单摘要与核对结果。
- `roles`：资料角色及当前路线实际用途；IMU存在不表示参与融合。
- `read_at`：接口读取时刻，不是采集时刻。
- `payload_checked=false`：未重新解码／核验图像或bag；构建提交仍执行实时核验。
- `cache_policy=bounded_manifests_rechecked_per_request`：每次重新读取有上限的清单，不缓存此前成功结果。

每份JSON最多读取2,000,000字节，激光`sample.json`最多256,000字节；摘要必须匹配固定登记。清单缺失、超限、格式异常或摘要变化分别返回409 `input_evidence_unreadable|input_evidence_budget|input_evidence_invalid|input_evidence_changed`。前端清除旧事实并展示错误。原始载荷变化由现有预检／构建检查检出，事实接口不作完整性通过声明。

激光日志窗口与header纳秒以十进制字符串传输，避免JavaScript整数精度损失。NYU图像时间保留微秒数和包含末帧的窗口。来源时钟声明与UTC同步分开；未知现场关系、EPSG、现场轴向、UTC同步都保持未知。无可解释时间文件名时返回未知，不使用文件mtime。

本批不编辑坐标、单位、矩阵、时钟映射或传感器配套关系；DM09／DM10仅实现只读子集。

## 3. 同包去重补充

相同场景、固定归属及`uploaded_package.package_sha256`先定位原登记，即使验收复制目录保留原封存路径。仍重新检查新包，并通过原资料`resolve()`核对内容和固定摘要。显示名变化不参与包身份判断。

存在多个匹配登记返回422 `upload_existing_records_ambiguous`；原封存证据不可用或与新包不符返回422 `upload_existing_evidence_invalid`。不自动选一条、不修复旧路径、不改写说明。不同场景继续独立登记；既有同内容但字节不同的ZIP不据此视为同一包。
