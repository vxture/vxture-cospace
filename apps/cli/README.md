# 本地工程命令入口

首个入口用于校验离线清单与合成服务包，输出明确诊断及执行结果；后续按需增加固定版本查询。

CLI调用spatial和service，不复制领域规则。正式算法试验工具目前仍在experiments/scripts；后续稳定能力提升为产品模块后，试验入口改为调用该模块。

当前采用Python3.14、根uv环境及标准jsonschema库。从仓库根目录运行：

```sh
uv run --locked python -m apps.cli.check_sample examples/indoor
```

输出JSON，成功退出码为0，校验或读取失败为2。--channel real始终拒绝。该命令只读，不执行正式发布或撤回。

结构错误的error包含code=structure_error、文件名file、JSON Pointer字段路径path及message。其他错误当前统一为validation_error及message。正常样例输出保持不变；旧版字符串error已调整为对象，尚无对外稳定接口兼容承诺。

新增点查询入口：

```sh
uv run --locked python -m apps.cli.query_sample examples/indoor-spatial --scene synthetic-equipment-corridor --release release-spatial-sample-001 --frame sample-local --point 5 3 1
```

输出occupied及固定版本摘要。错误退出2；空间unknown/out_of_scope是正常查询结果，退出0。此命令不修改指针、不执行撤回或正式发布。

## 持久化合成发布管理

设置COSPACE_DATABASE_URL指向专用PostgreSQL演示库，使用以下命令（不要指向其他项目或正式数据库）：

```sh
uv run --locked python -m apps.cli.releases init-demo
uv run --locked python -m apps.cli.releases register examples/indoor-spatial
uv run --locked python -m apps.cli.releases activate --scene synthetic-equipment-corridor --release release-spatial-sample-001 --expected-revision 0 --actor engineer
uv run --locked python -m apps.cli.releases current --scene synthetic-equipment-corridor
uv run --locked python -m apps.cli.releases revoke --scene synthetic-equipment-corridor --release release-spatial-sample-001 --actor reviewer --reason "sample defect"
uv run --locked python -m apps.cli.releases trace --scene synthetic-equipment-corridor --release release-spatial-sample-001
```

首次激活预期revision为0；后续使用current返回的实际值，不能盲重试旧请求。query子命令携带scene/release/frame/point且每次检查撤回。原query_sample命令是独立文件快照演示，不检查数据库撤回。init-demo只做显式试验建表，不能替代正式迁移；actor不是认证身份。


真实预览消费：`python -m apps.cli.preview_consumer --root 独立目录`，提供init、install、list、status、activate和restore。安装不切换，重启后显式恢复，保存绑定与查询会话分开；支持点、对象及有限范围查询。见[操作手册](../../docs/guides/预览消费版本保存与恢复.md)。
