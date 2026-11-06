export type FixedVersion = { scene_id: string; release_id: string; truth_version_id: string; frame_id: string; package_sha256: string };
export type DataInspection = FixedVersion & { source_description: string;
  verification: { status: string; verified_at: string | null; source_files_rechecked: boolean };
  items: { path: string; bytes: number; sha256: string; role: string; media_type: string }[] };
export type OntologyInspection = FixedVersion & { ontology_sha256: string;
  definition: { ontology_id: string; version: string; types: Record<string, { properties: Record<string, { type: string; required: boolean }> }> };
  validation: { status: string; object_count: number };
  objects: { object_id: string; type_id: string; properties: Record<string, string>; anchor_xyz: number[]; validation: string }[] };
export function assertVersion(result: FixedVersion, selected: FixedVersion) {
  for (const field of ['scene_id', 'release_id', 'truth_version_id', 'frame_id', 'package_sha256'] as const)
    if (result[field] !== selected[field]) throw new Error('核对内容与所选固定发布不一致');
}
export function Inspection({ data, ontology }: { data: DataInspection; ontology: OntologyInspection }) {
  const roles: Record<string, string> = { ontology: '本体规则', objects: '语义对象', coverage: '覆盖证据',
    truth: '权威空间模型', human_view: '人视图', machine_view: '智能体视图', release: '发布描述', unclassified: '未分类资料' };
  return <>
    <div id="data"><h3>数据管理 · 固定资料清单</h3><p>{data.source_description}</p>
      <div className="notice">登记时已校验大小与摘要 · 校验时点未记录 · 本次未复查源文件<br />采集：无（合成定义） · 使用条件：未评估 · 现场质量：未验证</div>
      <p className="digest">发布 {data.release_id} · 真值 {data.truth_version_id}</p>
      <div className="table-scroll"><table className="objects"><thead><tr><th>逻辑路径 / 角色</th><th>字节 / 类型</th><th>SHA256</th></tr></thead>
        <tbody>{data.items.map(item => <tr key={item.path}><td>{item.path}<small>{roles[item.role] ?? item.role}</small></td>
          <td>{item.bytes}<small>{item.media_type}</small></td><td className="hash">{item.sha256}</td></tr>)}</tbody></table></div>
    </div>
    <div id="ontology"><h3>语义本体 · 类型与实例</h3><p>{ontology.definition.ontology_id} / {ontology.definition.version}</p>
      <p className="digest">本体摘要 {ontology.ontology_sha256}</p>
      <div className="notice">已用固定规则重新校验 {ontology.validation.object_count} 个对象：类型引用、属性声明、必填与字符串类型。<br />这是小型合成规则包，未进行行业本体推理或现场语义确认。</div>
      <table className="objects"><thead><tr><th>类型 ID</th><th>属性约束</th></tr></thead><tbody>{Object.entries(ontology.definition.types).map(([id, type]) =>
        <tr key={id}><td>{id}</td><td>{Object.entries(type.properties).map(([name, rule]) => <div key={name}>{name} · {rule.type} · {rule.required ? '必填' : '可选'}</div>)}</td></tr>)}</tbody></table>
      <h4>对象核对</h4><div className="table-scroll"><table className="objects"><thead><tr><th>对象 / 类型</th><th>属性与锚点</th><th>校验与证据</th></tr></thead><tbody>{ontology.objects.map(object =>
        <tr key={object.object_id}><td>{object.object_id}<small>{object.type_id}</small></td><td>{Object.entries(object.properties).map(([key, value]) => <div key={key}>{key}：{value}</div>)}
          <small>[{object.anchor_xyz.join(', ')}] · {ontology.frame_id} · 米</small></td><td>规则校验通过<small>对象级证据关联未登记</small></td></tr>)}</tbody></table></div>
    </div>
  </>;
}
