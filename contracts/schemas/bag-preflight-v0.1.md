# 离线 bag 内容预检报告 v0.1

日期：2026-10-28。对应 P1/E01a；实现 `packages/data/bag_preflight.py`，报告 Schema 为 [bag-preflight-v0.1.schema.json](bag-preflight-v0.1.schema.json)。

## 输入与格式选择

首个适配器限定 ROS1 bag v2 容器，选定两个不同话题，内容分别为标准 `sensor_msgs/PointCloud2` 与 `sensor_msgs/Imu`。使用可选依赖 `rosbags==0.11.9` 在根 Python 3.14 环境离线读写，无需安装 ROS 或运行 roscore。使用 Noetic 类型定义只是解释旧消息格式，不将 Noetic 发行版设为产品运行基础。

这是当前已有 P1 工具的兼容输入选择，不是长期采集格式冻结。MCAP、ROS2 SQLite、Livox 自定义消息、PCD/PLY 和其他厂商格式后续分别适配；解析库支持某种格式不等于本适配器已支持。

从输入文件读取一次有上限的字节快照，在临时副本上解码，报告摘要绑定该副本。`expected_sha256` 可传入已登记成员的摘要；没有传入时只能报告观察到的摘要，不能声明来源已核对。原始文件、来源声明、角色和证据仍由观测输入契约/受控封存流程负责。本增量未自动接入既有 dataset 导入器或 F01/F02 清单。

## 报告字段

| 字段 | 定义 |
|---|---|
| schema_version / format | `cospace.bag-preflight/0.1`；`ros1_bag_v2` |
| input.bytes / sha256 | 完整捕获字节的长度和摘要；读取失败或超限时为 null，不将截断前缀摘要冒充完整文件摘要 |
| input.expected_digest_verified | 仅表示捕获字节符合调用方传入的摘要；不表示来源可信或实测资料真实性 |
| streams | 按话题记录类型、角色、消息数、通过点内容检查的点数、坐标标识、字段布局和时间统计 |
| header_start_ns / header_end_ns | 原始 header 时间的整数纳秒范围；不推断 UTC，不以浮点秒丢失精度 |
| backward_steps / duplicate_steps | 按 bag 记录时间遍历消息时，header 时间的倒退/重复次数 |
| header_time_overlap_ns | 两流 header 数值区间的交集；数值重叠不证明同一时钟或完成同步 |
| errors | topic + code 的诊断集合；损坏/不支持输入产生 bag_decode_failed 等明确失败 |
| structural_precheck_passed | 本 Profile 的结构/数值前置检查是否通过；至少两个消息/流及正时间重叠 |
| unverified | 来源角色、点时间单位和参考、同步、外参、IMU约定和姿态、独立质量仍未核验 |
| algorithm_ready / real_release_ready | 始终 false |

报告不根据文件格式推断 data_kind；合成夹具身份记录在试验 summary 内。真实资料必须另有来源与使用条件登记。

## 校验范围

验证消息类型及其标准 MD5 定义标识，拒绝自定义布局冒用标准消息名。逐条检查 header、非空且稳定的 frame、严格递增时间。激光检查每条消息的字段定义与稳定性、行/点步长、字节长度、字段边界/重叠、大小端和所有 XYZ/点时间值。XYZ 必须是浮点标量，点时间必须恰有一个 `time` / `t` / `timestamp` 数值标量；名称被识别不意味着单位或绝对/相对语义已确认。IMU 检查加速度和角速度有限值，不把单位四元数或零协方差当成有效姿态证据。

未知点、退化和冲突等空间状态不由此报告生成。非有限原始点导致本预检拒绝，不静默删除后宣称数据完整。

试验上限为32MiB文件、20,000条选中话题消息、单消息2MiB、每云100,000点。限额用于小型短序列适配，不代表性能指标。底层 bag 块解压和反序列化先于部分限额检查，这不是针对不可信压缩数据的内存沙箱；实际大日志和不可信输入接入需独立进程硬限额与分块读取设计。

## 可复跑入口

```powershell
uv sync --locked --extra input
.venv/Scripts/python.exe -m experiments.scripts.inspect_bag_offline input.bag --lidar-topic /points_raw --imu-topic /imu --output output/new-preflight.json
.venv/Scripts/python.exe -m experiments.scripts.smoke_bag_offline --output experiments/runs/全新运行目录
```

CLI通过为0、内容拒绝为2；参数和输出冲突拒绝执行。输出必须是新文件，不能覆盖输入。烟测通过库 Writer 生成真实容器字节，再执行 CLI Reader，不模拟解码返回值。输入 bag 文件不进版本历史；运行记录保留输入摘要、实现/锁文件摘要、依赖、原始命令、实际退出码和报告。
