# 用户文件来源声明 v0.1

P16可选来源收据，profile=`cospace.pointcloud-source/0.1`。可执行模型为`packages/data/preview_pointcloud.py`的`SourceReceipt`，结构见[JSON Schema](pointcloud-source-v0.1.schema.json)；跨字段与摘要约束由同文件`source_receipt`执行。

## 内容及含义

```json
{
  "profile":"cospace.pointcloud-source/0.1",
  "basis":"user_declared_file",
  "original_name":"first-frame.ply",
  "cloud":{"path":"cloud.ply","sha256":"<原文件64位摘要>","bytes":154780,"points":12884},
  "coordinates":{
    "unit":"m","frame_id":"os1_16/os_sensor",
    "axes":["sensor_x","sensor_y","sensor_z"],
    "scope":"sensor_local","scene_alignment":"unverified"
  },
  "description":"提供者填写文件来源、数据范围和已知处理情况"
}
```

`basis`只接受`user_declared_file`。原文件名为1—160字，不含路径、冒号或控制字符；description为1—500字且非空白。cloud及coordinates与点云清单完全一致；坐标仍受PLY契约限制。单文件最大64,000字节，拒绝重复JSON键、额外字段与不合法声明。

浏览器计算原文件摘要并完整保留字节为`cloud.ply`，收据不包含Workspace、场景ID、操作者、本机绝对路径或伪造的采集时间。服务端身份、归属和登记时间继续由原登记流程产生。收据内容是提供者的说明，不能等同上游采集日志、测量证明或配准结论。

## 绑定与重复提交

`pointcloud.json.source_receipt_path`指定`source.json`；其provenance记录收据字节摘要、原文件摘要及相同description。缺失、额外、篡改、不一致或借用其他格式的收据均拒绝。登记后改动收据会导致事实、预检、构建解析及重复上传核验失败。

浏览器ZIP采用固定顺序、STORE、固定DOS时间。原文件（含文件名）和坐标／来源声明相同时生成同一ZIP；同场景重复提交复用原记录，不覆盖原名称或actor。资料名称不参与ZIP内容。修改声明产生新的资料包及登记，保留原点云字节与历史成果；这不代表现场发生变化。该确定性仅约束浏览器准备算法，不改变通用上传按ZIP字节摘要去重的规则。

本机通过后显示“尚未登记”，需要第二次确认才上传。服务端独立复核，固定模型、双视图、发布和离线消费沿现有流程继续。三类事实始终分开：摘要及格式已检查、来源由用户声明、场景对齐和精度未验收。
