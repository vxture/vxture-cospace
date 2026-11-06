# F06b1 领域变更集与候选分支实验契约 0.1

日期：2026-10-28。输入Schema为spatial-change-v0.1.schema.json；schema_version=cospace.spatial-change/0.1。只支持synthetic，输出候选，不产生正式真值、视图或发布。

## 1 固定基线与操作

变更固定scene及base.release_id/release_sha256/truth_id/truth_sha256。先完整验证F04来源快照，再严格比较基线，不能把基于旧版本的变更自动重放到新版本。

| op | 前置条件 | 效果 |
|---|---|---|
| object.add | object_id在基线中不存在 | 新增完整对象记录 |
| object.replace | ID存在且expected_object_sha256匹配 | 替换类型/锚点等当前支持字段，保留对象ID |
| object.remove | ID存在且expected_object_sha256匹配 | 从候选删除，旧基线保留 |
| resource.replace | geometry/coverage角色及expected_sha256匹配 | 整份不透明资源替换，新增成员身份 |

对象前置摘要使用UTF-8、sort_keys=true、separators=(',',':')、ensure_ascii=false、allow_nan=false的JSON字节规则。它是本Python实验Profile的确定规则，尚非跨语言RFC8785规范；外部生成器应读取已验证对象并按此Profile生成，跨语言数值规范需另定版本。

同一对象或同一资源角色每批只允许一次操作，避免操作顺序歧义。类型必须存在于固定本体，锚点必须在固定scope半开范围内。禁止重复新增、无效旧摘要、没有实质变化的对象替换和空对象集（当前F04限制）。坐标、本体、scope迁移及对象拆分/合并不支持，未知操作直接拒绝。

evidence至少一项，每项携带身份、路径、大小与摘要。外部资源只接收已载入的不可变bytes，检查实际大小与摘要；不读取URL或根据输入路径写文件。证据真实性及独立性不在本校验中得到证明。

## 2 候选与影响

build_candidate不修改source或变更输入。输出candidate及按实际摘要寻址的blobs目录；新内容kind=candidate_content，schema_version=cospace.change-candidate/0.1，故不能误投到F04正式结构检查入口。candidate.json目前由领域校验器检查，尚无单独公开输出JSON Schema，不声称为完整的跨语言候选协议。

内容重新引用新objects以及被替换的geometry/coverage；坐标、scope、本体与未变资源复制固定字节。原质量profile/assessment、视图、release及采用记录不复制为新批准。base_provenance只保留外部旧基线引用，基线须独立保存，候选不承诺包含全部历史证据。候选变更清单保留原输入引用，证据新字节由candidate.evidence固定。

所有基线人/机视图都列入impacted_views，view_policy=invalidate_all_no_reuse。即使只有语义对象变化也不能直接复用带旧truth摘要的视图。required_rechecks明确要求独立质量、覆盖分区、语义目标集以及两类视图重新派生；这些只是待办，不假定已执行。

quality_status=pending_independent_validation，publication_status=candidate_only，authorized=false，real_release_ready=false。资源替换只证明字节完整，不解码几何或分区，不能伪造真实建图更新成功。

## 3 提交前置条件

CandidateBranch是进程内、受锁保护的实验分支，固定基线发布摘要。submit要求expected_revision，比较与保存发生在同一锁内；同一revision竞争只有一个成功，失败保留旧head。不做自动重试或冲突自动合并。

这里revision只保护候选分支头，不能代替数据库发布指针CAS、跨进程锁、持久化事务或崩溃恢复。后续不同revision的提交仍是同一基线下的候选替换，不自动把旧候选叠加成新基线。返回published=false，正式发布内容及旧ReleaseManager未变。

validate_candidate检查候选关键状态、内容身份、固定成员摘要和多余字节，submit再次执行并保存隔离副本。这是内部传输一致性检查，不是独立采用审批或恶意输入的生产验收入口；正式接入前仍须从受控变更重新构建并审核完整语义。

## 4 资源与示例

最多256操作、16项证据；资源字典最多32项，每项8MiB、总计32MiB。禁止明显越界/大小写碰撞路径、重复资源身份和未引用字节。不处理压缩包、执行脚本或安装插件。

运行 `.venv/Scripts/python.exe -m experiments.scripts.generate_change_sample` 生成examples/spatial-change：变更输入、输入资源、candidate.json与9个内容寻址blob。样例移动cabinet-a并替换整份覆盖占位资源，不能证明独立检测变化、增量建图或新质量通过。

## 5 下一增量

本轮F06b1只支持整个几何/覆盖资源替换，不将其称为细粒度体素块更新。F06b2需针对F05定义按逻辑块索引的add/replace/remove、旧块摘要与缺块前置语义、目标包摘要重建及受影响范围分析；完成后再推进F06c事件/追溯。实际合并发布仍须独立校核、视图重建与受控原子切换。
