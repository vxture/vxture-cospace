# 已有点云输入 v0.1

适配器：`ply_pointcloud`；JSON 清单 profile：`cospace.pointcloud-input/0.1`。可执行定义为 `packages/data/preview_pointcloud.py` 中严格 Pydantic 模型（拒绝额外字段、重复 JSON key、缺失单位和坐标声明）。

```json
{
  "profile": "cospace.pointcloud-input/0.1",
  "cloud": {"path":"cloud.ply","sha256":"<64位小写十六进制>","bytes":154780,"points":12884},
  "coordinates": {
    "unit":"m", "frame_id":"os1_16/os_sensor",
    "axes":["sensor_x","sensor_y","sensor_z"],
    "scope":"sensor_local", "scene_alignment":"unverified"
  },
  "provenance": {
    "kind":"derived_single_frame",
    "source_manifest_sha256":"<上游清单摘要>",
    "source_member_sha256":"<上游消息或成果摘要>",
    "description":"首帧中间点云；ROS约定单位，未配准、未作精度验收"
  }
}
```

`scope` 为 `sensor_local | scene_local`；`kind` 为 `derived_single_frame | existing_pointcloud`。来源摘要表示提供者声明的血缘引用，不等于上游全量文件验证。`scene_alignment` 首版只接受 `unverified`。无 EPSG、UTC 或场景配准证据时保持未知。

PLY 必须是 binary_little_endian 1.0，vertex 数与清单一致，属性严格按 float x/y/z，或追加 uchar red/green/blue 顺序排列。允许 comment 行；拒绝其他 element、属性、额外尾部字节、截断、NaN/Inf、绝对坐标超过 1,000,000m。最大 100 万点、32 MiB 文件；头最大 8 KiB，单行最大 1 KiB；清单最大 64,000 字节。

ZIP 必需三个文件：`input.json`（沿用 input-upload/0.1，format 为 ply_pointcloud）、`snapshot/pointcloud.json`、`snapshot/cloud.ply`。P16增加可选的`source_receipt_path: "source.json"`；指定后必须附带第四个成员`snapshot/source.json`，不指定时不得多带该文件。历史三文件包保持兼容。上传不自动构建或发布。

浏览器“准备 PLY”可从受支持的裸PLY生成上述资料包，无需工程命令。用户明确填写米制局部坐标及来源说明，本机校验后再次确认，才调用原上传接口；不增加文件直传协议。详见[用户文件来源声明](pointcloud-source-v0.1.md)。

带来源收据时，`provenance.kind`固定为`existing_pointcloud`，`source_manifest_sha256`等于`source.json`原始字节摘要，`source_member_sha256`等于原PLY摘要；说明、cloud、coordinates须逐字段一致。服务端在登记、事实读取、预检和构建解析时校验收据；固定模型`source.source_receipt`保存已校验内容，随固定发布及离线包保留。这证明声明与所选文件的一致性，不证明来源陈述、单位或场景对齐已被现场核实。

登记保留 point_count、cloud_bytes、cloud_sha256、snapshot_sha256、坐标声明和显示属性；input_frames/used_frames 固定为 1，表示单份输入兼容字段，界面使用点数。固定模型保持输入坐标及 RGB；无 RGB 使用中性灰，不声明真实彩色。
