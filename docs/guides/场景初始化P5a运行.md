# 场景初始化 P5a 运行

面向可信本机管理员。产品用户在已授权场景中使用数据管理；本批没有新增自助创建场景按钮，不以某个场景的manager权限替代Workspace创建授权。

P5b后续已提供按平台owner基线或产品显式授权创建空场景的在线入口，见[运行说明](Workspace场景创建P5b运行.md)。P5a继续负责样本包初始化与旧样本显式接管。

## 查看预置样本

8770数据管理已加入独立的 **OS1-16 · multi/1** 场景：

`http://127.0.0.1:8770/workbench/layout.html#data?space=space-0004d0e3c133f5fb&tab=inputs`

使用本地模拟管理员登录后可切换 NYU 与 OS1。NYU复用原 `space-ea727be75c1049db` 和 `input-596c9a6e1dfc4847`；OS1为 `space-0004d0e3c133f5fb`，资料 `input-92d53629d51643d2`。OS1没有构建或发布，可点资料“详情 → 用于构建”，后续按原流程提交。

查看者仅看到已有明确授权空间，不因预置样本而获得新场景权限。原来的空负例场景保留，不需要删除来凑数量。

## 受控初始化

配置文件 `configs/samples/scene-presets.json` 将物理场景键映射到来源ID；源路径仍在部署配置中。请求文件示例：

```json
{
  "scope": {
    "issuer": "https://accounts.vxture.com",
    "org_id": "org_example",
    "workspace_id": "ws_example"
  },
  "preset_id": "nyu-office-0001a",
  "manager_subjects": ["usr_example"],
  "actor": "deployment-administrator",
  "reason": "经核对向该Workspace预置办公室场景"
}
```

字段是示例，执行前必须替换为已核对的真实归属和用户ID。第一次创建使用独立业务runtime与策略目录；已有运行区必须指向该服务实际使用的路径，不创建另一套漂移授权。不得指向原始 `var/nyu` 工程目录，业务runtime与策略目录需互不包含。

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.initialize_scene --runtime var/scenes/example --policy-root var/auth/example/policies --request var/private/scene-request.json plan
```

审阅输出中的scope、space_id、source检查、policy_revision与plan_sha256后应用：

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.initialize_scene --runtime var/scenes/example --policy-root var/auth/example/policies --request var/private/scene-request.json apply --expected-revision N --plan-sha256 SHA256_FROM_PLAN
```

`N`和摘要替换为刚审阅的值。返回完整回执才是初始化成功。重复应用旧计划可能因策略修订变化而拒绝；重新plan后重放完成记录会返回 `created=false`，不会恢复已撤销的授权。

已有相同物理场景时，在请求增加 `existing_space_id`，显式复用已绑定场景与已有资料。默认模式发现同Workspace已经登记该样本时会拒绝重复建空间。接管要求已存在相同scope绑定和所列manager授权，不改原目录显示信息、旧资料或历史发布。物理场景一致性须管理员确认，工具不能自动识别任意现场。

失败／进程中断后，保留状态记录及暂存文件；使用原请求重新plan，再显式apply。不要删除已有资料、整目录或策略库来重试，不修改scene_key规避幂等。文件变化、来源停用或撤权均先处理对应管理变更，初始化不自动“修复”。

## 重放验收

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.verify_scene_initialization --output var/validation/scene-initialization-p5a-rerun-001
```

输出目录必须不存在。验证两场景同Workspace、另一个Workspace独立、不同CLI进程重复复用、实际进程退出23后的恢复、撤权不补回、真实授权HTTP直链、预检及RP重启。使用本地模拟身份，服务自动关闭。报告不含客户端密钥。

本地模拟IdP的issuer随模拟进程改变；本次8770策略位于 `var/validation/scene-construction-demo-auth-p4-001/policies`。不要用生成全新模拟认证目录的旧启动方式冒充保持了相同初始化身份。生产使用稳定issuer与持久策略库；真实平台场景创建接口接入仍属P5b。
