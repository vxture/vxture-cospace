# DS 依赖归档

当前使用正式发布的 `@vxture/design-system@15.1.1`、`@vxture/design-ui@12.1.0` 与 `@vxture/design-tokens@4.0.0`。15.1.1 与 12.1.0 从 GitHub Packages 下载，保留 registry 原始归档，不重写组件或包版本。Tokens 4.0.0 沿用已验证的本机完整包归档。

`provenance.json` 记录各归档的版本、来源与 SHA-256；发布前扫描精确暂存树及展开后的归档。认证配置只用于本地下载，不放入 vendor、Git 或镜像。使用 file 依赖和 pnpm overrides，使 CI 与生产构建无需私有 registry 凭据。

DS 15.1.1 已修正导航行高、分组标题尺寸与语义弱化文字色；当前项目已移除临时 patchedDependencies。保留早期归档及其来源记录供追溯，它们不是当前安装版本。
