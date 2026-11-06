# 本机 DS 包归档

私有 registry 当前返回 401；本目录归档 yucer 已安装的完整 DS 包，保留原始代码与 package.json，不复制或重写组件。项目以 `file:vendor/*.tgz` 安装，传递依赖通过 pnpm overrides 指向相同归档，因此构建无需访问 yucer 项目路径。

`provenance.json` 记录版本、来源与归档 SHA-256。归档工具为 `experiments/scripts/archive_local_ds.py`。不要在 vendor 中放认证凭据。

具备私有 registry 认证后，可将依赖切换为已发布的相同版本并移除本地 overrides；认证通过环境或用户配置提供，真实 token 不入仓。

DS 15.0.0、UI 12.0.0、Tokens 4.0.0 是本机 yucer 已安装版本，未宣称为 registry 最新版。
