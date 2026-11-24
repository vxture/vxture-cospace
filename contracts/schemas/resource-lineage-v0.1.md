# 来源与引用追溯 v0.1

状态：D04a，2026-11-25。只读展示已登记版本及实际引用边，不宣称为完整处理血缘图。没有版本替换、归档或删除命令。

`GET/HEAD /api/data-lineage`：必填 resource_id；可选 project_id、offset（0～10000）、limit（1～100，默认20）。未知、重复参数及写入方法拒绝；中央会话与当前业务权限始终核验。响应 no-store。

不传 project_id 为来源管理视角，要求 workspace_manager，来源有场景还须 data.manage / space.manage。返回已登记版本、当前可读来源、共享快照是否保存及当前身份可见的实际引用。存在新源版本但尚未登记时，只在 source.version_id 表示当前来源，不能冒充已登记版本。来源暂不可读取时 status=partial、source.state=unavailable，历史登记保留，不能推断来源已删除或当前版本已回退。

传 project_id 为接收项目引用视角，须有当前项目访问权限且至少存在该资源的实际引用，只有授权但未使用时拒绝。仅返回此项目的可见引用及其固定版本快照；source.state=restricted，来源位置、链接、当前源版本与版本登记时间均为 null，不返回来源场景 ID、原记录标识、未使用的版本或其他项目引用。已撤销、到期或解除的历史引用仍按项目权限可核对，不恢复其下载权限。

profile=`cospace.resource-lineage/0.1`。resource 为可披露名称、类型和管理归属名称；versions 为固定元数据版本、登记时间、当前来源匹配状态及快照状态；references 复用 D03a 可见使用记录。source_files_rechecked=false，目录查询不下载原件或重新核验字节。

引用分页在权限过滤后进行；summary 为当前可见全集统计，不随分页变化：linked_references 为尚未解除的关联数（含失效授权）、effective_references 为授权仍有效的关联数、historical_references 为已解除数、projects 为尚未解除关联的去重项目数。summary.scope / impact.scope 固定 visible_only。不存在可见引用不等于全局无引用；impact.global_assessment=not_assessed，physical_delete_supported=false。retention_required 仅表示已发现仍关联的引用，不构成删除或归档许可。

读取不修改资源、授权、引用、项目、构建或发布。损坏登记、快照或共享记录失败关闭。每资源最多1000个登记版本，共享记录沿用10000条扫描上限；原件载荷不参与本接口扫描。源资料与消费引用不自动升级；处理输入输出血缘、显式升级及归档治理在后续 D04b / D04c 完成。

401 未登录；403 无来源管理权限、项目不可访问或不存在实际引用；422 参数无效；503 登记 / 快照不可用或查询超预算。
