# 场景初始化 v0.1

范围：可信本机管理员 CLI，不是 HTTP 接口。平台登录只证明身份与当前 Workspace，不自动授予创建未绑定场景的权限。既有 `/api/spaces` 的 POST 及未实现的 `/api/scene-initializations` 仍拒绝访问，包括平台 `workspace:owner`；没有从 URL、用户名称或场景管理员角色推断创建授权。

后续更新（P5b）：已核对平台080 §2.6的workspace owner产品基线，新增独立、显式启用的产品在线创建API，见[Workspace场景创建](workspace-scenes-v0.1.md)。本页仍定义P5a可信CLI及原路径；不把旧路径直接开放。P5a工具的来源分配仍由可信管理员核对，P5b在线路径已实施Workspace来源指纹分配。

## 输入与样本定义

`cospace.scene-initialization-request/0.1`：

| 字段 | 定义 |
| --- | --- |
| scope | 明确 `issuer`、`org_id`、`workspace_id`；由可信管理员依据平台登记核对，不是浏览器声明 |
| preset_id | `configs/samples/scene-presets.json` 中的样本包ID |
| manager_subjects | 显式初始产品管理员 `usr_...` 列表，不能把操作者显示名当用户ID |
| existing_space_id | 可选，显式接管相同物理场景；需已有同一scope绑定与所列manager授权 |
| actor / reason | 本地受控操作审计；actor不是OIDC验签证明 |

未知字段、重复成员和空白审计说明拒绝。没有浏览器可填写的源文件路径。服务端样本包将一个稳定 `scene_key` 关联到名称、说明与来源ID；一个场景包可以含多个同场景来源。首批只有 NYU office_0001a 和 OS1 multi/1 两个不同场景。

幂等身份：`init-` 加 `SHA256(scope + scene_key)` 前32位。新 `space_id` 沿用既有格式，取同摘要前16位；碰撞时拒绝，不覆盖。新的工程父项目按scope生成，只作本地目录父记录，不等同平台Workspace。已经初始化的同scope场景共用该项目；旧场景显式接管则保留原项目、空间、资料与历史成果。

## plan / apply

`plan` 只读，校验真实来源内容、目录冲突、现有绑定／授权、来源许可与重复样本。返回 `cospace.scene-initialization-plan/0.1`、scope、space_id、project_id、state、policy_revision、spec_sha256、plan_sha256、资料校验摘要和预期目录快照。计划包含本机路径，只交可信本机管理流程，不暴露给普通用户。

`apply` 需要计划的policy_revision及plan_sha256。加本机跨进程锁后重新生成计划；策略修订或计划变化都拒绝。完成记录重放返回相同回执，`created=false`；不新增场景、资料、授权或审计修订。

保存过程：`prepared → directory_ready → inputs_ready → complete`。状态保存在策略SQLite的 `scene_initializations` 表；原始请求、定义摘要、状态事件、错误与资料引用可追溯。目录最终文件不替换，计划自有 `.pending` 暂存文件可在恢复时重写。资料登记复用现有不可变记录和去重逻辑。只有最后事务才提交新scope绑定及manager授权，并与complete回执同一SQLite事务提交。

中断不执行级联删除：保留带初始化ID的记录，部分新场景在绑定前没有HTTP访问权限。重新plan、apply显式恢复，已成功的资料登记复用。接管旧场景在失败时仍可能已经有自身合法访问权限，不能声称旧场景因此隐藏；旧授权、模型与发布不改动。

策略被撤销、资料／目录丢失、来源许可被停用或配置改指向时，完成记录重放拒绝，不“修复”成原权限。需走明确的管理变更。初始源内容变化也不当作同一初始化自动升级，后续资料版本走普通数据管理。

## 输出与限制

`cospace.scene-initialization-receipt/0.1`：id、scope、space_id、project_id、preset_id、scene_key、inputs（id/source_id/record_sha256）、policy_revision、initialized_at、adopted。authority固定 `trusted_local_administrator`；`created` 表示本次是否完成初始化。

不自动构建、选择、发布、安装或激活机器人消费包。保持 `quality=unverified`、`production_ready=false`、`robot_ready=false`。来源检查只是可解析与摘要一致，不是独立测量精度验证。

同一Workspace发现另一已绑定空间登记了同路径且同内容样本时，要求显式接管，避免重复造空间。接管已登记另一已知样本场景时拒绝。物理场景判断依赖审核的scene_key和管理员确认，不能根据点云摘要自动识别任意现场是否同一物理场景。

多Workspace初始化的身份与资料记录独立；当前来源目录本身仍是受控部署配置，没有逐来源的租户分配ACL。因此本工具须由可信管理员确认scope可使用哪些来源，不能由此开放多租户自助选源。在线创建和来源分配需P5b的平台授权契约。
