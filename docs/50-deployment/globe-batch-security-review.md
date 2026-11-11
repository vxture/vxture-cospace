# 三维球第二批：既有路径告警核查

日期：2026-11-11。范围为 v0.7.24 主分支 Sonar 的五项 Python 路径告警。

| 位置 | 核查结果与处置 |
| --- | --- |
| pointcloud_composition.read_composition | 上层 Manifest 将 composition_path 限定为 composition.json，但函数直接调用缺少自身限制。本批增加固定文件名与目录边界检查，拒绝符号链接，添加直接调用回归。 |
| PreviewJobs._process_declaration / _require_input_files | 路径来自服务端登记记录，通过 PreviewInputs.resolve 重新检查来源摘要，业务入口先校验场景权限；旧模式来自服务启动参数。并非浏览器直接提供的文件地址。本批未取消告警，也未宣称消除任意本地登记路径风险。 |
| StorageInventory.snapshot.add（两处） | 已检查绝对路径、字面及解析后的业务根目录范围，并逐级拒绝符号链接与 junction；失败统一为 storage_observation_unavailable，不回传文件信息。已有越界、父级路径及链接回归。本批保留这些限制。 |

核查说明不等于在 Sonar 中确认误报，也不代表这些本地文件操作经过竞态安全验证。
后续如需限制可信管理员登记的本地来源目录，应单独制定来源根目录迁移规则，避免
直接收紧导致现有合法资料不可构建。扫描器状态如仍失败，应如实报告，不关闭规则。
