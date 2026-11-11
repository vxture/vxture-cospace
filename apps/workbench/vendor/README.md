# 本机 DS 包归档

私有 registry 当前返回 401；本目录归档 yucer 已安装的完整 DS 包，保留原始代码与 package.json，不复制或重写组件。项目以 `file:vendor/*.tgz` 安装，传递依赖通过 pnpm overrides 指向相同归档，因此构建无需访问 yucer 项目路径。

`provenance.json` 记录版本、来源与归档 SHA-256。归档工具为 `experiments/scripts/archive_local_ds.py`。不要在 vendor 中放认证凭据。

具备私有 registry 认证后，可将依赖切换为已发布的相同版本并移除本地 overrides；认证通过环境或用户配置提供，真实 token 不入仓。

DS 15.0.0、UI 12.0.0、Tokens 4.0.0 是本机 yucer 已安装版本，未宣称为 registry 最新版。

## DS 15.0.1 导航兼容补丁

`../patches/vxture-design-system-15.0.1-navigation.patch` 由 pnpm patchedDependencies 安装时应用，归档本身保持原始哈希。该补丁修正 Tokens 4.0.0 控件尺寸调整后 ShellSidebarNav 的映射：条目 control-2xl（40px）、分组 control-xl（32px）、分组文字 label-small（12px）、分组名称 text-muted-foreground（DS 弱化文字色）；同步覆盖 ESM/CJS。内容按钮及其他 DS 组件不受影响。它是本项目维护的兼容补丁，不代表上游已发布新版本；上游提供对应修复后可删除补丁并升级依赖。

分组标签继承触发器的弱化文字色与交互态，不再单独覆盖文字颜色；源码修正同步位于 DS 仓库 `ShellSidebarNav.tsx`，待上游正式发包后替换项目兼容补丁。
