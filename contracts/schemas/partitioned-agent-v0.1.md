# 固定发布的分区智能体表面交付 v0.1

## 用途与边界

`cospace.partitioned-agent/0.1` 是已发布固定模型的表面网格分区包。工作台“发布与使用 → 分区交付”提供下载。保留原离线包及其消费库协议，不自动切换或升级已有消费版本。

包只包含表面候选、固定来源清单和分区索引；不包含人视图、原点云、语义对象、本体、业务关联或对象关系。需要后者时继续使用原 `offline.zip`。无表面证据返回 `unknown`，不能解释为自由空间或可通行。`quality=unverified`、`robot_ready=false`。

## 在线获取

- `GET /publications/{id}/partitions.json`：发布、场景、模型摘要、坐标系、分区数、网格数、ZIP 与索引摘要、下载地址及查询预算。
- `GET /publications/{id}/partitions.zip`：ZIP 下载；响应头 `X-CoSpace-Package-SHA256` 和 `X-CoSpace-Index-SHA256`。
- 两者均要求当前平台会话和场景 `space.export` 权限，跨 Workspace/场景拒绝。暂停或退役的发布拒绝新导出，响应不缓存。已持有的离线副本无法远程撤回。

按请求从校验过的固定发布导出，不增加缓存目录、发布可变状态或商业额度逻辑。

## ZIP 布局与绑定

- `index.json`：索引，[Schema](partitioned-agent-v0.1.schema.json) 与运行时 Pydantic 模型保持一致。
- `publication.json`、`model.json`：原发布及模型清单，原字节保留。
- `p00000.bin` 等：连续命名的分区，每个网格为三个小端有符号 int64 索引，24 字节/网格，按 XYZ 字典序排列、无重复。

先以每轴 256 个网格划分空间，超过 4,096 网格的分区沿最长轴递归拆分。分区索引记录实际紧包围的半开网格范围 `[min,max)`；不同分区的包围范围不重叠。导出时独立解码全部分区，证明排序后与原固定模型网格逐项一致，并记录完整网格序列摘要。

每个包最多 500,000 网格、1,024 分区；每分区最多 4,096 网格。ZIP 压缩及解压总量均不超过 32 MiB，索引不超过 2 MiB。超限明确拒绝，不静默抽样。

消费方须从授权交付记录保留预期发布 ID、场景 ID 和索引 SHA256；索引摘要是外部校验依据，不从待验证 ZIP 自行推导。索引绑定来源清单及每个分区的摘要和字节数；原清单的发布 ID、模型 ID、场景、空间几何摘要、智能体摘要、坐标系、分辨率及派生依据须一致。

## 离线查询

在项目根目录运行，需 Python 和 NumPy：

```powershell
.venv/Scripts/python.exe -m experiments.scripts.query_partitioned_preview 'D:/Downloads/PARTITIONS.zip' --publication preview_REPLACE --space-id space_REPLACE --index-sha256 INDEX_SHA256 --frame-id FRAME_ID --bounds MIN_X MIN_Y MIN_Z MAX_X MAX_Y MAX_Z --limit 1024
```

占位值均须替换为交付信息或实际范围。`--point X Y Z` 与 `--bounds` 二选一；`--limit` 仅用于范围，1–4,096，默认 1,024。旧无归属发布须显式传 `--legacy`，与 `--space-id` 互斥。两种查询均须提供匹配的 `--frame-id`。位置单位米，绝对坐标不超过 1,000,000；范围按网格中心落在半开 AABB 中选择，与原范围查询一致。

每次查询重读并校验索引及两份来源清单，仅解压相交分区；不缓存上次查询的文件可信状态。`partition_read` 给出读取数、总分区数及 `scope=requested_partitions_only`。这是本次命中分区的核验，不能声称未读取分区已核验；缺失文件、错误摘要、重复成员、额外成员或不符布局均拒绝。

单次范围最多读取 64 分区和 65,536 个候选网格。两类超限均不返回部分结果：

| 状态 | 网格返回 | 未列区域 | 处理 |
| --- | --- | --- | --- |
| `complete` | 全部匹配网格 | `unknown` | 只陈述表面证据 |
| `limit_exceeded` | 空，保留真实匹配总数 | `null` | 缩小范围或提高结果上限 |
| `partition_budget_exceeded` | 空，匹配总数为 `null` | `null` | 缩小读取范围 |

CLI 退出码：0 查询完整，3 查询超限，2 文件/绑定/参数错误。所有查询返回固定发布与模型引用，不自动寻找最新版本，不使用登录凭据或网络。该包不接入旧消费库的自动激活流程。

## 实测与后续

Anoeta 的 C1 验收使用 B2 固定的 53,531 网格模型。原始 134,422,976 点仍保留在工程分块中；本次不代表全分辨率固定模型或扫描重建算法已经实现。IFC 坐标核对和构件关联为后续 C2。
