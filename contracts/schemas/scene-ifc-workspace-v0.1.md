# 场景 IFC 构件资料 v0.1

## 产品范围

IFC 是一个场景空间下的可选配套资料。通用入口为“空间关联 → IFC 构件资料”，提供构件目录、名称/类型/GlobalId 搜索、几何状态及独立坐标系下的预览。采用既有场景权限，不增加套餐或商业额度控制。

当前交付限于资料接入与查看。自动配准、现场工程建模、控制点编辑、变换求解、批量业务对象创建和原生 IFC 在线上传均不在本批范围。坐标关系为待确认；IFC 构件不会自动成为已发布对象或改变原点云模型。

## 可复现的离线解析

原生解析器隔离在 `experiments/ifc-tool`，使用独立锁文件；生产 Python 环境和镜像不安装 IfcOpenShell。输入为 IFC4 家族文件，提供外部预期 SHA256，输出目录须不存在：

```powershell
uv run --project experiments/ifc-tool --frozen python -m experiments.scripts.inspect_ifc_scene --ifc 'PATH/scene.ifc' --sha256 EXPECTED_SHA256 --output 'PATH/new-catalog'
```

输出保留 `source.ifc` 原字节、`ifc.json` 目录及 `e00000.npz` 等构件网格。原始单位由项目长度单位读取，几何统一为米并应用 IFC 内部放置链；不将 site 经纬度解释为点云坐标转换。GlobalId、IFC 类型、名称、所属容器、放置矩阵、包围范围和网格摘要保留。没有几何表示和提取失败分别计数，失败不冒充空构件。

预算：输入最多 128 MiB，10,000 产品实体，总顶点 2,000,000、总三角形 4,000,000，网格压缩总量 192 MiB。超过预算失败，目录完成标识不发布，部分文件保留为失败证据。工具只适用于可信的运维预处理，浏览器不能提交文件路径或触发原生解析。

## 场景配置和服务

在私有 `setup/scene-ifc.json` 中配置[场景绑定 Schema](scene-ifc-bindings-v0.1.schema.json)。每项绑定实际场景 ID、目录绝对路径和外部保留的 `ifc.json` SHA256；重复场景拒绝。生产默认绑定为空；已有部署未配置时保持可启动。

本机受权服务支持 `--scene-ifc-config`。生产资产放在业务根的 `runtime/preview-inputs` 中，参与冷备份；外部路径在备份时明确拒绝。当前离线配置的 IFC 资产尚未登记为产品输入，不纳入现有按登记输入核算的存储用量；后续通用资料上传接入时统一处理。备份/恢复核验目录、原 IFC 及全部已提取网格，保持原路径恢复。

| 请求 | 行为 |
| --- | --- |
| `GET /api/scene-ifc?space_id=…` | 授权场景的构件目录；未配置返回 `configured=false` |
| `GET /api/scene-ifc/element?space_id=…&element_id=e00001&catalog_sha256=…` | 一份固定目录中的构件顶点预览 |

两者均要求平台会话和场景 `association.edit` 权限；跨 Workspace 或场景拒绝。响应 `Cache-Control: no-store`。不暴露服务端路径或网格文件地址。目录及原 IFC 每次核验；构件加载还校验 SHA256、字节数、内部数组预算、索引和包围范围。变化或损坏返回 409，错误信息不含本机路径。

预览最多 10,000 个顶点，按文件索引步长显示；这是显示预算，不改变保存的构件三角网格。目录及预览固定 `alignment_verified=false`、`quality=unverified`、`robot_ready=false`。

## 验收

业务测试使用独立合成网格与多场景权限，原生解析回归另用程序生成的 IFC 毫米制模型，验证单位换算、旋转/平移和解析文件的生命周期，避免依赖特定工程样本。Anoeta 仅作为额外兼容性样本，不进入源码或生产默认配置。
