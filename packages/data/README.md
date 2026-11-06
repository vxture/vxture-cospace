# Data

数据管理平台模块，负责资料登记、固定数据集、内容引用、来源条件、成果血缘及保留检查。对象存储和数据库由技术基础实现。

数据登记不等于独立质量通过；正式采用、发布和撤回状态由lifecycle负责。引用采用固定身份与摘要，避免反向导入所有领域对象。不能删除有效发布仍依赖的必要资料或证据。

`bag_preflight.py`为P1独立离线ROS1 bag预检适配器，依赖可选 `input` extra。检查标准PointCloud2/Imu的实际字节、时间、布局和数值，algorithm_ready始终false；不自动接入旧导入链路。见[报告契约](../../contracts/schemas/bag-preflight-v0.1.md)。

`nclt_input.py`检查NCLT原生ms25 CSV，保留整数微秒与官方声明单位，已用于公开真实传感器字节核对。它不虚构sensor_msgs/Imu、姿态或外参，见[格式定义](../../contracts/schemas/nclt-ms25-preflight-v0.1.md)。

`preview_lidar.py`将逐消息封存的受限ROS1激光样本接入预览登记/构建链路，复用bag_preflight并保留现有限额。核对全部消息，仅首帧生成传感器局部候选，不使用IMU/参考位姿配准。需要input与preview extras，见[格式契约](../../contracts/schemas/preview-lidar-single-frame-v0.1.md)。原独立bag_preflight CLI行为保持原样。

validation.py已支持合成文件登记、包内路径、字节数和摘要检查；preview_*提供NYU与受限ROS1样本的本机登记及来源追溯。尚无通用真实采集批次接入、完整数据集管理、许可审核或归档功能。详细计划见[平台规划](../../docs/architecture/数据管理与语义本体平台规划-v0.1.md)。
