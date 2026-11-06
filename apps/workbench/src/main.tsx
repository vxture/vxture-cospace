import { lazy, Suspense, useState, type FormEvent } from 'react';
import type { HumanView } from './SpatialView';
import { Inspection, assertVersion, type DataInspection, type OntologyInspection } from './Inspection';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import './style.css';
import Jobs from './Jobs';
import Delivery from './Delivery';
const SpatialView = lazy(() => import('./SpatialView'));

type Release = { scene_id: string; release_id: string; revision?: number; active?: boolean;
  truth_version_id: string; frame_id: string; package_sha256: string; revocations?: { reason: string; actor: string; created_at: string }[] };
type PointResult = Release & { point: number[]; state: string; reason: string; evidence_ids: string[] };

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, body === undefined ? { cache: 'no-store' } : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw new Error(`${response.status} · ${data.detail?.message ?? data.detail?.code ?? '请求失败'}`);
  return data as T;
}

function App() {
  const [scene, setScene] = useState('synthetic-equipment-corridor');
  const [release, setRelease] = useState('release-spatial-sample-001');
  const [selected, setSelected] = useState<Release | null>(null);
  const [coords, setCoords] = useState(['5', '3', '1']);
  const [point, setPoint] = useState<PointResult | null>(null);
  const [human, setHuman] = useState<HumanView | null>(null);
  const [inspection, setInspection] = useState<{data: DataInspection; ontology: OntologyInspection} | null>(null);
  const inspect = useMutation({ mutationFn: async (version: Release) => {
    const path = `/scenes/${encodeURIComponent(version.scene_id)}/releases/${encodeURIComponent(version.release_id)}`;
    const [data, ontology] = await Promise.all([request<DataInspection>(`${path}/data`), request<OntologyInspection>(`${path}/ontology`)]);
    assertVersion(data, version); assertVersion(ontology, version);
    return { data, ontology };
  } });
  const preview = useMutation({ mutationFn: async (version: Release) => {
    const result = await request<HumanView>(`/scenes/${encodeURIComponent(version.scene_id)}/releases/${encodeURIComponent(version.release_id)}/human`);
    if (result.scene_id !== version.scene_id || result.release_id !== version.release_id ||
        result.truth_version_id !== version.truth_version_id || result.frame_id !== version.frame_id ||
        result.package_sha256 !== version.package_sha256) throw new Error('人视图与所选固定发布不一致');
    return result;
  } });
  const read = useMutation({ mutationFn: ({ scene, release, current }: { scene: string; release: string; current: boolean }) =>
    request<Release>(current ? `/scenes/${encodeURIComponent(scene)}/current` :
      `/scenes/${encodeURIComponent(scene)}/releases/${encodeURIComponent(release)}`) });
  const query = useMutation({ mutationFn: (body: unknown) => request<PointResult>('/query', body) });
  const clearInspection = () => { setInspection(null); inspect.reset(); };
  const clear = () => { setSelected(null); setPoint(null); setHuman(null); clearInspection(); preview.reset(); read.reset(); query.reset(); };
  async function loadInspection() {
    setInspection(null);
    if (!selected) return;
    try { setInspection(await inspect.mutateAsync(selected)); }
    catch { setHuman(null); setPoint(null); }
  }
  async function loadHuman() {
    setHuman(null); setPoint(null); query.reset();
    if (!selected) return;
    try {
      const result = await preview.mutateAsync(selected);
      setHuman(result);
    } catch { setHuman(null); setInspection(null); }
  }
  async function load(current: boolean) {
    setSelected(null); setPoint(null); setHuman(null); clearInspection(); preview.reset(); query.reset();
    try {
      const result = await read.mutateAsync({ scene, release, current });
      setSelected(result); setRelease(result.release_id);
    } catch { /* Render the explicit error state, never a default spatial status. */ }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setPoint(null);
    if (!selected) return;
    const xyz = coords.map(Number);
    if (coords.some(value => value.trim() === '') || !xyz.every(Number.isFinite)) return;
    try { setPoint(await query.mutateAsync({ scene_id: selected.scene_id, release_id: selected.release_id,
      frame_id: selected.frame_id, point: xyz })); } catch { setHuman(null); setInspection(null); }
  }
  const busy = read.isPending || query.isPending || preview.isPending || inspect.isPending;
  const revoked = selected?.active === false || Boolean(selected?.revocations?.length);
  const labels: Record<string, string> = { occupied: '占据', observed_free: '已观测空闲', unknown: '未知', out_of_scope: '范围外' };
  return <div className="shell">
    <aside><div className="brand">CoSpace<span>空间态势工作台</span></div><nav aria-label="工作区域"><strong>发布与查询</strong><a href="#inspection">数据管理 · 只读核对</a><a href="#inspection">语义本体 · 只读核对</a><a href="#jobs">构建与校核 · 只读任务</a><a href="#delivery">智能体交付 · 只读核对</a></nav><p>真值建一次<br />两类视图共用之</p></aside>
    <main><header><div><span className="eyebrow">工程验证 / P2</span><h1>发布与空间查询</h1><p>固定版本读取，保留空间状态与证据来源。</p></div><span className="badge">合成样例 · 非现场结论</span></header>
      <section className="panel"><h2>选择发布</h2><div className="fields"><label>场景 ID<input value={scene} disabled={busy} onChange={e => { setScene(e.target.value); clear(); }} /></label><label>发布 ID<input value={release} disabled={busy} onChange={e => { setRelease(e.target.value); clear(); }} /></label></div>
        <div className="actions"><button disabled={busy || !scene} onClick={() => void load(true)}>读取当前发布</button><button className="secondary" disabled={busy || !scene || !release} onClick={() => void load(false)}>追溯指定发布</button></div>
        {read.error && <p role="alert" className="error">{read.error.message}</p>}
        {selected && <div className="summary"><div><small>固定发布</small><strong>{selected.release_id}</strong></div><div><small>真值版本</small><strong>{selected.truth_version_id}</strong></div><div><small>坐标系</small><strong>{selected.frame_id}</strong></div><div><small>当前有效性</small><strong>{revoked ? '已撤回' : selected.active === true ? '可查询（合成）' : '无撤回记录（查询时再检查）'}</strong></div><p className="digest">内容摘要 {selected.package_sha256}</p></div>}
        {selected?.revocations?.map((item, index) => <p className="error" key={index}>撤回：{item.reason} · {item.actor} · {item.created_at}</p>)}
      </section>
      <section className="panel"><h2>三维人视图</h2><p>读取时检查撤回；展示的是固定快照，后续撤回需刷新获知。每次空间查询仍重新检查。</p><button disabled={!selected || busy || revoked} onClick={() => void loadHuman()}>{preview.isPending ? '加载中…' : '加载 / 刷新人视图'}</button>
        {preview.error && <p role="alert" className="error">{preview.error.message}；未展示空间内容。</p>}
        {human && <Suspense fallback={<p>加载三维组件…</p>}><SpatialView data={human} point={point?.point ?? null} /></Suspense>}
      </section>
      <section className="panel"><h2>点状态查询</h2><p>单位：米。所有查询均由服务端再次检查撤回状态。</p><form onSubmit={event => void submit(event)}><div className="coordinates">{['X', 'Y', 'Z'].map((axis, i) => <label key={axis}>{axis}<input type="number" required step="any" value={coords[i]} disabled={busy} onChange={e => { setCoords(coords.map((v, j) => j === i ? e.target.value : v)); setPoint(null); query.reset(); }} /></label>)}<button disabled={!selected || busy || revoked}>{query.isPending ? '查询中…' : '查询固定版本'}</button></div></form>
        {query.error && <p role="alert" className="error">{query.error.message}；没有返回空间状态。</p>}
        {point && <div className={`result ${point.state}`}><small>点 [{point.point.join(', ')}]</small><h3>{labels[point.state] ?? point.state}</h3><p>原因：{point.reason}</p><p>证据：{point.evidence_ids.join(', ') || '无已登记观测证据'}</p><small>发布：{point.release_id}</small></div>}
        {!point && !query.error && <div className="empty">{revoked ? '该发布已撤回，保留历史追溯，不能继续空间查询。' : selected ? '输入坐标，查询所选固定版本。' : '先读取一个发布，再开始查询。'}</div>}
      </section>
      <section className="panel" id="inspection"><h2>数据与语义核对</h2><p>资料与规则来自同一固定快照。加载时检查撤回；历史追溯仍通过上方发布入口读取。</p>
        <button disabled={!selected || busy || revoked} onClick={() => void loadInspection()}>{inspect.isPending ? '核对中…' : '加载 / 刷新资料与本体'}</button>
        {inspect.error && <p role="alert" className="error">{inspect.error.message}；未展示资料或规则结论。</p>}
        {inspection && <Inspection data={inspection.data} ontology={inspection.ontology} />}
        {!inspection && !inspect.error && <p className="empty">{revoked ? '该发布已撤回，不能加载资料与本体。' : '选择固定发布后，加载资料清单与本体规则。'}</p>}
      </section><Jobs key={scene} scene={scene} /><Delivery key={`${scene}:${release}`} scene={scene} release={release} /><footer>合成空间浏览与查询不代表实际通行、定位或安全结论。当前无工程写入操作。</footer>
    </main></div>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
