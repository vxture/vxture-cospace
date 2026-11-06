# 观测输入实验契约 0.1（F01/F02）

状态：结构与领域规则验证草案。不是现有导入接口支持的新格式，不构成真实算法输入就绪。

Schema：observation-input-v0.1.schema.json（JSON Schema Draft 2020-12）。专用校验器：packages/data/observation_contract.py。样例：examples/observation-input/equipment-synthetic.json。

## 内容与约束

- 原始日志成员固定路径、字节数、摘要、媒体类型与编码。流引用成员和通道，声明传感器、字段单位与含义、用途角色。多个传感器可共用一个日志成员。
- data_kind 区分真实和合成来源。允许真实元数据登记，不意味支持真实内容解码或发布。样例字节与证据摘要为占位声明，校验器不读取对应文件。
- 坐标首版仅支持米制右手局部笛卡尔 frame；轴和原点说明必须存在，其现场真实性不能由 Schema 判断。地理 CRS、垂直基准与工程坐标转换另定 Profile，局部坐标不附虚假 EPSG。
- 变换采用列向量 `p_target=T_target_source*p_source`，检查齐次末行、旋转正交性与行列式 +1；不接受反射或缩放。首版每个 source 至多一个父 frame，禁止循环；允许多棵尚未对齐的树，未连接或 unverified 的变换不能用于融合。变换绑定本次输入快照，跨时段适用性尚未定义。
- 原始时间保留 clock_id、时间尺度、单位和时间戳含义。未验证时允许缺 UTC 区间，不生成虚假映射。verified 必须有 UTC 起止、同步误差和映射证据引用；字段齐全并不证明同步经过实测。UTC 使用 RFC3339 的 Z 形式。
- 控制点与独立检查点分开。独立检查点必须 used_for_fit=false 且 used_for_tuning=false；稳定 point_id 防止同一记录重复。不同 ID 是否对应同一实体、资料是否真正独立仍需流程检查。
- evidence / mapping_ref 是带摘要的外部记录引用；本校验器只检查结构，不解析引用或证明来源。uncertainty_m 需由后续测量规程明确置信水平与统计口径，当前不用于精度等级判定。
- 禁止未知字段、悬空 frame/member、重复身份、非有限数、反向时间区间及明显越界成员路径。路径检查不替代受控封存、符号链接与真实字节摘要检查。

## 校验结果边界

返回 metadata_valid=true，始终返回 payload_verified=false、evidence_verified=false、algorithm_ready=false、real_release_ready=false。不修改旧 synthetic-bundle / dataset / agent-package 契约，不推断导航、定位或质量结论。

后续真实适配需补齐：日志解码与字段核实、原始时间范围/映射模型、同步漂移测量、标定有效期与测量不确定度口径、不可变证据解析、用途隔离核对、实际文件封存与算法专用输入门槛。
