# NCLT ms25 原生 CSV 预检 v0.1

日期：2026-10-28。实现 `packages/data/nclt_input.py`。报告版本 `cospace.nclt-ms25-preflight/0.1`，用于独立P1实验，未接入既有导入或正式发布。

## 原生格式与来源

NCLT官方ms25读取示例声明以下10列、无表头CSV；原始文件按ASCII解释，不改变行顺序，不转换为虚构的标准IMU消息：

| 列（从0起） | 字段 | 官方示例声明的单位 |
|---|---|---|
| 0 | utime | 微秒，保留整数；未在本适配器中建立UTC/同步映射 |
| 1—3 | mag_x / mag_y / mag_z | Gauss |
| 4—6 | accel_x / accel_y / accel_z | m/s² |
| 7—9 | rot_r / rot_p / rot_h | rad/s；角速度，不是姿态角 |

证据为 `experiments/evidence/2026-10-28/public-input-review-002/nclt-ms25-reader.txt`。同时保存了官方旧版ROS转换示例；该示例写出mag/accel/rot三路Float64MultiArray，不能视为现有PointCloud2/Imu适配器可直接消费的sensor_msgs/Imu。

原CSV单位声明与坐标轴/外参是不同前提。本增量不改变符号、不补四元数、不默认为单位外参，不根据加速度接近重力值来声称已完成标定。

## 报告定义

| 字段 | 定义 |
|---|---|
| input | 完整捕获字节的bytes/sha256；expected_digest_verified仅表示符合调用方给定摘要 |
| columns | 固定列名和declared_unit；来自官方说明，不是实测单位验证 |
| rows_seen / valid_rows / invalid_rows | 遍历、数值结构合法和不合法行数；异常行不静默删除后放行 |
| time | 原整数微秒范围、倒退/重复次数、正间隔最小/最大值；不由此认定采样稳定或时钟同步 |
| ranges | 合法行各数值列的最小/最大值；有错误时仅为部分统计，不能视为完整成果 |
| errors | code与row（文件级诊断为null）；最多32条，原始错误行总数仍由invalid_rows保留 |
| structural_precheck_passed | 恰为10列、时间为正64位整数、其他值有限、至少两行且严格递增；仅该Profile通过 |
| algorithm_ready / real_release_ready | 始终false |
| unverified | 激光、时钟映射、坐标轴和外参、IMU姿态、独立质量仍未核验 |

单文件64MiB、最多1,000,000行；CLI超过字节限额直接拒绝，不对前缀输出完整文件摘要。错误、超限或不完整解析都不放行。

## 入口与资料保存

```powershell
.venv/Scripts/python.exe -m experiments.scripts.acquire_nclt_sensor --output var/public-input/全新目录
.venv/Scripts/python.exe -m experiments.scripts.inspect_nclt_ms25 var/public-input/全新目录/ms25.csv --expected-sha256 采集记录中的摘要 --output output/全新报告.json
```

获取脚本仅下载固定2013-01-10官方sensor archive，上限32MiB。仅按basename查找唯一普通ms25.csv成员，写固定输出名，不使用extractall或归档路径作为输出路径。保存完整压缩包及成员摘要，未获得官方预发布校验和，因此本地SHA256是内容固定记录，不是独立来源真实性认证。大原始数据保存在被忽略的var目录，证据与报告进实验记录。

NCLT数据使用ODbL1.0与DbCL1.0，按官方要求保留来源、论文引用和适用的数据再发布条件；数据许可与本项目软件代码许可分别记录。本轮只将资料用于内部开发输入验证，未将其登记为现场独立检查资料或正式空间成果。
