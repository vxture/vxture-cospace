# 工作台 DS 接入记录 v0.3

本记录取代 v0.2 中“尚未导入 DS”的实现状态。页面地址仍为 `/workbench/layout.html`，现由 Vite 多入口构建 React 页面，原 `/workbench/` 功能演示保留。

## 实际依赖

- `@vxture/design-system` 15.0.0
- `@vxture/design-ui` 12.0.0
- `@vxture/design-tokens` 4.0.0
- Tailwind CSS / 官方 Vite 插件 4.3.3

版本来自 yucer 本机安装。私有 registry 未配置认证，返回 401；使用完整本机包归档安装，来源和摘要见 `apps/workbench/vendor/provenance.json`。没有重写 DS 组件或复制其 token 值。

## 组件与样式归属

| 元素 | 实际 DS 组件或入口 |
| --- | --- |
| 全局基础 | fonts、globals、brands/vxture、workbench CSS |
| 登录 Header | ShellHeader：xl / centered / transparent |
| 工作台 Header | ShellHeader：md |
| 产品标识 | ShellHeaderMark、ShellHeaderTitle、ShellHeaderDivider、ShellProductTitle |
| Launcher 与管理 | Popover、ShellPanelContent、ShellPanelSection、ShellPanelRow、ShellIconButton |
| 账户 | ShellUserMenu |
| 页面容器 | ShellPageContainer |
| 表单 | Field、FieldGroup、FieldLabel、Input、NativeSelect |
| 控件 | Button、Icon、Switch、Tabs、StatusBadge |
| 列表与浮层 | Table、Card、Dialog 系列 |
| 主题 | ThemeProvider、ShellThemeToggle |

本地 CSS 只表达 SVG 空间图的业务绘制与布局，不定义品牌值或覆盖 DS 控件。空间图使用 DS 语义色；基础控件不再手写。删除旧版 public/layout.html 与 layout-shell.css/js，避免自定义基础样式覆盖 DS。

## 实测

浏览器 1440×1000：登录页 Header 64px，工作台 Header 48px，空间区域 1440×952；登录主按钮使用 XL 档，32px。背景计算值与 DS `--background` 相等（本次浅色为 #f4f7fd）。确认主题切换、业务表格、配置草稿、成员弹窗、沉浸与 Esc、919px 和 390px 登录布局，共 14 项检查通过，未发现 JavaScript 错误。

`pnpm install --frozen-lockfile --offline` 和 TypeScript + Vite 构建通过。DS 包内部分 `.d.ts` 文件为空，导致第三方声明检查 TS2306；本项目改用 `skipLibCheck: true`，业务源码的 `strict` 检查保留。未修改归档依赖声明。该上游问题应在 DS 修复后恢复检查。现有 use-client 打包提示仍存在，不影响本次客户端运行。

## 功能边界

登录仍为第三方接入设计，不创建认证会话；API 未因 UI 接入 DS 自动获得认证保护。空间为 SVG 示意，尚未接真实三维数据。业务配置为本机草稿，成员为临时草稿；不含计量与计费。
