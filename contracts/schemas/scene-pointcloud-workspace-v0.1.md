# 场景点云工作区 v0.1

## 范围

场景的完整编码点记录保持 A 批分块格式。此接口提供显示派生、来源选择与区域成果登记，复用现有 PLY 预检和构建；不实现自动配准、SLAM、IFC 对齐或商业额度管理。

## 服务端配置

[场景绑定 Schema](scene-pointcloud-bindings-v0.1.schema.json)定义一个场景空间到完整场景、显示索引及其预期 SHA256 的绑定。路径仅由受控配置提供，HTTP 不接受路径。生产空配置为 `setup/scene-pointclouds.json`，工程服务可传 `--scene-pointcloud-config`。未配置返回 `configured:false`，不读取其他场景数据。

所有接口均要求当前平台授权和该场景的 `data.manage`，响应 `Cache-Control:no-store`。写请求执行现有同源和 CSRF 检查；查询参数缺失、多余或重复均拒绝。当前 Workspace 权限不从资料目录或图层名称推断。

## 读取

- `GET|HEAD /api/scene-pointclouds?space_id=…`：返回 `cospace.scene-pointcloud-workspace/0.1`，包含固定场景/索引摘要、共同局部原点、单位依据、未配准标识、来源与显示分块目录；不公开服务器路径。
- `GET|HEAD /api/scene-pointclouds/tiles/t00000/0?space_id=…&index_sha256=…`：仅允许索引内的 tile 和 0/1/2 级，先校验绑定与索引，再校验二进制长度和摘要。浏览器也校验长度、SHA256 和有限坐标。

离线生成器为 `experiments.scripts.prepare_scene_tiles`。每个原空间格内按来源独立生成三个显示层级，步长为 0.25 / 1 / 4 个声明坐标单位，每格取原来源序号最小的实际点。二进制先存所有 little-endian float32 XYZ，再存全部 uint8 RGB，每点合计 15 字节；单块单级最多 50,000 点。RGB 由原 uint16 除以 256 取整得到，显示时转换为线性颜色。索引仅在成功后出现，失败保留 failed.json，重跑须新目录。

画布按视锥、所选来源和 XYZ 范围请求相交块，180ms 合并相机变更，旧请求取消且迟到响应不落图。视口最多 96 块、150,000 点；优先整体降低显示层级，仍超限则提示缩小范围，不丢弃覆盖块。LRU 缓存最多 96 项、300,000 点；更换场景、Workspace、索引或重新确认会话时清理。显示误差和抽样不改变成果派生参数。

## 区域成果

`POST /api/scene-pointclouds/compositions` 使用[区域请求 Schema](scene-pointcloud-compose-v0.1.schema.json)，返回 202 和任务。来源顺序明确表示体素派生优先级；XYZ 区域为半开 `[min,max)`，不推断配准或单位。`voxel_size:0` 保留范围内全部原始点；非零值显式派生，不平均坐标。同一请求 ID 同一参数复用任务；同 ID 不同参数拒绝。当前服务同时执行一个派生任务，忙时明确返回 409，不接受未保存的排队任务。

后台从原始分块读取，超过 250,000 成果点整体失败，不截断。完成后冻结 ZIP 摘要及原始匹配量/保留量，重新检查会话、订阅准入、当前场景权限和索引，使用已有上传登记器提交资料；组合依据随输入进入模型与双视图。

`GET|HEAD /api/scene-pointclouds/compositions/compose-…?space_id=…` 返回持久状态：`queued/running/succeeded/failed/interrupted/awaiting_authorization`。成功有 `input_id`；失败不伪装成功。服务重启后原进行中任务标为 interrupted，不自动重复执行。

若派生已完成但平台确认窗口过期或平台暂不可用，保存为 `awaiting_authorization`，不绕过平台、不把轮询当用户活动。原操作者确认会话后，以 `POST /api/scene-pointclouds/compositions/compose-…/register` 和仅含 `space_id` 的 JSON 完成登记：重检当前权限、索引和 ZIP 摘要，复用成果，不再扫描源点。该 POST 支持重复调用，其他操作者不能代为登记；撤权、来源修订或成果变化仍拒绝。

## 备份与边界

冷备份接受此可选配置，但绑定资产须实际位于同一业务根的 `runtime/preview-inputs` 内，恢复仍采用原机器原路径。外部资产绑定会明确阻断冷备份，须先纳入业务根。进行中区域任务阻断冷备份；待确认登记的冻结成果可备份恢复。配置不包含平台凭据。

全量 NPZ 不发送浏览器，不作为一个全分辨率固定模型加载。浮点显示/PLY 为派生成果，原完整编码记录仍保留。未配置 GPU 时保留来源与数值范围操作，框选和三维浏览不可用。生产发布仍须 PR、五项检查、release 与 Environment 审核。
