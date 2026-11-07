import React,{useEffect,useState} from 'react';
import {Button,StatusBadge} from '@vxture/design-system';
import {ArrowClockwise} from '@phosphor-icons/react';
import {businessEndpoint} from './business-endpoint';
import {recordLink,useRecordNavigation} from './record-navigation';
import {realScreenHref} from './real-space-data';
import {SpaceWorkflow} from './space-workflow';
import './scene-progress.css';

type Action={module:'space'|'build'|'data'|'delivery'|'ontology'|'association';label:string;values:Record<string,string>;allowed?:boolean};
type Release={publication_id:string;candidate_id:string|null;status:string;matches_current:boolean};
type Journey={target:{kind:string;id:string};current_step:string|null;steps:{id:string;title:string;status:string;detail:string;action:Action|null}[]};
type Summary={journey:Journey|null;work:{status:string;label:string;detail:string;action:Action}|null;candidate_ref:{candidate_id:string}|null;service_status:string;tracked_job:{job_id:string;state:string;is_current:boolean}|null;viewing_publication:Release|null;publications:Release[];available_publication_count:number;primary_action:Action;consumer_status:'unobserved'};
type Report={space_id:string;observed_at:string;summary:Summary};
export function SceneProgress({space,name,input,revision=0,onRead}:{space:string;name:string;input?:string;revision?:number;onRead?:(report:Report|null)=>void}){
 const target=useRecordNavigation();
 const [result,setResult]=useState<Report|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(true),[tick,setTick]=useState(0),[details,setDetails]=useState(false);
 const job=target.job,publication=target.publication,batch=input?target.batch:'';
 useEffect(()=>{const update=()=>setTick(v=>v+1);window.addEventListener('cospace:records-changed',update);window.addEventListener('cospace:session-confirmed',update);return()=>{window.removeEventListener('cospace:records-changed',update);window.removeEventListener('cospace:session-confirmed',update);};},[]);
 useEffect(()=>{const controller=new AbortController();setResult(null);setError('');setBusy(true);onRead?.(null);
  const query=new URLSearchParams({space_id:space,...(input?{input_id:input}:{}),...(batch?{batch_id:batch}:{}),...(job?{job_id:job}:{}),...(publication?{publication_id:publication}:{})});
  fetch(`${businessEndpoint}/api/workflow?${query}`,{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error(response.status===403?'当前场景或目标记录无访问权限。':response.status===409?'场景记录或版本引用已变化，请核查目标并刷新。':'场景进度暂不可用，请确认会话或网络后重试。');
   const report=await response.json();if(report.space_id!==space||!report.summary||report.summary.viewing_publication?.publication_id!==(publication||undefined)||(job&&report.summary.tracked_job?.job_id!==job))throw Error('场景进度响应与当前目标不一致，请刷新。');
   if(!controller.signal.aborted){setResult(report);onRead?.(report);}
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>controller.abort();
 },[space,input,batch,job,publication,tick,revision]);
 useEffect(()=>setDetails(false),[space]);
 const summary=result?.summary,viewing=summary?.viewing_publication;
 const action=summary?.primary_action,external=action?.module==='space'&&!!action.values.publication;
 const values=action?{...action.values}:{};
 const href=action?(external?realScreenHref(space,action.values.publication):recordLink(action.module,values)):'';
 return <section className="scene-progress" aria-label="场景进度摘要" data-space={space} data-service-status={summary?.service_status}>
  <div className="scene-progress-main"><div className="scene-progress-copy">
   <div className="scene-progress-heading"><span>{viewing?'当前查看发布':'场景进度'}</span>{summary&&<StatusBadge tone={viewing?.status==='paused'?'warning':viewing?.status==='unavailable'||summary.work?.status==='needs_attention'?'warning':summary.service_status==='complete'?'success':'neutral'}>{viewing?(viewing.status==='available'?'分发中':viewing.status==='paused'?'暂停分发':'成果不可读'):summary.work?.label||'固定发布概况'}</StatusBadge>}</div>
   {busy&&<p role="status">正在读取场景进度…</p>}{error&&<p role="alert">{error}</p>}
   {summary&&<><p className="scene-progress-reference">{viewing?`版本：${viewing.publication_id}`:summary.journey?.target.kind==='input'?`跟进资料：${summary.journey.target.id}`:summary.tracked_job?`跟进任务：${summary.tracked_job.job_id}`:summary.candidate_ref?`工作候选：${summary.candidate_ref.candidate_id}`:summary.work?'尚未选择工作候选':'按当前授权查看固定发布'}</p>
    {viewing?<p>{viewing.matches_current?'对应当前工作候选。':'历史候选发布；保持此版本查看。'}{summary.work?`${summary.tracked_job&&!summary.tracked_job.is_current?'跟进任务':'当前工作'}：${summary.work.label}。`:''}</p>:summary.work&&<p>{summary.work.detail}</p>}
    <p className="scene-progress-meta">可用固定发布 {summary.available_publication_count} 个 · 消费端未观测 · 质量待验收<span>读取于 {new Date(result!.observed_at).toLocaleTimeString('zh-CN',{hour12:false})}</span></p>
   </>}
  </div><div className="scene-progress-actions">
   {action&&action.allowed!==false&&<Button asChild size="sm"><a href={href} {...(external?{target:'_blank',rel:'noopener noreferrer'}:{})}>{action.label}</a></Button>}
   <Button variant="ghost" size="sm" aria-label="刷新场景进度" disabled={busy} onClick={()=>setTick(v=>v+1)}><ArrowClockwise size={15}/></Button>
   {error&&<Button variant="outline" size="sm" onClick={()=>{window.dispatchEvent(new Event('cospace:confirm-session'));setTick(v=>v+1);}}>确认会话并重试</Button>}
   {summary?.work&&<Button variant="ghost" size="sm" aria-expanded={details} onClick={()=>setDetails(v=>!v)}>{details?'收起流程明细':'流程明细'}</Button>}
  </div></div>
  {summary?.journey&&<div className="scene-journey"><p>本次流程 · {{scene:'场景',input:'资料',job:'任务',candidate:'候选',publication:'固定发布'}[summary.journey.target.kind]||'目标'}：{summary.journey.target.id}</p><ol aria-label="业务流程进度">{summary.journey.steps.map((step,index)=><li key={step.id} data-status={step.status} aria-current={summary.journey?.current_step===step.id?'step':undefined}><strong>{index+1}. {step.title}</strong><span>{{complete:'已具备',pending:'待完成',in_progress:'进行中',needs_attention:'需处理',unknown:'未核验'}[step.status]||'未知'}</span><p>{step.detail}</p>{step.action&&step.action.allowed!==false&&<a href={recordLink(step.action.module,step.action.values)}>{step.action.label}</a>}</li>)}</ol><small>语义本体、空间关联按业务需要增强；消费端启用与现场质量需另行验收。</small></div>}
  {details&&<div className="scene-progress-details"><SpaceWorkflow space={space} name={name} input={input} onClose={()=>setDetails(false)}/></div>}
 </section>;
}
