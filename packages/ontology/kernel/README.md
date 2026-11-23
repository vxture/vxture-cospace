# Vxture Ontology Kernel

独立的本体定义内核，位于 CoSpace 的公共资源产品中，但不依赖 CoSpace。Python >= 3.11，运行时仅使用标准库。独立分发名 `vxture-ontology`，安装后的导入名 `vxture_ontology`。

## 使用

```python
from vxture_ontology import Catalog, builtin_catalog, canonical_bytes

catalog = builtin_catalog()
details = catalog.describe()
bundle = catalog.export('electrical')  # includes the exact core dependency
restored = Catalog.from_bytes(canonical_bytes(bundle))
```

```text
vxture-ontology --module electrical
vxture-ontology --library definitions.json
```

在当前仓库中也可使用 `python -m packages.ontology.kernel --module electrical`。打包入口为本目录的 `pyproject.toml`，资源随包安装，不读取仓库根目录的配置或 Schema。

## 已支持与边界

- 有界 JSON 解析，重复键、非有限数值与未知字段拒绝。
- 核心/领域模块定义，概念及单继承、属性声明、关系方向与端点声明。
- 精确版本/摘要依赖，禁止核心依赖领域，依赖与继承无环检查。
- 概念必须来自自身或依赖闭包；暂不允许覆盖继承属性。
- 确定性依赖导出，返回副本，调用者不能修改内核已加载定义。

内置定义状态为 `draft`。8 个模块、51 个候选概念和 30 类关系是产品语义编制草案，未宣称外部标准等价或专业审核通过。通用核心与室外空间与设施为 `0.1.0`，组织与运营为 `0.3.0`，其余为 `0.2.0`。B08 为园区供配电、安全消防、给排水、环境和运维提供有依据的对象、属性与关系；工作区选择采用前仍须独立发布。B03 实例校验执行本 profile 的结构、引用、属性、端点和候选园区规则；不执行单位换算、业务事实推理、事实核实或场景发布。

`canonical_bytes` 是本 profile 自身的 UTF-8、键排序、紧凑 JSON 编码，不声称 RFC 8785 符合性。模块摘要针对该编码；库摘要针对按模块 ID 排序的导出文档。外部消费者须采用同一编码，或将字节交给内核计算，不用原文件摘要替代。

## 独立性要求

B04a 的 `vxture_ontology.authoring.DefinitionAuthoring` 提供草稿、校验、差异、送审、审批、不可变版本发布和历史读取，要求显式注入事务存储端口与授权函数。不会自动导入数据库或宿主服务，运行时仍仅标准库。SQLite 参考适配器位于纯内核之外的 `packages/ontology/authoring_sqlite.py`，不随独立 wheel 分发。B04b 已通过宿主适配器接入 CoSpace HTTP 与现有模块的业务表单，纯内核依赖方向保持不变。操作与状态详见仓库 `contracts/schemas/ontology-authoring-v0.1.md`。

B09a 新增 `vxture_ontology.workbench.DefinitionWorkbench`。宿主将经过认证的作用域和操作者绑定到工作台：

```python
from vxture_ontology.workbench import DefinitionWorkbench

workbench = DefinitionWorkbench(store, trusted_scope, trusted_actor,
                                 authorize=policy, templates=host_catalog)
summary = workbench.read('core')
```

`store` 实现相同事务端口；`policy(scope, actor, action)` 必须返回严格布尔 True。可以省略 `templates` 使用内置候选定义。现有 `read/edit/submit/review/publish` 策略继续适用；工作台额外检查 `read_private` 才显示草稿、校验细节及送审快照。工作台命令沿用 v0.1 字段，不接收浏览器传来的 actor/scope。授权、部署及持久化仍由宿主负责。

B02 新增 `instance_schema()` 与 `park_baseline_rules()`，返回随独立包分发的 JSON Schema 和显式选用的园区候选完整性规则副本。B03 的 `validate_instances(raw_bytes, catalog, rule_set=None)` 为纯校验入口：未选规则时仍校验引用、属性、端点、有效区间和几何绑定；显式 `rule_set='park-baseline'` 增加职责完整性与时态层级检查。返回带 code、JSON Pointer path、severity、state 的确定性报告，含输入/Schema/定义库/规则摘要。无第三方运行依赖，无现场实例存储或网络访问。

```python
from pathlib import Path
from vxture_ontology import builtin_catalog, validate_instances

report = validate_instances(Path('manufacturing.json').read_bytes(),
                            builtin_catalog(), rule_set='park-baseline')
assert report['valid']  # 仅说明契约及所选规则满足，不证明现场事实
```

```text
vxture-ontology --instances manufacturing.json --rules park-baseline
python -m packages.ontology.kernel --instances examples/ontology/parks/manufacturing.json --rules park-baseline
```

报告 JSON 输出到 stdout；不满足规则退出 1，通过退出 0；读文件失败安全诊断输出 stderr。输入最多 4 MiB、深度 32，工作预算与最多 200 条常规诊断；超限增加明确错误并返回 valid=false。结构解释器只支持随包 Schema 使用的封闭关键词子集，新增未知关键词拒绝，不是通用 JSON Schema 实现。当前只接受内置 park-baseline 名称，不接受自定义规则文件，后续须先定义规则校验与锁定协议。

实例由消费方持有，契约见仓库 `contracts/schemas/ontology-instances-v0.1.md`；三个合成实例位于 `examples/ontology/parks/`。

禁止导入宿主的场景、空间、设备、地图、认证、商业权益、任务、数据库、HTTP 或 UI 模块。本包接收显式字节/定义并返回定义与诊断，不访问网络、不写运行状态。认证、存储、审计和发布由宿主通过外部适配器提供；内核验证不能作为授权依据。

三层体系的第三层是消费方事实。本体产品提供纯实例校验接口，不拥有实例库和现场确认结果。当前旧 `preview_*` 与 Workspace 编制代码仍在父目录，属于 CoSpace 历史集成，未被本内核依赖，也未在本批完成迁移。
