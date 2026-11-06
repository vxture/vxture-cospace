# 固定发布来源追溯：上传资料与批次补充字段

P10对现有`cospace.preview-lineage/0.1`作兼容性补充，保持登记资料、构建、固定发布、离线包四个节点及原关系不变。

`GET /publications/<id>/api/lineage`的登记资料节点在固定模型确实保存对应引用时增加：

```json
{
  "kind": "input",
  "registration_ref": {
    "method": "uploaded_package",
    "profile": "cospace.input-upload/0.1",
    "package_sha256": "<上传ZIP原始字节SHA-256>",
    "actor": "<登记时已验签主体>"
  },
  "batch_ref": {
    "batch_id": "<封存批次ID>",
    "admitted_revision": 2,
    "sealed_members_sha256": "<封存成员摘要>",
    "input_record_sha256": "<登记记录摘要>",
    "space_id": "<场景ID>",
    "project_id": "<项目ID>"
  }
}
```

这两个字段来自发布快照的`source.input_binding.registration_ref`与`source.batch_ref`。不重新按当前资料、路径或最新批次推断，不反写模型或发布，不给旧记录补造字段。已配置来源的`registration_ref`保持原结构；没有相关引用时字段缺省。

登记节点的状态继续核对当前登记与固定输入绑定；它不表示当前批次状态已经重新核验。批次引用表示构建准入时保存的修订，当前启停／历史需要进入对应批次查看。

构建节点新增同一性条件：任务中的`batch_ref`必须与固定模型的来源一致。任务被改成其他批次或其他修订时，节点显示`mismatch`；固定发布本身不因此重写。历史未记录批次时两侧都缺省仍兼容。

页面在原来源节点内显示上传方式和操作者，摘要按需展开显示上传包及封存成员摘要；返回资料和来源批次的链接携带明确场景、资料和批次。原生产就绪及机器人就绪标记不变。
