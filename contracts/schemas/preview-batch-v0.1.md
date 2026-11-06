# 采集批次与保存成果生命周期 v0.1

本批H1实现“资料组织批次＋构建准入＋固定来源”。不是设备采集控制器，不新增业务模块。批次属于**构建 → 数据管理**；批次不等于资料、构建任务、模型候选或固定发布。

## 状态与作用域

| 当前状态 | 允许操作 | 后续状态及副作用 |
| --- | --- | --- |
| draft（整理中） | replace_members | 完整替换成员，核对登记记录及同空间归属；不预检源文件 |
| draft且至少一项成员 | seal | 重新resolve全部源文件，固定成员与摘要，进入sealed |
| draft或sealed | disable | 记录原因与原状态，进入disabled，阻止以本批次发起新的资料构建 |
| disabled | restore | 返回停用前状态，保留固定成员和历史，不自动构建或发布 |

封存后不允许增删成员、改名或修改来源声明。补充资料建新批次；一个登记资料可出现在多个批次，构建必须明确选其一。停用其中一个不撤销其他封存批次的构建资格。已入队任务不追溯取消；已有几何之上的对象、业务、关系修订继续作为独立候选处理。停用不撤回发布、已导出包或消费端保存版本。

批次封存是元数据冻结＋当时源文件核对，不是底层文件系统写保护或空间精度验收。源文件仍须保持封存，每次构建依旧重新预检。origin=imported_sample表示导入样本，field_collection仅为人工现场采集声明，均未经独立核实；本版未采集设备ID、真实采集时段或操作人员认证。

## 数据模型

完整结构见[JSON Schema](preview-batch-v0.1.schema.json)。id、space_id、project_id为稳定标识；name、origin、note记录来源声明。revision初始0，每次成功变更加1，expected_revision使用严格非负整数，拒绝布尔和隐式字符串转换。

members是最多100项的完整集合，每项包含input_id、登记label和input_record_sha256。成员摘要对读取的完整登记JSON（含本机路径）使用`ensure_ascii=false, sort_keys=true, separators=(',',':')`规范序列化后SHA256，不依赖原JSON缩进。sealed_members_sha256采用同一算法对按input_id排序的members计算。它是工程内容绑定，不是签名或外部权威校准证据。

每次创建、调整、封存、停用和恢复在同一SQLite事务中保存当前记录及完整历史快照，保留operation、reason、updated_at。读取核对当前指针与最后一条历史一致。历史通过API只追加，数据库文件仍是可由本机管理员修改的工程存储，不是不可篡改审计账本。

独立存储在资料目录下`acquisition-batches.sqlite3`，Python标准库SQLite，无新服务依赖。构造、空列表GET不创建数据库，也不修改旧资料。首次创建批次才建表；无批次的历史输入继续兼容。当前为单服务实例的本机流程，不宣称通用分布式任务事务或物理断电验证。

## 接口

| 方法与路径 | 请求/响应 |
| --- | --- |
| GET /api/batches?space_id=ID | 必填空间，仅列本空间批次；不存在的空间404 |
| POST /api/batches | space_id、name、origin、note；创建draft，201 |
| GET /api/batches/ID?space_id=ID | batch（附history）、attempts、publications；读取保存索引，不poll任务或预检源文件 |
| POST /api/batches/ID/transitions | space_id、expected_revision、operation、reason；仅replace_members可且必须附input_ids |

请求禁止未知字段、空白说明、重复成员及跨空间成员。坏状态、过期修订、预检失败或存储异常409；Pydantic字段格式错误422；来源Origin不允许403。失败不增加修订或历史。操作人员仍为未认证的本机工程调用，空间匹配不等于用户ACL。

批次详情的attempts包括显式绑定本批次的几何任务及继承来源的语义/业务/关系候选；失败、中断保留。publications从保存的模型source.batch_ref定位，integrity=not_checked，只是成果索引；完整性和来源检查应使用成果目录/固定发布接口。不会仅因input_id相同把旧任务归到新批次。

## 构建绑定

POST /api/builds新增可选batch_id、batch_revision。若所选资料当前已纳入任何批次，省略batch_id返回batch_selection_required；选中的批次必须sealed、包含当前input_id、修订及登记摘要一致。未纳入任何批次的历史资料保持原构建行为。整理中或停用状态不能靠省略batch绕过。

准入期间使用SQLite写事务锁，直到任务记录和子进程启动步骤完成，再释放；并发停用按准入先后排序，不追溯取消已准入任务。源文件预检在入锁前完成，启动的实际构建再次核对源数据。SQLite与文件系统/进程并非跨资源原子提交，故障后由现有任务中断语义处理，不自动重试。

job.json和model.json的source新增相同batch_ref，包含batch_id、admitted_revision、sealed_members_sha256、input_record_sha256、space_id、project_id。构建完成和读取候选时检查两者一致。语义/业务/关系候选继承这份几何来源引用，固定发布与离线包保存同一model.json。旧模型不追加该字段，既有包profile保持兼容。

空间流程面板可据保存的batch_ref定位来源批次，说明这是“提交修订”，不把批次当前状态反写到历史模型或把当前停用等同历史发布失效。

## 后续成果生命周期边界

| 对象 | 当前行为 | 后续单列 |
| --- | --- | --- |
| 登记资料 | 内容固定、批次引用、每次构建预检；不删除 | 资料停用/归档与跨批次引用检查 |
| 构建尝试 | queued/running/succeeded/failed/interrupted，失败保留 | 取消、受控重试与保留期限 |
| 模型候选 | 独立快照、显式核对选择、保留基线 | 候选归档与可选择范围 |
| 固定发布 | 独立保存，批次停用后仍可查询/导出 | 发布停止分发、引用影响提示与历史访问规则 |
| 离线包/消费引用 | 随固定发布，消费端显式激活/恢复 | 撤回通知与可信离线有效性，不能靠网页停用实现 |

这些对象不共享一个“停用”开关。下一批先定义资料/候选/发布的引用影响和可执行状态规则，再实现受控操作；不引入级联删除。
