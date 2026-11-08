# 固定发布来源 0.1

`GET /publications/{id}/api/provenance`，无参数；授权模式要求当前场景data.manage及space.preview。401未登录，403权限／范围不满足，409指定发布或其固定依据不可读。响应no-store。

profile为`cospace.publication-provenance/0.1`，包含publication_id、project_id／space_id、checked_at、nodes、notice。node含kind、title、status、id（可空）、detail及已有摘要／固定规则引用。status为matched／mismatch／missing。package_generated固定false；preflight_sequence固定null，历史构建未保存序号。没有节点表明消费端安装或启用状态。

先校验固定发布快照，再检查当前可读取的来源绑定；不是跨库事务快照。输入／任务缺失或变化保留缺失／不一致，不回退到最新选择；同一固定发布后续读取的当前来源状态可以变化，但发布自身不改写。本接口不生成ZIP、不执行预检、不触发构建、不写消费记录。

v0.6.0增加可选build_admission及build_admission_status（recorded／invalid／not_recorded）。仅新增点云构建保存实际准入文件校验依据，派生沿用原依据；preflight_sequence仍为null，坐标修订要求的历史预检序号位于依据内saved_preflight_sequence，二者不混用。历史及其他格式不回填。细节见[构建准入与本体使用查询](build-admission-and-ontology-usage-v0.1.md)。
