# 对象与业务台账绑定 v0.1

归属：定义 → 空间关联。对象语义来自固定本体；设备业务字段独立存放于固定台账记录，不能塞入本体属性绕过约束。本阶段只支持本机工程师手工登记设备台账，不抓取或同步外部系统，不记录巡检事件，不实现对象间关系。

## 台账登记

`POST /api/ledger`请求包括space_id、source_system、external_id、version、title和fields。fields仅允许asset_code、manufacturer、model、serial_number，均为最多100字符的字符串，可省略为默认空值。来源系统、业务标识、版本和名称必须非空白；长度上限分别80/100/40/100。不接受额外字段或客户端声明已确认。

```json
{
  "space_id": "space-6fe7d4c455774cb2",
  "source_system": "local-assets",
  "external_id": "TEST-PUMP-001",
  "version": "1",
  "title": "流程测试设备台账（非现场资料）",
  "fields": {"asset_code": "TEST-001", "manufacturer": "流程示例"}
}
```

结果为created与ref、record。record的profile为cospace.preview-ledger/0.1，包含ledger-加16位随机十六进制record_id、项目/空间归属、创建UTC时刻、固定confirmation=unverified及请求内容。ref包含record_id和sha256。

摘要计算：将规范化后的完整record以UTF-8、键排序、无多余空白、ensure_ascii=false、allow_nan=false编码，计算SHA256。JSON缩进不是身份；所有默认设备字段会在规范化record中补齐空字符串。

同一空间、source_system、external_id、version构成业务版本键：相同内容重复登记返回原记录created=false；同键不同内容409 ledger_version_conflict，更新必须给新version。版本是显式不透明字符串，不按语义版本或时间自动比较新旧。登记后不提供修改/删除接口；本机存储不构成防篡改或可信签名。

`GET /api/ledger?space_id=...`返回该空间records，每项为ref＋record；无记录返回空数组，读取不创建目录。space_id必填，历史未关联记录不进入台账绑定；服务端检查空间存在及项目归属，不等于用户授权。

## 完整绑定集与候选生成

`POST /api/business-candidates`：

```json
{
  "space_id": "space-6fe7d4c455774cb2",
  "base_candidate_id": "build-a16bfad1237544bf",
  "base_manifest_sha256": "实际基础候选model.json的64位SHA256",
  "bindings": [
    {"object_id": "os1-test-anchor-001", "ledger_ref": {"record_id": "ledger-0000000000000000", "sha256": "实际台账记录的64位SHA256"}}
  ]
}
```

示例摘要和record_id占位，提交须使用实际引用。Schema见[JSON Schema](preview-business-v0.1.schema.json)，覆盖LedgerDraft、LedgerRecord、BusinessRequest及BusinessSnapshot。

基础必须是同空间、完整且摘要匹配的语义候选；bindings为完整集合，最多100项，同一object_id最多一项。对象ID须存在于基础语义快照；台账引用必须匹配固定record_id＋摘要及同空间归属。一个台账可被多个对象引用，不据此推导重复设备或业务唯一关系。

bindings=[]表示新候选解除全部业务绑定，不能解释为无改动。页面对完整绑定集和解除操作要求显式确认。API仍以完整集为准；它不执行差量补丁、自动关联或审批。新增绑定、解除或换版均生成独立候选，不直接修改当前选择或发布；之后沿已有候选核对→选择→独立发布流程。

若引用已保存在基础候选的完整业务快照中，可继续使用该固定记录，即使本机台账目录缺失或后来改变；新引用仍须从本机登记目录按摘要解析。普通对象修订自动保留仍存在的稳定对象ID绑定；移除对象时对应绑定和不再使用的台账快照一起移除，不做名称模糊匹配。

## 固定模型快照

新的候选沿用现有几何、对象本体及锚点，添加business.json和model.json.business_association：path固定business.json，binding_count为完整绑定数。members绑定business.json字节摘要和大小；不改变现有objects.json v0.1结构。

business.json profile为cospace.preview-business/0.1，包含model_id、space_id、project_id、objects_sha256、bindings、records及confirmation=unverified。records是仅被bindings引用的去重固定台账列表，每项为ref＋完整record。objects_sha256绑定当前objects.json；每个对象、台账摘要、记录标识、空间、去重和声明数量均验证。

发布复制完整快照。旧发布不读取“最新台账”，新增台账版本不会改写旧候选或发布。原始设备台账的真实性和对象对应含义仍待现场验证。

## 查询、比较与离线

有business_association的模型对象查询profile升级为cospace.preview-object-query/0.2，每个对象增加business_links，内容为对应ref＋完整固定record；没有链接时为空数组。旧模型仍返回原0.1响应且不额外补业务字段。人视图和智能体查询使用同一固定记录，页面不把它声明为在线实时业务状态。

候选比较及固定发布比较新增business：base_available、target_available、added、removed、modified。新增/解除包含object_id与ledger_ref，换版包含object_id与before/after固定引用。业务差异与对象属性差异分开；人工核对摘要覆盖这些变化。历史已保存的核对报告保持原内容，不能补写为过去已审查业务绑定。

含业务快照的离线包为cospace.preview-offline/0.3，原0.2包成员＋business.json。发布清单、模型清单、业务文件及嵌入台账摘要和对象引用全部检查；离线对象响应与固定发布在线一致。0.1纯几何包、0.2语义包继续兼容；旧消费者若不支持0.3应显式升级，不删除业务文件伪装成0.2。

当前离线包包含所有绑定记录的完整设备字段，不含外部URI或凭据；未来需按消费权限、字段最小化及设备能力拆分交付配置。本阶段仅本机工程预览，不向真实机器人下发。

## 错误与边界

422为严格请求校验失败；403为Origin不允许；503为未配置台账/构建服务；409包括固定版本冲突、台账摘要或空间不匹配、基础候选变化、对象缺失或重复、快照不可用。失败不产生新候选或改动既有发布。登记不自动建立绑定；绑定不自动选择或发布；下载不自动激活。

未接入真实身份和空间ACL，保存的人工说明也不是认证审批。source_system只是外部系统名称标识，非已连接的服务。quality=unverified，robot_ready=false。
