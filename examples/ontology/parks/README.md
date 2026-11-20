# 三类园区合成实例 B02

三个包分别为研发办公园 `research-office.json`、制造工业园 `manufacturing.json`、仓储物流园 `logistics.json`，均标记 synthetic。每包 15 个实体、17 个关系断言、4 个简化几何和 4 个几何绑定，复用同一组固定本体模块。不是现场采集或完整生产园区模型，不承担专业规范、定位精度或园区覆盖证明。

建筑实体与建筑空间范围分别标识；企业入驻、空间用途和设施职责分别建模；资产台账记录关联实体；额定电压带单位和来源。研发/制造园引用房间，物流园引用装卸空间；用途由独立的有效期指派描述，不改变空间身份。

全部坐标为合成米制右手局部坐标。没有地理配准，不可直接作为真实经纬度显示。未提供几何的组织、指派、系统等通过语义关系查询；缺少几何并非对象不存在。覆盖声明为 partial，不能推导未记录设施不存在。

契约见 [ontology-instances-v0.1.md](../../../contracts/schemas/ontology-instances-v0.1.md)。反例补丁矩阵单独保存在 `tests/fixtures/ontology-instances/negative-matrix.json`，不作为正常消费实例传播。

从仓库根目录运行：

```text
.venv/Scripts/python.exe scripts/ontology/build_park_examples.py
.venv/Scripts/python.exe -m pytest tests/test_ontology_instance_contract.py -q
```

生成器默认只检查可复现性，不写文件。显式 `--write` 会重建这三个专用样例并重新锁定当前草案，修改后须评审引用和差异；不是实例迁移工具，不写运行状态或客户数据。固定生成时间和证据记录时间为示例编制时间，不表示真实观测。
