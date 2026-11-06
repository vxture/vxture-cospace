# P19：RGB-D资料预览与构建来源联动

## 1. 当前入口

服务：`http://127.0.0.1:8783`。本机模拟认证，登录后选择“模拟场景管理员”。

- [原办公室资料](http://127.0.0.1:8783/workbench/layout.html#data?space=space-d7a370b8107c30f7&tab=inputs&input=input-3633f8094bc44604)
- [本次全屏构建](http://127.0.0.1:8783/workbench/layout.html?screen=build&space=space-d7a370b8107c30f7&job=build-6ff86aeaabc849bf&input=input-3633f8094bc44604#build)
- [本次流程](http://127.0.0.1:8783/workbench/layout.html#build?space=space-d7a370b8107c30f7&input=input-3633f8094bc44604&job=build-6ff86aeaabc849bf&tab=flow)
- [固定发布](http://127.0.0.1:8783/workbench/layout.html#delivery?space=space-d7a370b8107c30f7&job=build-6ff86aeaabc849bf&publication=preview-a4ae5a5b87c24d70)

若模拟中央会话暂不可用，使用现有“确认会话并重试”操作。GET会话仅查询，不代替POST确认。本地模拟登录不等于生产认证。

## 2. 查看资料

1. 在办公室资料右侧详情中点击“查看RGB-D”。
2. 拖动资料帧或点击前后帧；彩色、深度及配对时差属于同一明确配对。
3. 第58—60帧仍有原图，显示无已有位姿；资料帧数和构建参与数量分别理解。
4. 按需打开已有估计轨迹，查看局部X/Z投影；这是首相机坐标，不是地面路线。
5. “放大RGB-D预览”打开大画面；关闭返回原资料。查看操作不保存预检或发起构建。

深度采用固定0—10m色标，无效像素透明。原深度码按NYU适配规则解释，不是直接毫米值；两张图保持各自原传感器画幅，没有在此对齐叠加。

## 3. 构建过程核对来源

1. 进入全屏构建，默认仍是纯底图。点击“源画面”。
2. 暂停后将“构建源时间”移到约0.943s，查看第29帧源图及相机位置。
3. 当前帧的源摘要、时间和估计位姿与P18过程记录核对后才显示。拖动时旧图清除，读取失败可在原帧重试。
4. 关闭源画面恢复完整底图。返回构建流程沿用原人工核对及固定发布入口。

60帧资料中57帧有已有估计位姿，本次只处理这57帧；处理完整不代表现场精度或机器人导航通过。只有`build.run`而没有`data.manage`时不开放原图；直接API也执行相应授权。

## 4. 运行区与恢复

业务目录：`var/validation/p19-001/runtime`。当前认证目录：`var/validation/p19-restart-001/auth`。旧服务和历史成果保留。

仅当8783无监听时，从项目根目录使用新的、尚不存在的output目录恢复服务：

```powershell
.venv/Scripts/python.exe -X utf8 -m experiments.scripts.serve_scene_journey_demo --source var/validation/p19-001/runtime --output var/validation/p19-restart-002 --candidate build-c8445a7aa7744502 --port 8783 --existing-runtime
```

这是继续P19独立副本，初始化本机模拟认证；不重建、选择或发布模型。output已存在时选择新的目录名。

机器验收：`output/playwright/flow-batch-p19-acceptance.json`。离线导出：`output/playwright/p19-offline.zip`。离线包不包含源图和逐帧过程分块。

详见[P19验收](../validation/RGB-D资料预览与构建来源联动-P19-2026-11-05.md)及[契约](../../contracts/schemas/rgbd-input-preview-v0.1.md)。
