# CoSpace 正式域名部署 · P27

> **历史记录，部署目标错误，禁止照此发布。** 2026-11-06 用户明确：worker01 仅承载 platform，CoSpace 应部署到 worker02。下文保留已发生操作用于追溯；后续以 [worker02 部署纠正](../50-deployment/10-worker02-correction.md) 和 vxtpl 的产品 workflow 为准。此标记不表示迁移已经执行。

## 边界与目录

产品地址 `https://cospace.ruyin.work`，认证保持 `https://accounts.vxture.com`。DNS 已指向 worker01；已有证书 SAN 覆盖 `*.ruyin.work`，本次无需新签证书。

独立 Linux 容器 `cospace-workbench`，UID/GID 10001，单进程 Uvicorn、只读根文件系统、0.75 CPU / 768 MiB 上限。内部发布为 `100.100.197.42:8793`，无公网业务端口。Nginx TLS 终止后转发至该端口。

| 路径 | 内容 |
| --- | --- |
| `/srv/cospace/releases/<release>` | 仅软件的不可变发布包、Dockerfile、依赖锁、软件清单 |
| `/srv/cospace/business` | 独立业务根，runtime / policy / setup，初始无租户绑定及资料 |
| `/srv/cospace/state` | 独立加密会话，业务备份不包含 |
| `/srv/cospace/secrets` | 客户端密钥、稳定会话密钥、产品回调签名密钥，容器按文件读取 |
| `/srv/cospace/evidence` | 运维和验收记录，无凭据 |
| `/srv/vxture/data/nginx/conf/conf.d/90-cospace-product.conf` | CoSpace 专用 vhost，现有证书只读复用 |

平台本机仓库不修改。平台同步脚本会重建 sites-enabled，故产品 vhost 放在 conf.d 的独立文件中；当前同步逻辑复制已知配置但不清理额外 conf.d 文件。若平台未来改为完整清理，升级前须把本产品配置纳入其保留机制。

本次正式业务根为空，不复制 8790 的模拟租户、用户、业务数据或 Windows 绝对路径。Windows 8790 保留原演示流程；8791 保留真实身份验证入口。

## 软件与启动

在本机仓库导出锁定依赖并生成只含软件的包：

```powershell
uv export --frozen --no-dev --extra preview --extra input --no-emit-project --output-file deploy/linux/requirements.lock
.venv/Scripts/python.exe -m experiments.scripts.package_production --output output/deploy/NEW.tar.gz --release NEW
```

发布包包含每个软件文件的 SHA-256。传输后校验包的外部摘要，再构建固定版本镜像；Python 基础镜像也使用已核对的 digest。pip 用 `--require-hashes` 检查依赖。

仅首次、确认业务根为空时执行初始化。初始化命令拒绝覆盖任何已有内容。

```sh
docker run --rm --user 10001:10001 \
  -v /srv/cospace/business:/data \
  cospace:ACCEPTED_RELEASE initialize
```

Compose 中所有密钥均用 `*_FILE`，文件私有且仅 UID 10001 可读。不得把明文值写进 compose、镜像、交接包或输出 `docker inspect` 的完整环境。为当前发布准备仅含镜像名的 `.env`，然后：

```sh
docker compose --env-file /srv/cospace/.env \
  -f /srv/cospace/releases/ACCEPTED_RELEASE/deploy/linux/compose.yml up -d
docker exec cospace-workbench python deploy/linux/healthcheck.py
```

首次运行缺少真实订阅／场景配置仍拒绝业务访问。不能为了验收页面而临时去掉订阅检查或把模拟角色写入正式策略。

## HTTPS 与路由

产品 vhost 源为 `deploy/linux/cospace.nginx.conf`。先确认内部容器可达和平台兄弟站点状态，保留原配置后安装；必须 `docker exec vxture-nginx nginx -t` 成功，才执行平滑 reload。配置校验失败时恢复本批文件，不重启整个平台注册栈。

认证回调不记录 access log，错误日志设为 crit，避免错误请求中夹带 code/state；应用本身关闭 Uvicorn access log。资料上传限额沿用 128 MiB，Webhook 单独限制 64 KiB。

## 回退与备份

升级时先验收新镜像，保留旧镜像和软件清单。更改 `.env` 的镜像名即可回退同一业务根；涉及格式迁移时必须先做独立兼容性核对。本批初始化不改已有平台数据库。

若要完全撤销本次公网入口，将产品专用 vhost 移至 `/srv/cospace/evidence/` 后 nginx -t / reload，再停 CoSpace 容器。保留 business / state / secrets 和镜像，不删除任何业务数据。

业务冷备份前先停 CoSpace；复用 `experiments.scripts.workbench_backup`，保存外部摘要；恢复仍要求同机原绝对路径且目标不存在。会话与密钥独立备份和管理，不能混入业务 ZIP。

## 尚需的真实联调

1. 平台产品保持草稿；确认正式 HTTPS 登录、Secure Cookie、Workspace 权益读取。
2. 用户已在 Opera 登记 Webhook 签名密钥，平台检查确认通过。只读核对尚无 CoSpace 投递记录；需正常订阅触发真实事件，再比对平台投递及产品回执，不能以自发签名测试替代。
3. 由平台提供受控的订阅 Workspace 及第二个隔离 Workspace，配置真实场景权限，验证开通／撤销、成员授权、程序调用。
4. 按实际业务确认计量指标和套餐；本批不新增价格或收费订阅，不宣布正式上线。

最新只读核对、免费邀请套餐提案及逐项验收见 [真实订阅回调联调准备](../validation/真实订阅回调联调准备-P27-2026-11-06.md)。
