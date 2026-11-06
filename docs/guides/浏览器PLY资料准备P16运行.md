# P16 操作指引

入口：[数据管理 · OS1场景](http://127.0.0.1:8780/workbench/layout.html#data?space=space-0004d0e3c133f5fb&tab=inputs&input=input-9129e7b23b4d4ea6)。使用本机“模拟场景管理员”，真实账户联调未完成。

## 原文件到成果

1. 选择对应物理场景的场景空间，点击“导入资料 → 准备 PLY”。多资料及历史版本放在同一场景空间。
2. 选择受支持的PLY。样例：`D:\MyWebSite\vxturestudio\vxture-cospace\var\samples\multi-1-os1-lidar-1s-001\first-frame.ply`。
3. 填写资料名称、局部坐标系、坐标范围、三条不同的轴语义及来源说明。该样本frame为`os1_16/os_sensor`、范围为传感器局部、轴为`sensor_x / sensor_y / sensor_z`；说明其为未配准OS1首帧中间点云。其他文件须按其真实信息填写。
4. 核实原文件数值单位为米后确认，点击“检查并准备”。系统不转换坐标或单位。
5. 核对点数、颜色、坐标及来源，可展开摘要并保存ZIP；此时尚未登记。
6. 确认坐标与来源声明，点击“确认并登记”，服务端重新校验。相同文件及声明重复提交复用原记录，不覆盖原名称。
7. 在资料详情执行预检，整理封存批次，再进入构建中心。已有批次关系时须明确选择封存批次。构建成功后核对选择，到态势服务确认预览发布。

修改文件、坐标、轴、范围、单位确认或来源会使结果失效，需重新检查；只改资料名称不改包。上传失败可重试同一包；切换场景后重新选择文件。旧服务未声明准备能力时不可执行，仍可使用已配置来源或已有ZIP。

## 预置验收结果

- 资料`input-9129e7b23b4d4ea6`：12,884点，无RGB；“用户文件声明（未独立核验）”。
- 构建`build-fc412d231e854332`；封存批次`batch-5655cf9c9e664fbe`修订2。
- [固定发布与下载](http://127.0.0.1:8780/workbench/layout.html#delivery?space=space-0004d0e3c133f5fb&job=build-fc412d231e854332&publication=preview-770fb858bd554092)，固定预览在新标签页打开。
- 离线包SHA-256：`6747ecbcf7390e52c101d35effc64d782308dcaa0994fc2cf75439af6f054411`。

准备通过表示文件与声明满足格式要求；模型仍为未验收候选，不代表配准、精度或机器人可用。

## 运行

数据`var/validation/p16-001/runtime`；当前模拟认证`var/validation/p16-restart-001/auth`；端口8780。P15/8779保留。8780进程退出后，选择尚不存在的output目录启动，不要重复占用监听端口：

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.serve_scene_journey_demo --source var/validation/p16-001/runtime --output var/validation/p16-restart-002 --candidate build-c8445a7aa7744502 --port 8780 --existing-runtime
```

重启后需重新登录，业务数据沿用原独立运行区。见[P16验收](../validation/浏览器PLY资料准备-P16-2026-11-05.md)、[来源契约](../../contracts/schemas/pointcloud-source-v0.1.md)和[PLY契约](../../contracts/schemas/pointcloud-input-v0.1.md)。
