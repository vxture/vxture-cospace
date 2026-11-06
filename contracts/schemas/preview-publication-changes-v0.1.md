# 固定发布变化追溯 v0.1

归属：使用 → 态势服务。此接口只读取两个明确的发布快照，不使用当前候选指针，也不执行选择、发布、审批、回滚或合并。

## 请求

`POST /api/publication-comparisons`

```json
{
  "space_id": "space-6fe7d4c455774cb2",
  "base_publication_id": "preview-7a62782ab6e4438b",
  "target_publication_id": "preview-9b422a246ffb4ea5"
}
```

两方必须归属同一显式空间。space_id为null或省略时仅指历史未关联范围，不能混入已关联发布。发布ID严格匹配`preview-`＋16位小写十六进制，不允许额外字段。请求和响应信封见[JSON Schema](preview-publication-changes-v0.1.schema.json)；嵌套changes的语义继承[候选比较契约](preview-changes-v0.1.md)。Schema只校验结构，SHA256及引用一致性由后端校验。

方向由请求决定，允许反向及自身比较；不依据创建时间自动排序，不推断线性版本历史。自身比较可以没有内容差异，但该版本保存的核对基线通常仍是另一个模型。页面排除目标自身，要求用户另选基线。

## 响应

profile为`cospace.preview-publication-comparison/0.1`。

| 字段 | 定义 |
| --- | --- |
| space_id / project_id | 同一空间归属；历史未关联范围省略 |
| base_publication / target_publication | publication_id、candidate_id、model_manifest_sha256、publication_record_sha256、created_at |
| direction | 固定explicit_base_to_target_not_automatic_chronology |
| geometry_comparable | 坐标声明及网格尺寸兼容；不表示精度已验收 |
| changes.coordinate / geometry | 坐标兼容性、表面数量、单元集合差及最多20个样例；不可比较时增减为null |
| changes.objects / ontology | 稳定ID对象新增/移除/修改与完整前后值；固定本体引用变化 |
| changes.dual_view_impact | 对应目标几何、表面和对象快照，非图像差异分析 |
| changes.comparison_scope | 基于声明坐标，不进行独立配准或实地变化检测 |
| provenance.base / target | 各发布保存的候选核对记录及内部绑定检查结果 |
| comparison_sha256 | 除本字段外，完整报告的规范JSON SHA256；算法与候选比较相同 |
| quality / robot_ready | unverified / false |

publication_record_sha256绑定publication.json原始字节，包含核对记录。报告也绑定模型清单摘要；读取发布时核对成员摘要和长度、记录与模型归属、候选ID、清单摘要与几何来源。比较结束再次检查记录和模型清单字节。摘要用于本机内容一致性，不是数字签名，不能认证审批或授权。

即使当前候选改变或原构建目录不再可读，只要固定快照完整，仍可比较。来源追溯随后可能显示原始资料或构建记录缺失；快照内容比较与外部血缘可用性分开处理。

## 保存核对记录的含义

| provenance字段 | 定义 |
| --- | --- |
| status=not_recorded | 发布没有selection_review；不自动补写历史核对 |
| status=internally_consistent | 保存的候选比较摘要、目标模型、空间、选择序号、允许核对标识、确认和非空说明等内部绑定一致 |
| status=binding_mismatch | 保存记录结构或内部绑定不一致；仍可查看快照差异，不可当作核对依据 |
| matches_requested_base_model | 仅target的有效记录检查：保存的base_ref是否等于本次基线发布的candidate_id＋model_manifest_sha256；其他情况为null |
| saved_review | 保存的完整核对对象；没有或非对象格式时为null，不伪造核对人/时刻 |
| trust | 有保存记录时固定saved_local_record_not_authenticated_approval |

“模型一致”不代表两个发布之间存在已认证的父子关系。相同候选和清单可以形成多个发布；保存核对针对候选，不针对publication_id。目标有有效核对记录但基线模型不同，必须明确说明该记录不能证明本次两个发布之间已经核对。

表面移除仅表示证据移除，不表示空闲；对象移除仅表示不再含该标注，不证明设备拆除。坐标声明/分辨率不一致时不计算单元集合差，但仍返回标注、本体与核对记录。最大单方500,000个表面单元，沿用候选比较的限制。

## 错误与页面语义

422：请求结构不合法；403：Origin不允许；503：未配置构建服务；409：空间不匹配、发布缺失、成员或绑定变化、比较上限等。失败不返回可继续使用的旧报告。

页面更换基线、关闭面板、更换空间时中止旧请求并清空报告；服务失败、响应空间或发布ID绑定不一致时清空结果。下载保存当前报告，来源链接指向明确发布与构建记录，空间预览通过独立标签页打开。当前工程环境尚无身份认证及服务端空间ACL。
