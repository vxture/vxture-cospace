# 数据模式

2026-10-28 新增 [NCLT ms25原生CSV预检](nclt-ms25-preflight-v0.1.md)：固定10列、整数微秒和单位来源、逐行数值与时间诊断。已有公开实测ms25字节验证，未取得激光或完成算法准入。

2026-10-28 新增 [P1离线bag预检报告](bag-preflight-v0.1.md)及 [Schema](bag-preflight-v0.1.schema.json)：标准PointCloud2/Imu原字节读取、布局与数值检查、整数纳秒统计和明确拒绝报告。未接入真实采集、算法准入或既有导入器。

2026-10-28 新增 [事件与追溯 F06c](trace-events-v0.1.md)及 [Schema](trace-events-v0.1.schema.json)：CloudEvents 字段子集、封闭实体/活动/责任主体图、进程内重复投递检查与 PROV JSON-LD 映射。只支持合成候选构建和检查，未接消息代理、持久化投递或正式发布。

2026-10-28 新增 [体素逻辑块变更 F06b2](voxel-change-v0.1.md)及 [输入Schema](voxel-change-v0.1.schema.json)：按index增删改、旧摘要/缺块前置条件、候选重建与块影响范围；候选版本不能由普通运行包读取器直接加载。

2026-10-28 新增 [领域变更集 F06b1](spatial-change-v0.1.md)及 [输入Schema](spatial-change-v0.1.schema.json)：固定基线、对象操作、几何/覆盖整资源替换和候选分支CAS实验。细粒度体素块操作、正式发布合并及事件追溯尚待后续增量。

2026-10-28 新增 [消费请求响应 F06a](consumption-v0.1.md)及 [Schema](consumption-v0.1.schema.json)：固定来源、历史/运行模式、时效、批量完整性和拒答。运行期请求统一拒答，不构成有效性门禁或HTTP升级。

2026-10-28 新增 [机视图占据分块 F05](agent-voxel-v0.1.md)及 [Schema](agent-voxel-v0.1.schema.json)：u8占据编码、三维分块索引、缺块/损坏区分、必需组件和离线点查询。独立实验，不静默升级旧 agent-package 安装器。

2026-10-28 新增 [真值与双视图发布组合 F04](spatial-release-v0.1.md)及 [Schema](spatial-release-v0.1.schema.json)：在独立合成快照中核验实际字节摘要与跨文档身份关系；采用记录与不可变内容清单分离，消除质量报告反向引用的摘要循环。不是现有 API 接受的新发布格式。

2026-10-28 新增 [质量与消费配置实验契约 F03](quality-profile-v0.1.md)及 [Schema](quality-profile-v0.1.schema.json)：固定质量规程与完整度分母、三态及诊断、用途与陈旧度声明；实验规则通过不构成发布或机器人授权。

2026-10-28 新增 [观测输入实验契约 F01/F02](observation-input-v0.1.md)与 [Schema](observation-input-v0.1.schema.json)：独立验证原始流元数据、局部坐标与控制/检查点。它不是现有导入接口接受的新格式，真实内容、外部证据及算法就绪仍须后续验证。

新增[交付报告生成上下文](delivery-generation-v0.1.md)及[Schema](delivery-generation-v0.1.schema.json)，用于合成报告0.2的批次、观察区间与来源关联；结构规范之外仍须检查摘要、日期及身份一致性，不建立认证或运行权限。

首个增量按以下顺序落地：

1. 共用身份、坐标、来源类别及文件校验信息。
2. 真值清单及人视图、机器视图实例清单。
3. 服务发布组合及必要验证记录。

字段与结构由模式校验；跨文件来源一致性、摘要、能力证据及版本引用由产品校验逻辑检查。模式校验成功不能替代独立质量验证或审核采用。

契约版本独立于真值、视图及服务发布版本。

当前已实现[合成服务包试验契约](synthetic-bundle-v0.1.md)及其[结构规范](synthetic-bundle-v0.1.schema.json)。本地检查器支持该规范所用关键词，并执行跨文件领域规则；不是通用JSON Schema引擎或正式发布格式。正式证据规则、兼容迁移及生产版本目录仍待细化。

最新实现已迁移到标准Draft202012Validator，保留字节数整数字面量策略及原有定位诊断；不再使用自制关键词执行器。新增[0.2空间查询profile](synthetic-bundle-v0.2.md)，0.1继续兼容。后续实现以根uv.lock为依赖基线。

新增[固定发布核对投影v0.1](release-inspection-v0.1.md)，描述data/ontology只读HTTP响应及内部快照兼容边界，不升级源包profile。

导入增量新增[请求Schema](import-request-v0.1.schema.json)、[dataset清单Schema](dataset-v0.1.schema.json)及[CLI错误Schema](import-error-v0.1.schema.json)。仅支持合成输入固定快照，不能用dataset登记替代真值采用或发布。

新增[合成检查任务v0.1](check-job-v0.1.md)及其[Schema](check-job-v0.1.schema.json)，用于固定输入检查、单次attempt及报告追溯，不升级空间候选、真值或服务发布契约。

新增[任务只读接口v0.1](job-reading-v0.1.md)，含分页、详情、输入及报告投影；与空间发布消费的有效性门禁分别管理。
