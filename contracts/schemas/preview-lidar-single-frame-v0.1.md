# 激光单帧预览适配器契约 v0.1

格式标识为 `ros1_lidar_single_frame`。这是从受限ROS1样本中生成传感器局部候选的工程适配器，复用既有登记、预检、构建、双视图与固定发布流程。它不代表任意ROS bag的通用建图格式。

## 输入与核对

封存目录必须包含 `sample.json` 和 `sample.bag`。清单profile为 `cospace.external-lidar-specimen/0.1`，声明bag字节数/SHA256、半开记录时间窗口、各topic数量、按记录顺序的消息证据及首帧引用。每条消息证据包含topic、记录时间整数纳秒、序列化字节数和SHA256；含header的消息同时记录frame_id和header时间整数纳秒。两类时间分别保存，不推断时钟已同步。

适配器先核对bag摘要及既有PointCloud2/Imu结构预检，再从固定字节副本解码标准ROS1消息，逐项核对消息清单、窗口、topic数量及首帧来源。当前需要清单中唯一以 `/imu` 结尾的topic。未知消息定义、证据不一致、布局或数值检查失败均拒绝。

保留既有预算：bag最多32 MiB、最多20,000条消息、单消息最多2 MiB、单点云最多100,000个点；sample.json最多256,000字节。更大原始包须先提取受限样本，不通过提高限额直接导入。

首帧必须含XYZ、range、intensity字段。仅保留有限XYZ、非零XYZ且range大于0的点，强度必须有限；有效点数必须与清单一致。保留传感器局部XYZ，米制来自ROS约定及清单声明，未经过独立计量验证。其余点云、IMU和参考位姿只作来源核对，不参与配准、运动补偿或融合。

## 登记绑定

来源配置显式填写format和snapshot，省略tracking；非空tracking会被拒绝。NYU格式仍要求tracking，不改变旧行为。

登记记录包含：id、label、format、snapshot_sha256、bag_sha256、bag_bytes、input_frames、used_frames=1、verified_messages、selected_frame、frame_id、unit、valid_points，以及已有空间/项目归属。snapshot_sha256是sample.json原始字节摘要；selected_frame固定绑定topic、记录时间、header时间、frame_id、序列化字节数及消息摘要。

构建前重新核对上述完整来源绑定，拒绝登记后变化的资料。输出目录必须尚不存在。

## 同源候选与两类视图

| 产物 | 数据定义 |
| --- | --- |
| spatial.npz | 首帧有效点XYZ、原始强度、派生灰度颜色；当前规范候选几何 |
| human.ply | 二进制小端XYZ与RGB通道；通道内容为强度归一化灰度，不是相机RGB |
| agent.npz | 0.1米分辨率的表面证据单元索引；未列出区域为unknown |
| model.json | cospace.real-model-preview/0.1；绑定来源、坐标声明、构建方法、成员摘要及双视图 |
| views.js | 简化浏览器预览数据，显示坐标经过小数位裁剪，不作为几何权威源 |

model的data_kind为 `real_lidar_sensor_local_candidate`，construction.method为 `single_sensor_frame_no_registration`。双视图引用同一spatial.npz摘要。单元查询只返回surface_candidate或unknown，不推导已观测空闲、可通行性或ESDF距离。

初始候选没有语义对象；后续通过[对象标注契约](preview-objects-v0.1.md)生成新候选，确认状态保持unverified。坐标使用原始sensor frame，不能套用NYU的相机轴定义。

## 发布与消费

继续复用既有固定发布及点/对象查询，不新增第二套服务协议。无对象离线包为0.1，含对象包为0.2；读取器兼容两版。发布固定候选身份、模型摘要、来源及空间归属；新标注不改写旧发布。

quality.grade保持unverified，algorithm_ready、real_release_ready、robot_ready保持false。本适配器没有SLAM、去畸变、多帧注册、全局坐标、自由空间推断或独立精度验收，不能作为完整底图或机器人运行授权。
