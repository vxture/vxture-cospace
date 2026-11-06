# 合成样例与消费示例

首个完整样例以普通设备间及相连走廊为原型，包含合成真值、一份人视图、一份面向智能体的机器视图及固定服务发布组合。

所有合成内容显式标记synthetic。手工准备的视图须记录准备方式，不声称产品已实现自动派生；样例不作为现场精度、覆盖或重定位证据。

`trace-events/`保存 F06c 候选构建和检查的封闭追溯样例，包含原字节资源、事件、PROV JSON-LD 与校验结果；运行 `python -m experiments.scripts.generate_trace_sample` 可复现。详见[契约](../contracts/schemas/trace-events-v0.1.md)。

完整可读样例保持小体积并提供来源、生成方式、契约版本及预期结果。专用于拒绝路径的损坏输入放在tests相应测试资料目录，避免作为正常消费示例传播。

当前样例位于indoor，仅包含设备间、走廊、柜体的身份与合成锚点、本体和手工视图清单；尚无几何或覆盖产物。

从仓库根目录校验：`python -m apps.cli.check_sample examples/indoor`。

可用`python scripts/build_sample.py <空输出目录>`复建相同文件内容。脚本拒绝覆盖非空目录，样例未登记任何真实采集或现场审核人。

`agent-runtime/`从`indoor-spatial/`选择覆盖、对象和本体，需原来源配合核对，不是自包含机器人交付包。运行`python -m apps.cli.agent_package check examples/agent-runtime --source examples/indoor-spatial`；见[契约](../contracts/schemas/agent-package-v0.1.md)。导出新包分配新package_id，不保证清单逐字节相同。
