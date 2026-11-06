# F06b2 体素逻辑块变更实验契约 0.1

日期：2026-10-28。输入schema_version=cospace.voxel-change/0.1。输出仅为synthetic候选，不是可安装的agent-voxel运行包。

## 1 基线与操作

固定base_package_id和base_package_sha256；包清单原字节摘要递归绑定所有已登记块。调用方必须另供F05 expected_source，先完整校验原运行包，再检查变更基线；不能以已损坏基线生成新候选。

| 操作 | 前置条件 | 结果 |
|---|---|---|
| chunk.add | index范围内且未在基线清单登记；expected_absent=true | 新增完整块字节 |
| chunk.replace | index已登记且expected_sha256等于旧块摘要 | 替换完整块，字节不能与旧块相同 |
| chunk.remove | index已登记且expected_sha256等于旧块摘要 | 新清单不再登记该块，查询为unknown/missing_chunk |

“不存在”指基线清单无该逻辑块，不等于块存在但文件丢失。原块缺文件会在F05验证阶段拒绝。不能通过add覆盖已有块；不能remove未登记块。每个index每批只允许一次操作，索引必须为整数字面量，按固定dimensions/chunk_shape检查边界。

本Profile不支持修改坐标、原点、分辨率、分块形状、组件或来源身份；这些更改需完整重建和新来源验证。所有输入字节不变，变更结果构建为新字典。

## 2 字节和证据

至少一项证据，证据及替换块均固定相对路径、字节数、SHA256。校验实际bytes，不读取外部路径或URL。证据真实性、变化检测结论和独立性未在这里验证。

新块必须符合F05 u8编码、完整块长度及0至4状态码，拒绝压缩/截断/未知编码。最多256操作、16证据、272输入资源；每资源8MiB、合计32MiB。拒绝重复资源引用、未引用资源、大小写路径碰撞及明显越界。输入路径不作为生成输出路径。

新候选块按逻辑index排序，路径确定为chunks/x-y-z.u8；未受影响块沿用原字节。操作顺序不影响候选载荷与清单摘要，但变更摘要保留操作记录顺序。每个impact记录块的半开bounds、旧/新摘要及删除标识；bounds由原点、块索引、块尺寸和分辨率计算，不依赖客户端上报范围。

## 3 候选隔离

输出files内只有agent-voxel-candidate.json与候选块，清单版本cospace.agent-voxel-candidate/0.1、stage=candidate_only。没有agent-voxel.json；普通VoxelSession加载时拒绝，不静默成为可运行包。该候选清单是内部实验输出，尚未制定独立公开输出Schema。

保留的source只是原基线来源，不代表新体素已经由原真值派生或对应新发布。输出base_source单独说明这一点，candidate_package_id必须不同于base_package_id；source_geometry_consistency_verified=false、authorized=false、robot_ready=false。

VoxelCandidatePreview必须重新提供原基线、expected_source、变更和证据，重新构造完整候选并比对所有字节及impact；任一字段变化拒绝预览。内部暂时投影至F05编码以执行纯查询，投影不返回、不持久化；预览响应返回candidate_manifest_sha256和base_source，不伪造新release或运行包摘要。

删除全部块允许生成全unknown候选，但不代表可发布或可导航。required_rechecks要求来源几何一致性、覆盖质量、机视图重派生与人视图影响检查。局部块范围不等于质量评估可无条件缩小到局部；任何新发布仍须重新绑定受影响真值、质量及视图。

## 4 样例与兼容

运行 `.venv/Scripts/python.exe -m experiments.scripts.generate_voxel_change_sample` 生成examples/voxel-change：变更清单、输入资源、候选清单/块以及before-after核对报告。样例新增[1,1,0]、替换[0,0,0]、删除[1,0,0]、保持[0,1,0]原字节。

未接入F06b1 CandidateBranch，未将两类候选强行合并成新真值；本轮没有新增数据库事务、持久化、文件安装、断电恢复或并发切换实现。所有源快照由调用方固定；发布指针的并发保护继续属于正式采用/发布流程。旧agent-package、可信分发及生命周期接口未升级。

## 5 下一步

F06c定义事件信封、因果关联、实体/活动/责任主体与版本追溯；随后以真实输入选择一个端到端增量接入，补上几何派生与独立质量证据，避免继续用候选字节一致性替代真实空间更新验收。
