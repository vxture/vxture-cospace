# F05 机视图占据分块实验 Profile 0.1

日期：2026-10-28。schema_version=`cospace.agent-voxel/0.1`。只支持合成数据、离线单点三态查询，不是机器人 SDK 或有效性门禁，也不替代已有 agent-package/0.1。

## 1 编码与坐标

清单 agent-voxel.json 为 JSON；占据载荷使用无头、无压缩的 u8 二进制数组，每单元一个字节，无字节序问题。encoding=`cospace.occupancy-u8/0.1`。不把点云、TSDF 或 ESDF 直接解释成占据图。

| 编码 | 查询 state | reason |
|---|---|---|
| 0 | unknown | unobserved |
| 1 | observed_free | synthetic_observation |
| 2 | occupied | synthetic_observation |
| 3 | unknown | degraded |
| 4 | unknown | conflict |

其他编码拒绝整个会话，不默认映射为空闲。每单元暂不携带概率或证据索引；来源证据解释待后续编码扩展，不能因此声称观测已验证。

origin_m 为米制局部网格下界，resolution_m 为三轴一致尺寸。dimensions 与 chunk_shape 都按 X/Y/Z 排列。分块 index 从0起；块原点=origin_m+index*chunk_shape*resolution_m，逐轴计算。首版要求每轴 dimensions 能整除 chunk_shape，不支持截短边缘块或多分辨率。

块内按 X 最快存储：offset=x+Nx*(y+Ny*z)。点坐标先做半开范围检查，再用 floor((point-origin)/resolution) 取得单元索引，不按最近邻四舍五入。负原点可用；上界属于 out_of_scope。仅在半开范围已检查后约束浮点除法的末位舍入，避免在上界内生成越界索引。

## 2 缺块与异常

- 清单未登记的逻辑块：unknown/missing_chunk，不能推断空闲。
- 清单登记但字节缺失：listed_chunk_missing，拒绝会话，不返回空间状态。
- 长度不符、摘要不符、未知编码、重复块或索引越界：拒绝会话。
- 范围外：out_of_scope；非法查询坐标报参数错误。

这个区别允许受控稀疏分发，同时保持损坏数据不会冒充未观测。全无分块也可解析，但所有范围内查询均为 unknown，不授予能力。

## 3 组件和扩展

当前恰有一个 required=true 的 occupancy 组件，编码必须支持。ESDF、定位参照、语义拓扑等只预留组件角色，不提供实际编码与消费者。

未知必需组件拒绝；未知可选组件记录 skipped_components。依赖必须存在且无环，支持的必需组件不能依赖被跳过的组件。本 Profile 的 components 只声明能力元数据，chunks 均属于唯一占据组件；未来多种实际载荷需要独立 Schema/Profile，不能仅增加 role 就声称集成。

## 4 固定来源与离线使用

清单绑定 scene、release、truth、machine view 的身份和摘要以及 frame。加载时调用方必须独立提供 expected_source，包括固定来源、frame 和 bounds；不能从待检查包本身取值回填。

pinned_voxel_source 可从通过 F04 内容关系检查的快照提取这些固定值。机器人读取时只需持有该固定元数据及本机运行包，不必加载完整真值、人视图或 F04 几何文件。当前 pin 不是签名、有效性凭据或可信来源；正式分发与可信配置仍需已有信任体系及 F06 适配。

本轮合成字节按独立测试配方生成，derivation 固定为 synthetic_fixture_not_voxelized。来源身份绑定不证明这些体素由对应几何派生，source_geometry_consistency_verified 始终为 false。几何体素化、独立覆盖证据及派生误差验证仍未实现。

查询返回固定 source、清单摘要和状态；robot_ready=false、authorized=false、validity=synthetic_unverified_only。离线读取不构成离线运行授权，不检查真实时效、撤回或机器人能力。

## 5 实现与资源

VoxelSession 接收不可变 bytes 的内存目录；复制索引并持有原字节，后续外部替换目录不改变当前会话。启动时验证所有登记块，查询仅读取当前块。它是受限全驻留实验，不实现磁盘按需加载、LRU、压缩或流式下载。

实验限制：最多4096块、16个组件、每文件8MiB、总包32MiB、总逻辑单元一千万。拒绝路径越界、大小写冲突、额外成员和非有限坐标。没有磁盘读取器或安装器；这些路径规则不能代替文件安装时的重解析点、锁和原子提交检查。

运行 `.venv/Scripts/python.exe -m experiments.scripts.measure_voxel_profile` 生成 examples/agent-voxel/synthetic 与目录外的 expected-source.json，同时写入 output/validation/voxel-profile-resources.json。

测量口径：包实际字节数、占据载荷字节数、加载耗时、增量 Python 分配峰值、1000次暖查询中位数/P95。输入 bytes 与 pin 在加载计时前已存在；Schema 本地读取计入加载，源 F04 校验和载荷磁盘 I/O 不计入。tracemalloc 不等于进程 RSS，也不包含事先分配的输入载荷。小样结果不代表大场景、ARM64 或机器人性能。

## 6 兼容与后续

既有 runtime.py、LocalPackages 与文件安装器只接受旧 synthetic-regions Profile；本轮不让旧客户端静默读取体素编码。已运行旧 agent 包、local、files 回归。

后续先完成 F06 请求/响应、时效与局部完整性协议，再设计显式 Profile 分派与已有安装器接入；真实体素构建、压缩与按需加载按实际数据和硬件实测推进。
