# 独立本体实例契约 v0.1

日期：2026-11-20。B02 候选契约。权威结构定义为 `packages/ontology/kernel/instance.schema.json`（JSON Schema Draft 2020-12），安装独立包后通过 `vxture_ontology.instance_schema()` 取得。候选园区规则通过 `park_baseline_rules()` 取得。两者为独立资源，不读取宿主配置或实例数据库。

## 所属与边界

`vxture.ontology-instances/0.1` 是 L3 消费方实例交换包。消费方负责实例存储、来源接入、现场核验和授权；本体产品提供定义、契约与后续纯校验能力。不添加 CoSpace 用户、租户、场景 ID、地图 SDK 或商业限制字段。`namespace` 是消费方给出的全局命名空间 URI，不是权限边界，URI 不自动请求网络。

包字段：`profile`、`package_id`、`namespace`、`synthetic`、`title`、`generated_at`、`definition_refs`、`sources`、`evidence`、`entities`、`assertions`、`frames`、`geometries`、`geometry_bindings`、`coverage`。所有集合字段必须出现，允许为空的集合按 Schema 定义。对象未知字段拒绝。

首版采用单命名空间、自包含引用，不接受指向包外的实体、来源、证据或几何 ID。需要联邦引用时另立契约，不猜测不存在的实体。实例包不包含本体定义副本，消费方必须同时提供准确的定义及完整依赖闭包。

## 身份、定义与来源

实体身份为 `(namespace, entity.id)`，与名称、包 ID、外部编号、几何 ID 分离。同一命名空间后续导出可保留实体 ID；不同包 ID 不意味着不同实体。跨命名空间即使同名、同局部 ID 或相同资产编号也不自动合并。各集合内部 ID 唯一，实体与断言使用各自独立 ID 空间。

`definition_refs` 为精确 `{module_id, version, sha256}` 列表，每个模块 ID 唯一，包含传递依赖；摘要采用定义内核 `canonical_bytes`。只对这些固定模块解析 `module:concept` / `module:relation`，不回退到最新版本。草案可用于工程验证，固定摘要不代表正式发布或专家签核。

`sources` 包含来源 ID、`system`、`scope`、`revision` 和 `synthetic`。实体 `source_bindings` 包含 `{source_id, external_id}`，是来源记录关联，不是默认等价或自动归并规则。一个来源记录若描述多个实体，须另有匹配依据；首版不执行自动实体消歧。

`evidence` 包含 `{id, source_id, record_key, recorded_at, description}`。可据来源系统、作用域、修订与记录标识追溯依据；本版不嵌入附件、不下载 URI、不证明附件存在或现场真实。合成包所有来源 `synthetic=true`，真实包所有来源为 false；混用须拆包，避免合成内容冒充真实事实。包中的证据也必须来自所声明来源。

## 实体与属性

实体字段为 `id`、`type`、`properties`、`source_bindings`、`evidence_ids`，可带 `valid_time`。实体仅声明一个最具体概念类型，继承语义从固定定义解析。

属性是 `{value, source_id, evidence_ids, unit?, quantity?}`。`value` 为字符串、有限数值或布尔值，不使用 null 表示未知，不把对象引用塞入字符串属性。必填、数据类型、最小值、单位和量种按概念及全部继承属性校验；未声明属性拒绝。布尔值不能冒充整数/数值。整数按 JSON 数学整数解释。单位与量种成对出现，只接受定义声明的准确值，首版不做换算或单位别名匹配。

缺少可选属性表示未记录；缺少必填属性是契约不满足。不用空字符串、0 或 false 填补未知值。属性来源和证据与关系断言分别声明。铭牌额定参数不等于观测值，本版不把属性对象冒充完整时序观测协议。

## 断言、有效时间与完整性

关系断言字段为 `id`、`relation`、`subject_id`、`object_id`、`source_id`、`evidence_ids`、`valid_time`、`epistemic_status`。端点必须在本包中存在，类型可为关系端点声明的子类型。对称关系不要求存两条边，也不自动补逆向存储。重复同一断言 ID 拒绝，不按名称或几何近邻生成边。

`epistemic_status`：`reported` 为来源报告；`corroborated` 为消费方声明已有佐证；`disputed` 为有争议报告。均不是引擎认定的现场真值。基数与层级规则只计算 reported / corroborated，disputed 保留用于冲突诊断，不当作已满足所需关系；不能任意选一条覆盖争议。

时间统一使用真实有效的 UTC 日历时间 `YYYY-MM-DDTHH:mm:ss[.ffffff]Z`，最多六位小数，不接受闰秒。结构校验须启用实际可用的 `date-time` 格式检查，不能依赖格式注解；某些 JSON Schema 安装不含可选日期检查器。样例测试用标准库日期解析补足此检查。

`valid_time={start,end}` 使用半开区间 `[start,end)`；end 为 null 表示向未来开放，不表示结束时间未知；有限 end 必须严格晚于 start。未知开始时间不能编造为已有有效指派，应保留在消费方待核对数据中。`generated_at` / `recorded_at` 是包生成/证据记录时间，不替代业务有效时间；允许有依据的追溯录入。

候选规则集 `vxture.ontology-instance-rules/0.1` / `park-baseline@0.1.0` 是显式选择的领域规则，不是安装某概念就自动启用的全行业强制要求。规则集随包分发，执行时应锁定版本与规范编码摘要，校验结果记录这一选择。调用方可另行提供版本化规则集；不能静默修改规则来使实例通过。

| 概念（包括子类） | 必需出向关系 | 基数 |
| --- | --- | --- |
| 建筑空间范围 | 对应建筑实体 | 1 |
| 入驻指派 | 入驻组织 / 入驻空间 | 1 / 至少 1 |
| 空间用途 | 用途空间 | 1 |
| 设施职责指派 | 责任组织 / 职责对象 / 职责管理范围 | 1 / 至少 1 / 至少 1 |
| 资产记录 | 记录描述对象 / 记录管理组织 | 1 / 1 |

所有角色指派及其子类必须有有效期。角色关系有效期不得超出角色有效期；每个必需关系在整个指派区间应满足基数，不能用只覆盖半年的关系满足全年的指派。按重叠区间中的不同目标计数，同一目标的多份支持证据不重复计数；将争议关系标为 disputed 不能补齐缺失端点。非角色概念的完整性按其活跃断言区间逐段检查，且至少存在满足最小基数的活跃断言。

`spatial_part_of` 在重叠有效区间内禁止自指与环，且最多一个直接父空间；不同时间可以重组。不得要求所有空间均有父空间，顶层空间可没有父空间。管理范围允许与园区空间重叠，未规定必须属于园区层级。不从管理范围相交推导职责、从入驻推导所有权、从成员关系推导功能连通。

## 空间与几何

`frames` 首版仅支持 `local_cartesian`、米制、右手 XYZ，坐标含义由 description 明确；样例为合成局部坐标，没有 WGS84/EPSG 或定位精度承诺。未来地理参照和坐标转换通过另行版本化的适配契约处理，不将未知坐标冒充经纬度。

`geometries` 用独立 ID 引用 frame，支持 `point3`（三维点）和 `box3`（min/max 三维包围盒）；坐标必须有限，每轴 max 严格大于 min。包围盒是简化空间表达，不是精确建筑模型或合法边界证明。

`geometry_bindings` 包含 `entity_id`、`geometry_id`、`purpose=placement|extent` 及来源/证据。空间区域采用 extent，物理对象采用 placement 或 extent；角色、组织和信息记录不直接绑定几何，须通过显式语义关系定位其对象。首版允许实体没有几何，查询返回未记录；不能据此宣称实体不存在。几何绑定不生成 located_in 或 spatial_part_of，也不自动执行相交、包含、距离和通行推理。

## 覆盖和未知

`coverage` 描述某来源对指定空间实体、概念、关系及有效区间的覆盖声明，状态为 unknown / partial / complete。没有覆盖声明默认为未声明完整性。complete 是来源声明，不是现场完备性证书，不授权自动否定。

查询结果须分开表达：未记录（无断言）、未知（信息不足）、冲突（有效证据/断言相互矛盾）、不满足（已给输入违反某条明确约束）。本批不实现这些查询返回接口。即使声明 complete，也不能在缺少独立闭世界业务规则和核验的情况下把“未记录备用设施”当作“不存在备用设施”。

## 预算、诊断与批次界线

首版输入预算拟定 4 MiB UTF-8、32 个模块引用、10,000 实体、20,000 断言；其他集合和文本长度以 Schema 为准。B03 解析器须在解析前检查字节预算，并拒绝重复 JSON 键、非有限数值和超预算输入。JSON Schema 不负责字节预算、解析重复键或所有跨记录约束。

B02 已执行 Schema 与样例一致性检查。B03 才提供纯实例语义校验 API，解析实体/证据/来源引用、端点类型、继承属性、基数、时态、层级和几何约束。候选反例矩阵位于 `tests/fixtures/ontology-instances/negative-matrix.json`：schema 阶段当前应拒绝；semantic 阶段当前只确保结构合法，不假称已被拒绝。

矩阵的 `expected.path` 是需要定位的输入字段或缺失位置；B03 诊断含 code、JSON Pointer path，图环等全局问题允许主路径加 related_paths，删除关系的基数错误应定位角色实体而不是不存在的数组元素。诊断是可核查的结构/语义结论，不是真实性、专业合规或授权证明。
