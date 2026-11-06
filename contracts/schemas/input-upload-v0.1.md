# 场景资料包上传 v0.1

本批接通本机资料上传，复用采集适配器，并于P14补充已有点云适配器。层级为 **Workspace → 场景空间 → 登记资料 → 构建任务 → 模型及双视图**；Workspace来自已验签身份，浏览器必须指定自己有导入权限的场景。上传不生成新场景、不发起构建、不选择候选、不发布。

## 传输与归属

`GET /api/input-uploads?space_id=…` 返回支持格式与预算；P15新增可选`routes`描述（format、category、category_label、label、requires、result），与当前formats一致。前端以formats作为支持范围；旧响应缺少routes时仅对已声明的已知格式使用兼容描述，未知格式不宣称可执行。max_upload_bytes及max_expanded_bytes用于显示预算；来源列表和上传能力独立加载及报错。需要当前场景的资料登记权限。

`POST /api/input-uploads?space_id=…&label=…` 使用 `Content-Type: application/zip`，请求体为ZIP字节；需要已登录身份、同源Origin及CSRF。仅接受这两个查询字段，名称去空白后1—100字。接收前检查权限，接收完毕重新检查会话和空间权限。此后已准入的处理可继续完成，非事务性撤销协议。

包内不包含租户、Workspace、场景ID、服务器路径或操作者。服务端固定场景归属与已验签actor，不能通过清单跨场景登记。

P16在能力响应增加可选`pointcloud_preparation`：profile=`cospace.pointcloud-preparation/0.1`、format=`ply_pointcloud`、source_profile=`cospace.pointcloud-source/0.1`、max_cloud_bytes=33554432、max_points=1000000。浏览器只有在该能力及formats均匹配时开放本机准备；旧服务缺少此字段不开放。准备结果仍通过本节POST上传，不新增端点或持久准备任务。

## 包内格式

根目录 `input.json` 按[JSON Schema](input-upload-v0.1.schema.json)校验：

```json
{"profile":"cospace.input-upload/0.1","format":"nyu_rgbd_with_existing_poses"}
```

| 适配器 | 必需成员 | 校验与阶段含义 |
| --- | --- | --- |
| `nyu_rgbd_with_existing_poses` | `input.json`、`tracking.json`、`snapshot/report.json`、`snapshot/raw/`内由report成员表精确列出的PGM/PPM文件 | RGB-D短序列加匹配的已有轨迹，沿用封存快照、文件摘要与轨迹绑定检查；这是构建输入，并非最终三维模型 |
| `ros1_lidar_single_frame` | `input.json`、`snapshot/sample.json`、`snapshot/sample.bag` | 沿用激光短样本适配器检查；构建取单帧局部点云，传感器坐标不等于已配准空间坐标 |
| `ply_pointcloud` | `input.json`、`snapshot/pointcloud.json`、`snapshot/cloud.ply`；清单指定时还需`snapshot/source.json` | 已有点云成果，显式米制局部坐标，保留输入坐标；详见[PLY契约](pointcloud-input-v0.1.md) |

包内格式由清单声明，服务端再按对应适配器检查内容。不是通用文件自动识别；上传接口不接收裸PLY、LAS、COPC、任意bag和任意ZIP目录。受支持的裸PLY可先在浏览器“准备 PLY”生成受控ZIP。文件名不能代替内容校验。

## 预算及拒绝条件

| 限制 | 当前值 |
| --- | --- |
| 上传ZIP | 128 MiB |
| 展开内容合计 | 192 MiB |
| ZIP成员 | 1104个 |
| 单个JSON清单 | 2 MiB |
| 每场景保留的上传展开内容 | 512 MiB |

只接受STORE/DEFLATE、普通文件和适配器声明的成员；拒绝路径穿越、绝对路径、反斜线、链接、加密ZIP、重复或大小写碰撞的路径、额外文件、重复JSON键和无效清单。流式接收检查上传上限，解包前检查展开预算，再读取并检查真实成员与原始数据摘要。

临时接收与解包目录在请求结束时清理；验证失败不登记资料。完整内容先原子移入 `preview-inputs/uploads/<space_id>/<ZIP SHA-256>/`，再登记资料。若两步之间中断，可能保留未登记内容；同包重试复用该内容，不自动删除。当前场景预算也计入这类保留内容；自动清理、断点续传、多节点对象存储尚未实现。

## 回执与后续引用

首次登记201，重复登记200；响应包含 `created`、`input`、`upload`。`upload`为 `format`、`sha256`（ZIP原始字节摘要）、`bytes`、`expanded_bytes`。`input.registration_ref`包含：

```json
{"method":"uploaded_package","package_sha256":"<64位小写十六进制>","actor":"<已验签主体>","profile":"cospace.input-upload/0.1"}
```

同一场景相同ZIP复用登记资料，保留原名称和原始actor；跨场景形成独立资料记录。去重键使用ZIP字节摘要，同内容重新压缩的ZIP可能生成新记录，不宣称语义内容去重。服务端保存来源摘要并随 `input_binding` 传到固定模型和双视图，浏览器响应不公开服务端存储路径。

上传阶段已检查内容；资料预检仍单独保存检查记录，构建时再次核验依赖。接入成功不表示精度、坐标配准、导航或实机可用性通过验收。

| 状态 | 含义 |
| --- | --- |
| 200/201 | 读取能力、复用资料／新登记 |
| 401/403 | 身份、CSRF、空间或Workspace权限拒绝 |
| 413 | 空包或上传体积超限 |
| 415 | 非ZIP媒体类型 |
| 422 | 元数据、包格式、内容或展开／场景预算无效 |
| 503 | 平台依赖不可用或缺少格式适配器 |

本批验证单宿主存储及真实业务进程重启；不声明多节点并发写入或生产存储验收。
