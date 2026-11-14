# 2026-11-15 集中维护检查

## 范围与结论

检查开始时普通 open issue 为 0，open PR 为 12。集中吸收可兼容更新，生成同一批锁文件与生产依赖，统一验证后发布；不逐个合并相互覆盖的锁文件。

| 原 PR | 处理 |
| --- | --- |
| #82 | 首页品牌标识简化为 CoSpace |
| #1 | setup-python v7，覆盖 CI、部署、回滚 |
| #3、#9 | Tailwind 与 Vite 插件同时更新至 4.3.5 |
| #5 | React Query 5.107.1 |
| #6 | pytest 9.2.0 |
| #7 | Three.js 与类型同时更新至 0.187.0 |
| #8 | 不采用 Node 26 类型；运行时与类型保持 Node 24，新增 Dependabot 主版本限制 |
| #69、#70 | 离线工具 lazrs 0.8.2、NumPy 2.5.4，LAS/LAZ 内存压缩读写回归 |
| #71、#72 | psycopg 3.3.8、Pydantic 2.14.3 |

## 修正的生产差异

生产镜像从 deploy/linux/requirements.lock 安装，而依赖 PR 只修改 pyproject.toml 和 uv.lock。集中重新导出生产锁文件；该文件原有 OpenTelemetry 1.45.1，而 uv.lock 已有修复版 1.45.2。同步后镜像才能获得修复。

CI 增加生产锁文件重新导出与差异检查，防止再次漏同步。镜像应用可用的 Debian 安全更新，安装完锁定依赖后移除 pip：Trivy 报告的 msgpack、urllib3、setuptools 来自 pip 的 vendored 工具，并非产品导入的运行时依赖。容器烟测验证安装工具已移除，且模型与双视图流水线仍可执行。

## 安全告警的边界

GitHub 默认分支当前展示 218 条历史镜像扫描告警，涉及 104 种规则；不能等同于 218 个本次新增问题。镜像每次实际构建后的扫描结果才用于判断本批是否消除已知问题，不批量关闭告警。

- Cesium 包含上游公开的默认 Ion 示例 token；jwt-token 告警落在压缩后的上游代码。产品不向源码写入实际 Ion 凭据。该条应按已核实的上游公开示例处理，不能扩展为忽略所有 JWT 扫描。
- 部分 Debian 告警没有 Fixed Version；应用可用更新后保留扫描和后续基础镜像升级跟踪，不以忽略规则伪装已修复。
- SonarCloud 主分支的 4 条历史路径相关告警位于 preview_jobs.py 和 platform_usage.py，涉及本地登记文件及存储清点。现有代码已包含输入登记完整性、场景授权、工作目录与链接检查、对外统一错误，但这不足以直接把告警全判为误报；保留专题跟踪与边界回归要求。本批不改变构建数据格式或授权行为。

## 发布要求

五项必需门禁 quality-gate、build、test-coverage、audit、gitleaks 通过后 squash 合并。主分支同一提交重新通过门禁后发布版本，由 production reviewer 审批，再部署到 worker02 /srv/md0/cospace，并验证健康检查与线上资源版本。
