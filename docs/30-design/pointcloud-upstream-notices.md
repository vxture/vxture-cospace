# 渐进点云运行时来源与许可

## 固定来源

所有第三方文件在 CI / Docker 构建时由 `scripts/prepare_pointcloud_tools.py` 下载并校验 SHA-256。生成文件不进入 Git，不从 CDN 在用户浏览期间加载。更新版本必须同时更新来源、摘要、兼容验证和本记录。

| 组件 | 固定来源 | 许可 / 分发位置 |
| --- | --- | --- |
| Potree 1.8.2 | [官方发布](https://github.com/potree/potree/releases/tag/1.8.2) | BSD-2-Clause；`/assets/potree-1.8.2/build/potree/LICENSE` |
| PotreeConverter 2.1.5 | [官方源码](https://github.com/potree/PotreeConverter/tree/2.1.5) | BSD-2-Clause；镜像 `/opt/potree/licenses/license_potree_converter.txt` |
| Three.js（该 Potree 发布内置版本） | 同一 Potree 发布包，独立 iframe 内运行 | MIT；`/assets/potree-1.8.2/libs/three.js/LICENSE` |
| tween.js | 同一 Potree 发布包 | MIT；`/assets/potree-1.8.2/libs/tween/LICENSE.txt` |
| proj4js | 同一 Potree 发布包 | MIT；`/assets/potree-1.8.2/libs/proj4/LICENSE.md` |
| BinaryHeap | 同一 Potree 发布包 | 源文件声明允许按 MIT 使用；保留文件头版权和许可说明 |
| jQuery 3.7.1 | [官方文件](https://code.jquery.com/jquery-3.7.1.min.js) | MIT；保留压缩文件头声明，替换发布包内旧版本 |
| LASzip、Brotli、nlohmann/json | 固定转换器源码内依赖 | 分别保留其 LGPL、MIT、MIT 许可，镜像 `/opt/potree/licenses/`；LASzip 动态链接 |
| laspy 2.6.1 | Python 锁文件 | BSD-2-Clause；原安装包包含许可 |

下载文件的准确摘要以准备脚本中的常量为准；不以运行时控制台版本文案识别来源。官方 1.8.2 发布包的部分控制台文案仍为 1.8.0。

## CoSpace 适配范围

前端不修改 Potree 引擎源码，独立 iframe 隔离其 WebGL / Three.js 运行时。CoSpace 提供消息桥、鉴权范围读取、局部失败暂停与重试、对象锚点和诊断指标。使用官方导出的 OctreeLoader，避开该发布便利包装函数对 metadata.json 的重复加载。

Linux 编译兼容补丁在准备脚本中逐项校验原文后应用：JSON 到 string 显式取值，Windows 调试中断替换为 GCC trap。补丁不改变层级生成、坐标量化、采样或编码；容器校验使用实际原生输出解码往返，而非只检查命令退出码。Windows 验证使用官方二进制。

首版只加载 UNCOMPRESSED 原生八叉树和其 Worker。Potree 的可选第三方菜单、旧 jQuery UI、拖入外部数据等入口不启用。原生包内资源的再分发仍保留上游许可，不能因某项功能未启用而删除相应声明。
