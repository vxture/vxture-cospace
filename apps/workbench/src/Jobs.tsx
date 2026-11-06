import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
type Spec = { scene_id: string; dataset_id: string; dataset_sha256: string; executor: string;
  config: { timeout_seconds: number; log_limit_bytes: number }; environment: Record<string, unknown> };
type Job = { scene_id?: string; job_id: string; state: string; revision: number; requested_at: string; sha256: string; spec: Spec; actor: string;
  attempts: { attempt_id: string; state: string; started_at: string; finished_at: string | null; diagnostic: {stage: string; code: string; message: string} | null }[];
  events: {event_id: string; state: string; created_at: string}[] };
type Page = {scene_id: string; items: Job[]; offset: number; has_more: boolean};
type Input = {scene_id: string; job_id: string; spec_sha256: string; dataset_sha256: string;
  manifest: {dataset_id: string; scene_id: string; verified_at: string; members: {path: string; role: string; bytes: number; sha256: string}[]}};
type Report = {scene_id: string; job_id: string; spec_sha256: string; report: {job_id: string; dataset_sha256: string;
  candidate_created: boolean; truth_created: boolean; not_executed: string[]; validation: {passed: boolean; truth_version_id: string}};
  artifact: {artifact_id: string; sealed_at: string; files: {path: string; bytes: number; sha256: string}[]}};
const states: Record<string, string> = {queued: '排队', running: '执行中', succeeded: '检查完成', failed: '失败', cancelled: '已取消'};
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false}) : '未记录';
async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, {cache: 'no-store'}), value = await response.json();
  if (!response.ok) throw new Error(`${response.status} · ${value.detail?.message ?? '读取失败'}`);
  return value as T;
}
export default function Jobs({scene}: {scene: string}) {
  const [page, setPage] = useState<Page | null>(null), [job, setJob] = useState<Job | null>(null);
  const [input, setInput] = useState<Input | null>(null), [report, setReport] = useState<Report | null>(null);
  const [id, setId] = useState('');
  const base = `/scenes/${encodeURIComponent(scene)}/jobs`;
  const list = useMutation({mutationFn: async (offset: number) => {
    const value = await get<Page>(`${base}?limit=10&offset=${offset}`);
    if (value.scene_id !== scene || value.items.some(item => item.spec.scene_id !== scene)) throw new Error('列表场景不一致');
    return value;
  }});
  const detail = useMutation({mutationFn: async (identity: string) => {
    const value = await get<Job>(`${base}/${encodeURIComponent(identity)}`);
    if (value.scene_id !== scene || value.spec.scene_id !== scene || value.job_id !== identity) throw new Error('任务身份不一致');
    return value;
  }});
  const contents = useMutation({mutationFn: async (selected: Job) => {
    const value = await get<Input>(`${base}/${encodeURIComponent(selected.job_id)}/input`);
    if (value.scene_id !== scene || value.job_id !== selected.job_id || value.spec_sha256 !== selected.sha256 ||
      value.dataset_sha256 !== selected.spec.dataset_sha256 || value.manifest.dataset_id !== selected.spec.dataset_id || value.manifest.scene_id !== scene) throw new Error('固定输入不一致');
    return value;
  }});
  const result = useMutation({mutationFn: async (selected: Job) => {
    const value = await get<Report>(`${base}/${encodeURIComponent(selected.job_id)}/report`);
    if (value.scene_id !== scene || value.job_id !== selected.job_id || value.spec_sha256 !== selected.sha256 ||
      value.report.job_id !== selected.job_id || value.report.dataset_sha256 !== selected.spec.dataset_sha256 ||
      value.report.candidate_created !== false || value.report.truth_created !== false) throw new Error('报告上下文不一致');
    return value;
  }});
  const busy = list.isPending || detail.isPending || contents.isPending || result.isPending;
  function clear() {setJob(null); setInput(null); setReport(null); detail.reset(); contents.reset(); result.reset();}
  async function loadPage(offset: number) {setPage(null); clear(); try {setPage(await list.mutateAsync(offset));} catch { /* explicit error */ }}
  async function load(identity: string) {clear(); setId(identity); try {setJob(await detail.mutateAsync(identity));} catch { /* no stale content */ }}
  return <section className="panel" id="jobs"><h2>构建与校核 · 检查任务</h2><p>场景：{scene}。任务独立于服务发布，只读核对。检查完成不表示真值已采用。时间：北京时间。</p>
    <button disabled={busy || !scene} onClick={() => void loadPage(0)}>刷新任务列表</button>
    {list.error && <p role="alert" className="error">{list.error.message}；没有可展示的列表。</p>}
    {page && <><div className="table-scroll"><table className="objects"><thead><tr><th>任务 / 输入</th><th>状态</th><th>提交时间</th><th>操作</th></tr></thead><tbody>{page.items.map(item =>
      <tr key={item.job_id}><td>{item.job_id}<small>{item.spec.dataset_id}</small></td><td>{states[item.state] ?? item.state}</td><td>{time(item.requested_at)}</td><td><button disabled={busy} className="secondary" onClick={() => void load(item.job_id)}>查看任务</button></td></tr>)}</tbody></table></div>
      {!page.items.length && <p>该场景暂无任务。</p>}<div className="actions"><button disabled={busy || !page.offset} onClick={() => void loadPage(Math.max(0, page.offset - 10))}>上一页</button><button disabled={busy || !page.has_more || page.offset >= 10000} onClick={() => void loadPage(page.offset + 10)}>下一页</button></div><p>从第{page.offset + 1}条开始；列表为读取时状态，新增任务可能改变分页。</p></>}
    <form className="actions" onSubmit={event => {event.preventDefault(); void load(id);}}><label>任务 ID<input value={id} disabled={busy} onChange={event => {setId(event.target.value); clear();}} /></label><button disabled={busy || !id}>读取任务详情</button></form>
    {detail.error && <p role="alert" className="error">{detail.error.message}；已清除旧任务内容。</p>}
    {job && <><div className="summary"><div><small>固定任务</small><strong>{job.job_id}</strong></div><div><small>状态 / 修订</small><strong>{states[job.state] ?? job.state} / {job.revision}</strong></div><div><small>执行器</small><strong>{job.spec.executor}</strong></div><div><small>操作者声明（未认证）</small><strong>{job.actor}</strong></div><p className="digest">规格摘要 {job.sha256}<br />输入 {job.spec.dataset_id}<br />输入摘要 {job.spec.dataset_sha256}</p></div>
      <p>限额：{job.spec.config.timeout_seconds}秒 / 日志{job.spec.config.log_limit_bytes}字节。</p><details><summary>固定运行环境</summary><pre className="job-json">{JSON.stringify(job.spec.environment, null, 2)}</pre></details>
      <h3>执行与诊断</h3>{!job.attempts.length && <p>尚无执行记录。</p>}{job.attempts.map(attempt => <div className="notice" key={attempt.attempt_id}><strong>{attempt.attempt_id} · {states[attempt.state] ?? attempt.state}</strong><p>开始 {time(attempt.started_at)}<br />结束 {time(attempt.finished_at)}</p>{attempt.diagnostic && <p role="alert">{attempt.diagnostic.stage} / {attempt.diagnostic.code}：{attempt.diagnostic.message}</p>}</div>)}
      <details><summary>状态事件</summary><ul>{job.events.map(event => <li key={event.event_id}>{time(event.created_at)} · {states[event.state] ?? event.state}</li>)}</ul></details>
      <div className="actions"><button disabled={busy} onClick={() => {setInput(null); void contents.mutateAsync(job).then(setInput).catch(() => {});}}>核对固定输入</button><button disabled={busy || job.state !== 'succeeded'} onClick={() => {setReport(null); void result.mutateAsync(job).then(setReport).catch(() => {});}}>读取检查报告</button></div>
      {contents.error && <p role="alert" className="error">{contents.error.message}；未展示输入。</p>}{input && <><h3>固定输入资料</h3><p>登记校验于{time(input.manifest.verified_at)}，现场质量未验证；本次复核封存摘要。</p><table className="objects"><thead><tr><th>资料 / 角色</th><th>字节 / SHA256</th></tr></thead><tbody>{input.manifest.members.map(item => <tr key={item.path}><td>{item.path}<small>{item.role}</small></td><td>{item.bytes}<small className="hash">{item.sha256}</small></td></tr>)}</tbody></table></>}
      {result.error && <p role="alert" className="error">{result.error.message}；未展示报告。</p>}{report && <div className="notice"><h3>合成输入检查报告</h3><p>规则校验：{report.report.validation.passed ? '通过' : '未通过'}；未生成候选，未生成新真值。</p><p>被检查输入真值版本：{report.report.validation.truth_version_id}<br />未执行：{report.report.not_executed.join('、')}</p><p>{report.artifact.artifact_id} · {time(report.artifact.sealed_at)}</p><ul>{report.artifact.files.map(file => <li className="digest" key={file.path}>{file.path} · {file.bytes}字节 · {file.sha256}</li>)}</ul></div>}
    </>}
  </section>;
}
