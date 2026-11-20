# 语义本体阶段版本发布范围

日期：2026-11-20。版本范围固定为公共资源—语义本体，保留该名称。后续产品独立化可使用本体引擎作为产品名，不改变本次导航。

## 本次交付

- 独立定义内核和 UI；8 个预置候选模块、42 个概念、19 类关系。
- 目录、筛选分页、系统配置分组、资源归组；固定功能导航，资源数据在内容区呈现。
- 已有模块的元数据、概念、属性与关系编辑，草稿保存、单独校验和固定依赖选择。
- 送审快照、不同主体审批、不可变版本发布、精确历史读取及导出；发布工件状态与内容候选成熟度分别表达。
- 可信宿主认证、管理权限、CSRF、并发修订和幂等；独立库不得导入宿主认证、场景、数据库或商业权益。

实例契约、纯校验器和合成样例作为已完成的内部基础随源代码保留，不新增面向消费方的接口、实例库或地图页面。本次不宣称整套园区行业标准已完成专业签核。

## 下一版本

空间关联的消费侧实例存储、实例采用、有效期查询、证据联查、局部几何定位和态势地图接入，全部延期。现有本地消费侧试作文件不纳入本次提交：

```text
packages/infrastructure/semantic_instance_store.py
packages/spatial/semantic_instances.py
tests/test_scene_semantic_instances.py
```

不更改既有场景发布/核验、权限与商业权益边界。新模块创建向导、批量导入、复杂兼容性自动分析及海量存储性能另行安排，不延长本次上线范围。

## 发布与回退

仅通过 feature PR、quality-gate/build/test-coverage/audit/gitleaks，squash merge 到 main；选择未使用的发布标签构建该提交镜像，生产 Environment reviewer 批准后部署 worker02。遵守 `10-worker02-correction.md`，不上传本地源码、不直接部署 main、不绕过生产审批。

新增运行文件位于宿主现有持久运行根目录：ontology-group-configuration.sqlite3 和 ontology-authoring.sqlite3，首次使用惰性创建，不迁移或覆盖既有场景数据。部署前按既有运维方式备份运行数据。回退采用前一已验证镜像与发布机制；保留新数据库，不因旧版本未使用它们而删除，禁止把 SQLite 文件或身份状态提交 Git。

发布前核对生产 Environment 审批、STACK_ROOT、DEPLOYMENT_READY 和 worker02 目标；凭据只通过 GitHub Environment 注入。实际检查、PR、标签与生产结果在任务回复及 GitHub 记录，不在本文件预写成功结论。
