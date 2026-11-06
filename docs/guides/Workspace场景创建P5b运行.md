# Workspace 场景创建 P5b 运行

## 查看本机效果

独立验收服务在 `http://127.0.0.1:8771/workbench/layout.html#data`。选择“登录 → 模拟场景管理员”，在数据管理右上角点击“新建场景”。本地模拟登录不是实际 Vxture 平台认证；8770原运行区和身份进程保持不变。

用户操作：**新建场景 → 配置资料来源 → 导入资料 → 预检 → 构建中心 → 查看模型与双视图 → 核对／发布**。新建场景不会自动导入样本或构建。现有场景继续沿用原流程。

创建结果未确认时，关闭弹窗或刷新均保留本标签页请求；再次打开“新建场景 → 核对并重试”会找回原场景。此时名称暂锁定，避免更换内容误建第二个场景。不要清空浏览器存储来重试一个结果未知的创建。

## 配置边界

正式运行使用稳定平台issuer、独立CoSpace OIDC client、持久会话密钥与策略库。沿用已有平台登录配置；不要复用本地模拟认证数据或将凭证写到浏览器。

在线创建与来源分配配置为 `workspace-scenes.json`，建议保存在实际服务策略目录，由可信部署管理员管理。服务使用 `--workspace-scenes-config` 显式指定。配置结构见 [契约](../../contracts/schemas/workspace-scenes-v0.1.md)。示例配置默认关闭创建，不包含实际租户授权：

```json
{
  "profile": "cospace.workspace-scenes/0.1",
  "revision": 1,
  "workspaces": [{
    "issuer": "https://accounts.vxture.com",
    "org_id": "org_example",
    "workspace_id": "ws_example",
    "allow_create": false,
    "creator_subjects": [],
    "source_bindings": {}
  }]
}
```

向指定 Workspace 分配来源前，核对真实归属、所用资料和人员。来源指纹必须由实际部署目录计算，例如只在本机管理员终端打印ID和指纹：

```powershell
@'
from pathlib import Path
from packages.data.preview_source_config import load_sources
from packages.data.space_sources import SpaceSources
sources,_=load_sources('deploy/config/preview-sources.json',Path.cwd())
catalog=SpaceSources(Path('var/nonexistent-fingerprint-only'),sources)
print(catalog.fingerprints)
'@ | .venv/Scripts/python.exe -X utf8 -
```

该计算不登记来源、不创建指纹计算目录。将经确认的来源ID及指纹写入对应scope的source_bindings，修改配置revision，再使用临时文件完整验证后原子替换。

运行参数在原授权工作台命令上增加：

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.serve_platform_workbench --runtime var/auth/example --sample var/scenes/example --initial var/scenes/example/initial --workspace-scenes-config var/auth/example/workspace-scenes.json --port 8771
```

路径须指向已准备好的独立业务运行区、真实策略库与可读初始成果，不能照抄覆盖已有服务。样本复制与模拟绑定由下述验收脚本自动在新目录执行。默认路径发现有效配置后会留下 `.workspace-scenes-required` 标记；不要删除该标记来绕过配置缺失。来源被撤销后，历史资料仍保留，新登记阻止。

## 重放本批验收

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.verify_workspace_scenes --output var/validation/workspace-scenes-p5b-rerun-001
```

输出目录必须不存在。脚本读取原样本并复制到独立运行区，使用本地模拟 OIDC、实际 HTTP、真实构建子进程、实际RP重启，结束后关闭测试服务。`--port 8771 --stay-open` 可保留模拟服务供浏览器验收，但仅在端口空闲时使用。

验收脚本不会自动发布。来源、身份与初始样本固定在本机工程配置中；换机器需先确认这些路径存在。真实平台联调仍需已登记client、实际Workspace账户及部署来源分配，不能把模拟结果写成生产通过。
