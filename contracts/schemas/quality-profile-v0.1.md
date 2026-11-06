# 质量、状态与消费配置实验契约 F03 v0.1

日期：2026-10-28。Schema：quality-profile-v0.1.schema.json。状态：元数据与规则实验，不接入正式发布和机器人运行门禁。

## 1 三种独立文档

共同 schema_version 为 `cospace.quality-profile/0.1`，kind 分别为 profile、assessment、observation；Schema 根 oneOf 分派，不接受混合文档。

| 文档 | 作用 | 固定引用 |
|---|---|---|
| profile | 消费用途、模式、目标范围、精度/覆盖/语义要求与最大陈旧度 | 质量规程、目标范围和目标对象集的身份与摘要 |
| assessment | 某真值在确定范围的评估声明 | 真值、规程、范围、网格分区、目标对象与检查点集合 |
| observation | 某网格单元的空间判断及诊断 | 真值、范围、frame、cell_index、证据 |

样例容器 examples/quality-profile/equipment-synthetic.json 仅为三个文档的测试集合，各内部文档分别校验。样例摘要是占位符、质量数值是测试值，既非实测资料，也非工程验收阈值。

## 2 范围与完整度

首版实验采用局部米制均匀三维网格。bounds 为下界包含、上界不包含的目标包围盒，cell_size_m 是三轴一致的网格尺寸；原点为 bounds 下界。各轴长度必须整除 cell_size_m，单次至多一千万单元。不支持不规则目标边界、掩膜与分辨率混合，这些需要后续 Profile。

总分母由 bounds 和尺寸计算，不相信上报 total_cells。observed_free、occupied、unobserved、degraded、conflict 是互斥分区计数，和必须等于目标单元总数；这里的五种分区是统计口径，不改变三态查询枚举。多重诊断在生成分区时按 conflict→degraded→unobserved 优先归类，每个单元只计一次。

observed_ratio=(observed_free+occupied)/total_cells，表示无退化或冲突的已观测空间比例，不表示可通行率。现校验器只检查汇总数值一致性；未读取 partition_ref 对应分区，不证明真实无重叠、完整覆盖或诊断归类正确。

语义完整度独立采用 confirmed_count/required_count；profile 固定目标对象集引用和期望对象数量，assessment 必须匹配。分母为零返回 null，不假定为100%；要求正语义覆盖而无目标对象时不满足规则。几何覆盖与语义确认不能互相代替，也不合成为一个总分。

## 3 状态与诊断

state 只有 occupied、observed_free、unknown。reasons 可包含 unobserved、degraded、conflict；已知状态不能同时声明 unobserved。已知判断需要证据，退化/冲突需要诊断证据，unknown 必须带原因。

normalize_observation 保留原始证据与诊断，遇 degraded/conflict 一律保守输出 unknown，不修改输入。空间单元 cell_index 为从目标下界起算的三个非负整数。当前未解析范围引用，故不检查该索引是否越界；与真实范围及真值的固定绑定在 F04/运行查询适配中完成。文件损坏、未授权、版本错误及 out_of_scope 不编码为这些三态。

## 4 质量规程与等级

rule 引用固定 procedure_ref，metric 首版仅为独立检查点三维位置 RMSE（米）。max_error_m=null 表示限差待定，geometry.value_m=null 且 basis=not_assessed 表示未评估；两种情况均不能算作质量通过。basis=independent_declared 只是声明，不意味着已验证独立性。

grade_label 为可空标签，不设置内建 A/B/C 数值映射。要形成正式等级，仍需规程定义检查点布置、独立性、残差来源、统计口径、限差与适用用途；仅给 RMSE 不足以证明局部最大误差或定位能力。量测、浏览、查询和重定位用途记录在 purpose 中，当前共用这一实验规则子集，尚未覆盖各用途完整条件。

## 5 时效与实验判定

operational 模式必须给 max_age_s；historical 可明确设为 null。UTC 时间必须为带秒的 RFC3339 Z 表达。评估时间由调用方显式传入，不能读文件修改时间；时间区间反向、观测晚于评估时刻均拒绝。

全范围时效保守使用 observed_from，即最老观测，而非最近一个观测。age==max_age_s 仍满足；超限返回 stale_observation。历史读取不等于运行期授权。这里只验证单一观测区间，混合新旧区域的局部时效以及可信时钟、撤回与 valid_until 留待 F05/F06。

evaluate_quality 核对场景、坐标、范围、规程及目标对象集，计算覆盖/语义比例、几何限差和时效。失败返回原因列表；全部声明满足也只返回 declared_limits_met=true。evidence_verified、authorized、robot_ready、real_release_ready 始终为 false，禁止当作生产门禁。汇总指标通过也不允许调用方将某个 unknown 单元解释成空闲。

## 6 后续接入边界

Schema 和专用领域校验器必须配合；Schema 本身不判断日期、分母和引用一致性。所有外部摘要与证据引用尚未解析。正式接入前需验证范围固定时间与真实性、原始分区计数、对象确认记录、独立检查点、规程批准及内容摘要。既有 synthetic-bundle、空间查询与 agent-package 保持原协议，不执行静默迁移。
