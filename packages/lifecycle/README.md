# Lifecycle

管理合成服务的登记、受控切换、立即撤回及追溯。ReleaseManager依赖存储事务接口，不直接导入SQLAlchemy。data登记资料、spatial定义空间内容、ontology定义本体，lifecycle负责采用状态。

当前只允许通过已验证的synthetic_point_query样例注册，不接受真实正式发布。激活检查expected_revision，撤回追加事件；历史内容固定但消费有效性每次检查。规则见[验证记录](../../docs/validation/发布生命周期验证-2026-10-26.md)。

独立 F06c 实验在 `trace_events.py` 中提供事件暂存、封闭追溯图校验和 PROV 子集导出；不调用 ReleaseManager 或改变采用状态。详见[契约](../../contracts/schemas/trace-events-v0.1.md)。
