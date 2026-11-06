# 合成空间查询契约 0.2

标识：cospace.synthetic-bundle/0.2。结构见[JSON Schema](synthetic-bundle-v0.2.schema.json)。0.1仍支持清单校验；0.2是显式新profile，不为0.1静默添加能力。含义仍为试验性合成包，不是正式真值或发布格式。

## 空间证据

真值及两类视图固定引用同一个coverage文件，文件与其他内容一样登记路径、字节数及SHA256。coverage绑定场景、坐标系和目标范围，列出证据与区域。所有证据明确为synthetic_observation并有描述，不代表真实传感观测。

区域采用轴对齐包围盒，仅用于最小查询语义验证；目标范围和区域均使用左闭右开区间[min,max)，最大边界属于范围外或相邻区域。盒子必须有正体积且位于目标范围内。它们不能替代真实点云、体素或可通行计算。

occupied与observed_free必须引用存在的合成证据，reason为synthetic_observation。unknown注明unobserved、conflict或degraded；conflict/degraded必须有诊断证据引用。未知区域不能因与空闲区域重叠就降为空闲。

查询规则：范围外为out_of_scope；范围内无区域命中为unknown/unobserved；占据与空闲同时命中为unknown/conflict；命中显式unknown时保留未知（原因优先级conflict、degraded、unobserved）；其余返回一致状态及证据ID。无区域代表无已登记证据，不代表已观测空闲。

机器视图和发布增加synthetic_point_query能力，人视图仍仅reference_reading；本轮人视图只具备手工清单及共用证据引用，没有渲染验证。两类视图共用内容不代表已实现真实自动派生。无量测或重定位能力声明。

## 固定读取与错误

本地服务一次读取、校验所有引用后，持有隔离的内存内容；后续查询不重新读取可能改变的文件。响应携带scene_id、release_id、truth_version_id、视图集合、frame_id、包入口摘要和发布摘要。未提供多版本指针及撤回，不得作为生产服务使用。

请求携带场景、发布、坐标及三个有限数值的点。版本或坐标不匹配是错误，不返回空间unknown。加载时文件损坏或引用不符直接拒绝启动，新服务不能从损坏内容返回状态；已加载快照保留原字节含义。入口摘要只绑定内容，不提供签名或来源可信保证。

API通过POST /sample/query查询，GET /sample返回载入版本。错误字段和HTTP约定见[API说明](../../apps/api/README.md)。CLI与API共用SampleService和空间规则。此profile不支持单位换算、坐标变换、栅格粗化、射线或范围查询。
