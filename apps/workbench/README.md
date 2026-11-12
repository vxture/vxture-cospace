## Production application entry (2026-11-09)

当前产品统一术语（2026-11-12）：**视觉表达**用于人观察、理解与核查，**计算表达**用于智能体及程序查询、计算与消费。工作台标题、预览切换、成果目录与交付说明统一使用这两个名称。接口与固定成果中的 `human_view` / `agent_view` 字段保持原契约。

The product is one React application, built from `index.html` and routed by React Router's browser router. Public entry is `/`; modules use `/space`, `/data`, `/build`, `/delivery`, `/ontology`, `/association` and administrative routes. Record context is in query parameters. The server serves the application shell only for this explicit route set, so direct refresh and new tabs work without a broad catch-all. `/workbench/*.html` and `/index.html` return 404 with no redirect. Generated resources are served under `/assets/`. Authentication returns directly to an application route; platform logout returns to `/`.

The notes below describe historical previews, not the current public routing contract.

# 工程工作台

2026-11-02 E1：空间关联新增稳定ID下的对象修订；构建中心“核对并选择”展示几何/表面、本体、坐标和对象差异。填写说明并确认限制后选择，序号变化须重新核对。态势服务新发布保存核对说明，旧发布不补造。见[操作手册](../../docs/guides/候选更新核对运行.md)。

2026-11-02 D2：态势服务的固定发布可展开“本地消费”，从实际offline.json生成该空间/发布/摘要的安装、主动激活与重启恢复命令。页面不读取消费端状态，失败或绑定错误不生成命令。消费库及CLI见[操作手册](../../docs/guides/预览消费版本保存与恢复.md)。

2026-11-02 导航调整：Launcher为使用（空间预览、态势服务）、构建（数据管理、构建中心）、定义（语义本体、空间关联）。对象标注独立移至空间关联，构建中心保留候选确认和关联入口；空间上下文跨模块传递。空间预览新增可展开的六模块进度。真实身份与空间授权尚未接入。见[功能架构](../../docs/architecture/产品功能架构与模块进度-2026-11-02.md)及[验证](../../docs/validation/六模块导航与职责调整-2026-11-02.md)。

2026-11-02 D1：“服务与交付”的固定发布可展开范围查询，填写最小/最大坐标及最多4096个返回单元。结果区分完整枚举、超限不返回部分数据和无证据未知，修改输入或切换空间清空旧结果；见[验证](../../docs/validation/智能体范围查询-D1-2026-11-02.md)。

2026-11-02：`layout.html`已接入真实项目/空间、资料与预检、构建、对象标注及固定预览发布。工程空间和交付列表会新标签页打开真实DS全屏界面，支持完整PLY人视图、智能体表面视图、对象联动及空间/历史发布切换，见[C验证](../../docs/validation/真实双视图DS全屏接入-C-2026-11-02.md)。这些写入仅用于本机预览；认证尚未接入。下文原合成入口与各历史批次的能力边界分别保留。

新增报告目录列表及固定批次＋摘要选择，配置COSPACE_DELIVERY_ARCHIVE，不替代单文件配置。列表刷新清空选择，读取失败不回退，Web不生成或写入，见[手册](../../docs/guides/交付报告归档运行.md)。

React19、TypeScript7、Vite8和TanStack Query的只读样例工作台。提供当前发布读取、指定版本追溯、三维合成人视图、点查询、资料清单、本体规则及对象核对，并增加任务列表、详情、固定输入、检查报告和诊断。无工程写入能力。

2026-10-27新增智能体交付核对区，展示服务端固定配置的保存报告、完整绑定及行动。刷新只重新读取报告，不扫描底层状态；场景/发布切换取消旧请求。配置COSPACE_DELIVERY_REPORT，见[运行说明](../../docs/guides/交付核对工作台运行.md)和[验证记录](../../docs/validation/交付核对工作台验证-2026-10-27.md)。

```sh
pnpm --dir apps/workbench install --frozen-lockfile --ignore-scripts
pnpm --dir apps/workbench run build
```

构建后由托管API同源挂载至/workbench/，启动见[运行手册](../../docs/guides/本地工作台与迁移运行.md)。开发模式可运行pnpm --dir apps/workbench dev，默认代理到本机8000端口。use client打包警告仍需跟踪。

`/workbench/layout.html` 为 React + Vxture DS 15.0.0 工作面，使用 DS 的背景、字体、Header、按钮、表单、表格和浮层，全屏空间不使用通用Header。依赖使用本机 yucer 已安装包的完整归档，详情见 [DS 接入记录](../../docs/architecture/工作台DS接入记录-v0.3.md)。由于上游包存在空声明文件，当前 `skipLibCheck=true`，应用源码保留 strict 检查。已连接本机真实样本流程，尚未连接第三方认证或生产业务服务。

读取失败清除旧空间结果，不将错误转换为空间unknown。修改场景或发布后清除已选快照；每次查询仍由服务器检查撤回。页面显示的有效性是最近读取状态，不是实时安全保证。

Three.js0.186.1按需加载，WebGPURenderer优先WebGPU，兼容路径使用其WebGL2后端。当前浏览器已实际验证WebGPU；回退和设备丢失仍待专门验证。对象仅显示已有锚点，空间分区使用服务端规则处理未知和冲突；没有推断墙面或设备形状。空间查询返回的点可在同一版本视图中标记。

人视图是固定合成快照，加载时检查撤回，已下载内容不支持远程收回；再次加载失败清除三维内容和旧点结果。服务端每次查询仍检查撤回。详见[人视图验证](../../docs/validation/三维人视图验证-2026-10-26.md)。

“加载 / 刷新资料与本体”同时核对两类内容与所选场景、发布、真值、坐标和摘要；任一失败不展示半套结果。修改发布清空核对区，撤回后加载失败清除资料、本体、三维和旧点结果。资料展示登记时校验状态，校验时间未记录，不访问可变源文件；规则结论使用固定本体重新计算。详见[验证记录](../../docs/validation/数据与本体核对验证-2026-10-26.md)。

构建与校核按顶部scene查询，不依赖选择release。刷新列表后查看任务，核对输入或读取成功报告；场景/任务切换清除旧结果，404/409/503显式显示。时间统一北京时间；状态仅为最近读取信息。运行时需设置COSPACE_DATA_ROOT，未设置会返回503。见[任务工作台验证](../../docs/validation/任务工作台验证-2026-10-26.md)。
