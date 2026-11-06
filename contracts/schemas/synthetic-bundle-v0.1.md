# 合成服务包试验契约

标识：`cospace.synthetic-bundle/0.1`\
状态：实验性子集；仅供本地元数据验证，不是正式真值或服务发布格式。

## 文件与引用

包入口为package.json，包含profile、scene_id、data_kind、release及data。data_kind固定为synthetic；data记录source_description及files。文件登记包含path、bytes、sha256、media_type；本轮仅支持JSON文件。路径相对包根目录，禁止绝对路径、反斜杠、盘符、父目录越界及解析后的包外链接。

所有依赖引用包含path及sha256，内容必须登记且与实际字节一致。JSON拒绝重复键及NaN/Infinity。SHA256证明内容一致，不证明来源可信；入口清单未签名，不能作为对外信任根。本轮默认本地可读取的小型包，不提供不可信大型文件上传或资源配额服务。

## 固定关系

- release引用一个truth及至少一个human视图和一个machine视图；目录agent不改变machine交换取值。
- truth含固定truth_version_id、场景、合成来源、frame、target_scope、objects、ontology_ref、quality及sample_only采用标记。
- ontology_ref固定ontology_id、version及摘要；本体types定义稳定类型ID和字符串属性的必要性。本轮不支持关系、单位换算、类型继承或迁移。
- objects具有唯一object_id、type_id、properties、anchor_xyz和synthetic确认标记。类型和必要属性必须符合所引用本体，锚点必须在目标范围内。
- 视图必须引用与release完全相同的truth引用，采用相同坐标和对象快照。preparation固定为manual_sample，不能据此声称已实现真实派生。
- frame固定为米制、右手系、X沿走廊/Y向左/Z向上的合成工程坐标；不支持坐标转换。
- capabilities仅允许reference_reading，表示引用完整性检查范围；不宣称浏览、量测、空间查询或重定位已验证。

具体实例见[合成包](../../examples/README.md)，校验入口见[CLI](../../apps/cli/README.md)。结构规范位于[JSON Schema](synthetic-bundle-v0.1.schema.json)，采用Draft 2020-12及本地定义引用，覆盖入口、文件引用、坐标、本体、对象、真值、视图和发布。固定结构拒绝未知字段；本体类型和实例属性允许动态键，分别由模式与本体内容约束。兼容性变化须显式修订试验profile，不能向固定结构静默加字段。

本地工具仅实现该结构规范实际使用的关键词，未实现通用JSON Schema引擎；遇到不支持的关键词直接报错，不静默忽略。bytes要求JSON整数字面量（不接受1.0或布尔值），这一输入限制比JSON Schema的整数数值语义更严格。结构检查在相应文档参与领域规则前执行，跨文件来源、摘要和能力检查仍由领域代码负责。本轮未使用独立JSON Schema实现做交叉验证。

结构错误返回code=structure_error、file、path及message；path使用JSON Pointer，根节点为空字符串，键中的斜杠和波浪线按规范转义。其他输入或领域错误返回code=validation_error及message；尚未统一细分所有语义错误码。CLI错误退出码为2，不输出成功标记。

## 与总体契约的差距

本轮不包含几何与覆盖文件、独立校核、受控审核、真实数据集登记、当前指针、撤回、查询或访问控制。quality明确为not_field_validated。real通道无条件拒绝；返回real_release_ready=false。后续正式实现不能将此子集直接改名为生产格式。
