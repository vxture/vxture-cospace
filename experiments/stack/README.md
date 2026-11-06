# 技术栈兼容试验

本目录为选型证据，不是产品API或工作台。依赖按试验锁定，虚拟环境、node_modules及dist不提交仓库。评估结论见[设计记录](../../docs/architecture/技术栈评估与确认-v0.1.md)。

从仓库根目录运行（需Python 3.14、uv及Node24/pnpm）：

```powershell
uv sync --project experiments/stack/python --python C:/Python314/python.exe --locked
./experiments/stack/python/.venv/Scripts/python.exe experiments/stack/python/evaluate.py
pnpm --dir experiments/stack/web install --frozen-lockfile --ignore-scripts
pnpm --dir experiments/stack/web run build
./experiments/stack/run-database.ps1
```

解释器路径是本机例子，其他机器指定其3.14路径。数据库脚本依赖本地postgres:18镜像，使用本地解析后的不可变镜像ID执行并保存元数据，创建独立临时容器，最终移除；不要用生产数据库连接串运行试验。脚本需要Docker权限，不挂载其他项目数据。

results保存通过范围与限制。web-build.log可能较大；严格第三方声明检查确实失败，当前skipLibCheck=true仅使应用类型检查与打包可以继续，不代表问题消失。数据库脚本随后可以重跑以更新最终依赖组合的证据。
