import { useEffect, useRef, useState } from 'react';

type Binding = Record<string, string> & {scene_id: string; release_id: string};
type Generation = {report_id: string; producer: {name: string; version: string}; limit: number;
  binding_sha256: string; payload_sha256: string;
  interval: {started_at: string; finished_at: string; elapsed_ms: number; wall_end_before_start: boolean};
  sources: {files: {locator_sha256: string; component_report_sha256: string};
    journal: {locator_sha256: string; component_report_sha256: string;
      control: {store_id: string; context: string; generation: number; revision: number; mode: string; state_sha256: string} | null}}};
type Envelope = {schema_version: string; source: {sha256: string; read_at: string; observed_at: null}; report: {
  generation: Generation | null;
  requested_binding: Binding; complete: boolean; needs_attention: boolean;
  observed: {binding_match: boolean; active_revision: number | null; journal_status: string};
  components: Record<'files' | 'journal', {complete: boolean; needs_attention: boolean}>;
  findings: {code: string; component: string; next_action: string}[];
  validity: string; authorized: false; robot_ready: false; repair_authorized: false;
}};
type ReportItem = {report_key: string; report_id: string; sha256: string;
  interval: {started_at: string; finished_at: string}; requested_binding: Binding; complete: boolean; needs_attention: boolean};
const names: Record<string, string> = {scene_id: '场景', release_id: '发布', truth_version_id: '真值版本',
  view_version_id: '智能体视图版本', package_sha256: '运行包摘要', release_sha256: '发布摘要',
  truth_sha256: '真值摘要', view_sha256: '视图摘要', profile: '用途配置', scope_sha256: '范围摘要'};
const components: Record<string, string> = {files: '文件包', journal: '恢复日志', binding: '版本绑定'};
const showTime = (value: string) => new Date(value).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  hour12: false, fractionalSecondDigits: 3});

export default function Delivery({scene, release}: {scene: string; release: string}) {
  const [data, setData] = useState<Envelope | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  const [items, setItems] = useState<ReportItem[] | null>(null);
  const [chosen, setChosen] = useState('');
  useEffect(() => () => active.current?.abort(), []);
  const selectedItem = items?.find(item => item.report_key === chosen);
  async function refresh(key?: string) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setData(null); setError(''); setBusy(true);
    try {
      const base = `/scenes/${encodeURIComponent(scene)}/releases/${encodeURIComponent(release)}`;
      const response = await fetch(key ? `${base}/delivery-reports/${encodeURIComponent(key)}` : `${base}/delivery`,
        {cache: 'no-store', signal: controller.signal});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail?.message ?? '报告读取失败');
      const result = value as Envelope;
      if (key && ((value.source?.report_key !== key) || value.source?.sha256 !== key.slice(37))) throw new Error('所选报告摘要不一致');
      if (result.schema_version !== 'cospace.saved-delivery/0.1' ||
          result.report.requested_binding.scene_id !== scene || result.report.requested_binding.release_id !== release ||
          result.report.authorized !== false || result.report.robot_ready !== false || result.report.repair_authorized !== false ||
          result.report.validity !== 'not_evaluated') throw new Error('报告身份或诊断边界不一致');
      if (!controller.signal.aborted) setData(result);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '报告读取失败');
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function loadList() {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setData(null); setItems(null); setChosen(''); setError(''); setBusy(true);
    try {
      const response = await fetch(`/scenes/${encodeURIComponent(scene)}/releases/${encodeURIComponent(release)}/delivery-reports`,
        {cache: 'no-store', signal: controller.signal});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail?.message ?? '报告列表读取失败');
      if (value.schema_version !== 'cospace.delivery-report-list/0.1' || value.scene_id !== scene ||
          value.release_id !== release || value.selection !== 'explicit_key_required' || value.authorized !== false ||
          !Array.isArray(value.items)) throw new Error('报告列表身份不一致');
      if (!controller.signal.aborted) setItems(value.items);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '列表读取失败');
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="panel" id="delivery" aria-busy={busy}>
    <h2>智能体交付 · 只读核对</h2>
    <p>目标：{scene} / {release}。报告独立于上方发布查询；完整绑定见报告明细。</p>
    <p className="notice">展示已保存的合成核对报告。刷新只重新读取文件；底层状态可能已变化，需重新生成报告才能再次核对。观察时间来自本机普通时钟，读取时间不代表状态新鲜度。</p>
    <button disabled={busy || !scene || !release} onClick={() => void refresh()}>{busy ? '读取报告中…' : '读取 / 刷新交付报告'}</button>
    <div className="actions"><button className="secondary" disabled={busy || !scene || !release} onClick={() => void loadList()}>读取 / 刷新报告列表</button></div>
    {items && <div className="delivery-picker"><p>共{items.length}份报告，按固定标识排序。不会自动选最新；选择不会改变服务发布。</p>
      <label>报告批次<select value={chosen} disabled={busy} onChange={event => {setChosen(event.target.value); setData(null); setError('');}}>
        <option value="">请选择一份报告</option>{items.map(item => <option key={item.report_key} value={item.report_key}>
          {item.report_id} · {item.sha256.slice(0, 12)} · {item.needs_attention ? '需处理' : '无待处理项'}
        </option>)}
      </select></label>
      {selectedItem && <><p className="digest">固定选择：{chosen}</p>
        <p>真值版本：{selectedItem.requested_binding.truth_version_id}<br />智能体视图版本：{selectedItem.requested_binding.view_version_id}<br />用途：{selectedItem.requested_binding.profile}<br />观察结束：{showTime(selectedItem.interval.finished_at)}（生成端普通时钟）</p>
        <details><summary>所选报告完整目标绑定</summary><dl className="delivery-binding">{Object.entries(selectedItem.requested_binding).map(([key, value]) => <div key={key}><dt>{names[key] ?? key}</dt><dd>{value}</dd></div>)}</dl></details>
      </>}
      <button disabled={busy || !chosen} onClick={() => void refresh(chosen)}>读取所选批次</button>
    </div>}
    <div aria-live="polite">{busy && <p>正在读取，旧报告已清除。</p>}{error && <p role="alert" className="error">{error}；旧报告已清除。</p>}</div>
    {!data && !busy && !error && <p className="empty">尚未读取交付核对报告。</p>}
    {data && <>
      <div className="summary" data-testid="delivery-summary">
        <div><small>观察范围</small><strong>{data.report.complete ? '有界观察完成' : '观察未完成'}</strong></div>
        <div><small>待处理项</small><strong>{data.report.needs_attention ? '需要处理' : '报告内无待处理项'}</strong></div>
        <div><small>完整绑定</small><strong>{data.report.observed.binding_match ? '报告记录一致' : '未匹配'}</strong></div>
        <div><small>活动修订</small><strong>{data.report.observed.active_revision ?? '未读到'}</strong></div>
      </div>
      <p>本次读取：{showTime(data.source.read_at)}（北京时间，服务端普通时钟）<br />有效性：未评估。机器人运行授权：未授予。</p>
      {data.report.generation ? <div className="notice" data-testid="delivery-generation">
        <p className="digest">报告批次：{data.report.generation.report_id}</p>
        <p>观察开始：{showTime(data.report.generation.interval.started_at)}<br />观察结束：{showTime(data.report.generation.interval.finished_at)}<br />单调计时耗时：{data.report.generation.interval.elapsed_ms}毫秒；时间均为北京时间，来自生成端普通时钟。</p>
        <p>各组件分别观察，不构成跨库一致快照；观察区间不代表有效期限。</p>
        {data.report.generation.interval.wall_end_before_start && <p role="alert">结束时间早于开始时间，存在系统时钟异常；耗时采用单调计时，不据墙上时间判断新鲜度。</p>}
      </div> : <p className="notice" data-testid="delivery-legacy">旧版报告：批次、底层观察区间及来源上下文未记录，无法补推。</p>}
      <p className="digest">保存报告 SHA-256：{data.source.sha256}</p>
      <h3>问题与后续行动</h3>
      {data.report.findings.length ? <ul className="delivery-findings">{data.report.findings.map((finding, index) =>
        <li key={index}><strong>{components[finding.component] ?? finding.component} · {finding.code}</strong><p>{finding.next_action}</p></li>)}</ul> : <p>本报告无待处理项；仍需独立运行门禁判定。</p>}
      <details><summary>完整版本绑定与组件状态</summary>
        <dl className="delivery-binding">{Object.entries(data.report.requested_binding).map(([key, value]) =>
          <div key={key}><dt>{names[key] ?? key}</dt><dd>{value}</dd></div>)}</dl>
        {Object.entries(data.report.components).map(([key, value]) => <p key={key}>{components[key]}：{value.complete ? '观察完成' : '观察未完成'} / {value.needs_attention ? '需处理' : '报告内无待处理项'}</p>)}
        <p>证明字段记录：{data.report.observed.journal_status === 'proof_fields_present_unverified' ? '字段齐备，未验证' : data.report.observed.journal_status === 'proof_fields_missing' ? '字段缺失' : '未检查'}。未验签、未验证历史、未授予修复权限。</p>
      </details>
      {data.report.generation && <details><summary>报告生成与来源上下文</summary>
        <p>生成器：{data.report.generation.producer.name} / {data.report.generation.producer.version}；核对限额：{data.report.generation.limit}</p>
        <p className="digest">目标绑定摘要：{data.report.generation.binding_sha256}<br />报告诊断内容摘要：{data.report.generation.payload_sha256}</p>
        <p className="digest">文件位置指纹：{data.report.generation.sources.files.locator_sha256}<br />文件组件报告摘要：{data.report.generation.sources.files.component_report_sha256}</p>
        <p className="digest">日志位置指纹：{data.report.generation.sources.journal.locator_sha256}<br />日志组件报告摘要：{data.report.generation.sources.journal.component_report_sha256}</p>
        {data.report.generation.sources.journal.control ? <>
          <p className="digest">日志库：{data.report.generation.sources.journal.control.store_id}<br />上下文摘要：{data.report.generation.sources.journal.control.context}<br />状态摘要：{data.report.generation.sources.journal.control.state_sha256}</p>
          <p>代次：{data.report.generation.sources.journal.control.generation}；修订：{data.report.generation.sources.journal.control.revision}；模式：{data.report.generation.sources.journal.control.mode}</p>
        </> : <p>日志控制身份未读到或格式不符。</p>}
        <p>位置指纹只关联生成端的规范化目录，不能证明设备身份或内容未被替换；摘要未签名，不提供来源认证。</p>
      </details>}
    </>}
  </section>;
}
