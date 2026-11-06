# 智能体运行包合成契约0.1

日期：2026-10-27。状态：R0实验子集已实现；不是正式机器人交付格式。结构规范为[JSON Schema](agent-package-v0.1.schema.json)，领域验证由packages/views/agent/runtime.py执行。

## 范围与来源

只接受cospace.synthetic-bundle/0.2固定本地来源和synthetic-region-reading/0.1配置。包只含清单、覆盖、对象及本体，不含人视图、纹理或代码；view_kind仍为machine。本轮按用途选择组件，不实现空间裁剪、体素化或精度改变。frame、scope和组件字节必须与来源完全一致。

来源绑定scene、release、truth、view身份和各自摘要，以及原包清单摘要。校验必须提供--source，先完整验证来源，再比较身份、坐标和组件内容；外部来源仅为一致性参照，不是可信签发者。R0尚不是自包含离线交付包，机器人SDK未实现。

## 组件及兼容

| role | encoding | 依赖 |
|---|---|---|
| occupancy | synthetic-regions/0.2 | 无 |
| ontology | synthetic-ontology/0.1 | 无 |
| semantics | synthetic-objects/0.1 | 对应ontology组件 |

本配置三类组件各一个且必需。组件ID唯一，成员路径不得重复或大小写冲突，依赖存在且无环。未知必需角色/编码拒绝；未知可选组件校验内容后跳过并返回skipped_components。必需组件依赖被跳过组件时拒绝。扩展字段不代表已实现距离场、定位或拓扑。

最多16组件，单成员8MiB，清单及声明成员合计32MiB。拒绝越界、链接/重解析点、Windows保留路径及重复JSON键。只读取声明成员，不执行额外文件，不接收压缩包。适用于受信任本机静态目录，不防护恶意并发文件替换。

Schema负责字段结构；来源绑定、坐标相等、依赖闭包和内容关系由领域校验检查。frame结构依赖已验证来源和严格相等比较，不能只凭Schema声称坐标正确。

## 结果、错误与写入

成功返回package_id、清单摘要、source、verified_bytes、usable_components和skipped_components，固定robot_ready=false、real_release_ready=false、validity=unverified_sample_only。不验证签名、撤回、离线时限，不安装或激活包。

主要领域错误：structure_error、source_mismatch、coordinate_mismatch、duplicate_component、missing_dependency、dependency_cycle、unsupported_component、unsupported_dependency、profile_mismatch、content_mismatch。文件层错误由CLI统一返回validation_error；SDK错误映射尚未冻结。CLI通过退出0，拒绝退出2。

输出目录必须不存在且与来源互不包含。导出失败可能留下未完成目录，目录存在不代表就绪；正式封存、安装及断电安全留到R1。
