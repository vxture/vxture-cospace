import React,{useEffect,useRef,useState} from 'react';
import {Button,Input,StatusBadge} from '@vxture/design-system';
import {dataRequest} from './data-project-client';
import {parseProcessing,parseGovernance,validateGovernanceResult,type ProcessingReport,type GovernanceReport} from './data-processing-contract';
import {useUnsavedNavigation} from './unsaved-navigation';
import {useOperationConfirmation} from './operation-confirmation';

const kinds:Record<string,string>={input:'采集资料',job:'构建任务',candidate:'模型成果',human_view:'可视表达',agent_view:'计算表达',publication:'固定发布'};
const states:Record<string,string>={registered:'已登记',queued:'已排队',running:'运行中',succeeded:'执行成功',failed:'失败',interrupted:'已中断',views_failed:'视图待恢复',unknown:'状态待核查',metadata_matched:'元数据已匹配',declared:'已声明表达',fixed_record:'已保存发布记录'};
const relations:Record<string,string>={consumes:'使用资料',produced_by:'产出自',expresses:'表达自',derived_from:'派生自',published_from:'发布自',output_unresolved:'产出未能核对'};
export function DataProcessingPanel({workspace,resource}:Readonly<{workspace:string;resource:string}>){
 const [report,setReport]=useState<ProcessingReport|null>(null),[error,setError]=useState(''),[generation,setGeneration]=useState(0),[limit,setLimit]=useState(20);
 useEffect(()=>{const c=new AbortController();setReport(null);setError('');
  void dataRequest('/api/data-processing?'+new URLSearchParams({resource_id:resource}),c.signal).then(v=>parseProcessing(v,workspace,resource)).then(v=>{if(!c.signal.aborted)setReport(v);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();
 },[workspace,resource,generation]);
 const nodes=new Map(report?.nodes.map(n=>[n.key,n]));
 return <section className="data-lineage-panel" aria-label="处理血缘"><div className="data-lineage-heading"><h3>处理血缘</h3><Button size="sm" variant="outline" onClick={()=>setGeneration(v=>v+1)}>刷新</Button></div>
 {error&&<p role="alert">{error}</p>}{!report&&!error&&<output>正在核对处理记录…</output>}{report?.status==='not_applicable'&&<p className="data-resource-secondary">尚未记录构建消费关系。资料登记和共享引用不代表已用于构建。</p>}
 {report?.status==='partial'&&<p role="alert">部分来源、绑定或处理记录缺失，未能完整核对处理链。请在来源工作面核查。</p>}
 {report&&report.status!=='not_applicable'&&<><ol className="data-processing-nodes">{report.nodes.slice(0,limit).map(node=><li key={node.key} className="data-lineage-version" aria-current={node.key===report.focus?'true':undefined}><div className="data-sharing-record"><strong>{kinds[node.kind]}</strong><StatusBadge tone="neutral">{states[node.state]}</StatusBadge>{node.key===report.focus&&<span className="data-resource-secondary">当前数据</span>}</div><code>{node.record_id}</code>{report.edges.filter(e=>e.from===node.key).map(edge=><p className="data-resource-secondary" key={edge.relation}>{relations[edge.relation]}{edge.to?` · ${kinds[nodes.get(edge.to)!.kind]} ${nodes.get(edge.to)!.record_id}`:''}{edge.status==='unresolved'?' · 未能核对':''}</p>)}</li>)}</ol>{report.nodes.length>limit&&<div className="data-lineage-heading"><span className="data-resource-secondary">已显示 {limit} / {report.nodes.length} 个节点</span><Button size="sm" variant="outline" onClick={()=>setLimit(v=>v+20)}>显示更多</Button></div>}<p className="data-resource-secondary">依据已保存元数据核对，不重新读取模型载荷。离线导出能力不计为已生成的交付成果。</p></>}
 </section>;
}

export function DataGovernancePanel({workspace,resource,label,onChanged}:Readonly<{workspace:string;resource:string;label:string;onChanged:()=>void}>){
 const [report,setReport]=useState<GovernanceReport|null>(null),[error,setError]=useState(''),[generation,setGeneration]=useState(0),[reason,setReason]=useState(''),[action,setAction]=useState<'archive'|'restore'|null>(null),[busy,setBusy]=useState(false);
 const gate=useRef(false),pending=useRef<{key:string;body:Record<string,unknown>}|null>(null),request=useRef<AbortController|null>(null);
 useUnsavedNavigation(!!reason||busy,'资料归档');useEffect(()=>()=>request.current?.abort(),[]);
 useEffect(()=>{const c=new AbortController();setReport(null);setError('');setAction(null);setReason('');
  void dataRequest('/api/data-governance?'+new URLSearchParams({resource_id:resource}),c.signal).then(v=>parseGovernance(v,workspace,resource)).then(v=>{if(!c.signal.aborted)setReport(v);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();
 },[workspace,resource,generation]);
 const confirm=useOperationConfirmation(JSON.stringify([workspace,resource,report?.snapshot,action,reason]));
 async function commit(){
  if(!report||!action||!reason.trim()||gate.current){return;}
  gate.current=true;setBusy(true);setError('');const fields={resource_id:resource,action,reason:reason.trim(),expected_revision:report.revision,expected_snapshot:report.snapshot},key=JSON.stringify(fields),body=pending.current?.key===key?pending.current.body:{...fields,request_id:crypto.randomUUID().replaceAll('-','')};pending.current={key,body};const c=new AbortController();request.current=c;
  try{const value=await dataRequest('/api/data-governance',c.signal,body);validateGovernanceResult(value,resource,action,report.revision);if(!c.signal.aborted){setReason('');setAction(null);onChanged();}}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'归档操作失败。');throw e;}finally{gate.current=false;if(!c.signal.aborted)setBusy(false);}
 }
 function submit(){if(!report||!action){return;}return confirm({verb:action==='archive'?'归档资料':'恢复资料',target:label,consequence:action==='archive'?'停止新共享、引用、版本追加和登记维护，原件与历史保留。':'重新允许新用途，不自动共享或关联。',preconditions:[{label:'全工作区引用与共享已核对',met:!!report.actions.find(a=>a.action===action)?.allowed},{label:'已填写原因',met:!!reason.trim()}]},commit);}
 const actionLabel=action==='archive'?'归档':'恢复';
 const submitLabel=busy?'提交中…':'核对'+actionLabel;
 return <section className="data-lineage-panel" aria-label="资料归档"><div className="data-lineage-heading"><h3>资料归档</h3>{report&&<StatusBadge tone="neutral">{report.state==='archived'?'已归档':'可用'}</StatusBadge>}<Button size="sm" variant="outline" disabled={busy||!!reason} onClick={()=>setGeneration(v=>v+1)}>刷新</Button></div>{error&&<p role="alert">{error}</p>}{!report&&!error&&<output>正在检查引用与共享…</output>}{report&&<><p className="data-resource-secondary">全工作区影响检查：{report.impact.has_linked_references?'存在关联引用':'无待解除引用'} · {report.impact.has_active_grants?'存在有效共享':'无有效共享'}</p>{report.state==='active'&&(report.impact.has_linked_references||report.impact.has_active_grants)&&<p>请先解除引用并撤销有效共享，再归档资料。</p>}{report.last_change&&<p className="data-resource-secondary">{new Date(report.last_change.updated_at).toLocaleString('zh-CN')} · {report.last_change.reason}</p>}{!action?<div className="data-lineage-heading">{report.actions.filter(a=>a.action===(report.state==='active'?'archive':'restore')).map(a=><Button key={a.action} size="sm" variant="outline" disabled={!a.allowed} onClick={()=>setAction(a.action)}>{a.action==='archive'?'归档资料':'恢复资料'}</Button>)}</div>:<><label>操作原因<Input value={reason} disabled={busy} maxLength={500} onChange={e=>setReason(e.target.value)}/></label><div className="data-drawer-footer"><Button variant="outline" disabled={busy} onClick={()=>{setAction(null);setReason('');}}>取消</Button><Button disabled={busy||!reason.trim()} onClick={()=>void submit()}>{submitLabel}</Button></div></>}<p className="data-resource-secondary">归档可恢复，保留原件、版本和审计，不释放存储。</p></>}</section>;
}
