# DS 依赖归档

当前使用正式发布的 `@vxture/design-system@15.6.1`、`@vxture/design-ui@12.5.1` 与 `@vxture/design-tokens@4.1.0`（2026-11-15 查询 registry 的 latest）。三个包均从 GitHub Packages 下载，保留 registry 原始归档，不重写组件或包版本。

`provenance.json` 记录各归档的版本、来源与 SHA-256；发布前扫描精确暂存树及展开后的归档。认证配置只用于本地下载，不放入 vendor、Git 或镜像。使用 file 依赖和 pnpm overrides，使 CI 与生产构建无需私有 registry 凭据。

空间服务使用 DS `ViewModeSwitch` 提供卡片 / 列表切换，保留组件的单选语义、键盘交互与视觉样式，业务侧仅传入选项与状态。项目无临时 patchedDependencies。保留早期归档及其来源记录供追溯，它们不是当前安装版本。
