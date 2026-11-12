import {WorkflowNavigationToggle} from './workflow-navigation';
import {SpaceSettings} from './space-settings';
import {runGuarded} from './unsaved-navigation';
import {appNavigate} from './app-router';
import React,{useEffect,useState} from 'react';
import {Button,Badge,StatusBadge,Drawer,Textarea,Select,SelectTrigger,SelectValue,SelectContent,SelectItem,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '@vxture/design-system';
import {ArrowClockwise,ArrowUpRight,Database,Cube,Eye,Robot,ArrowRight,Plus,ClockCounterClockwise,Sparkle,UploadSimple,Broadcast,Desktop,CheckCircle,SidebarSimple,FileArrowUp,X,ArrowsOutSimple,ArrowsInSimple,Clock,WarningCircle,Circle,SpinnerGap,Layout,Cpu,MapPin,ListChecks} from '@phosphor-icons/react';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink,useRecordNavigation} from './record-navigation';
import {inputFormat} from './input-format';
import {CandidateReview} from './candidate-review';
import {realScreenHref} from './real-space-data';
import {BuildRecovery,RecoverableJob} from './build-recovery';
import {BuildStages,ViewDerivations} from './view-derivations';
import {buildScanHref} from './build-scan-data';
import {BuildJobs} from './build-jobs';
import {PreflightHistory} from './preflight-history';
import {BuildContext,BuildInfo,BuildSceneLink} from './build-context';
import {BuildMaterials} from './build-materials';
import {InputRegistration} from './input-registration';
import './construction-flow.css';

type Input={cloud_sha256?:string;snapshot_sha256?:string;tracking_sha256?:string;registered_at?:string;registered_at_estimated?:boolean;id:string;space_id:string;label:string;format:string;input_frames:number;used_frames:number;verified_image_members?:number;verified_messages?:number;lifecycle_state?:string};
type Job=RecoverableJob&{display_code?:string;build_code?:string;demo_timeline?:{estimated:boolean;basis:string;stages:{start:string;end:string;estimated:boolean}[]};build_info?:BuildInfo;build_info_revision?:number;created_at:string;started_at?:string;finished_at?:string;candidate_url:string|null;pipeline?:string;view_parent_id?:string;stage?:string;input_binding?:{label:string}};
type Model={id:string;space_id:string;profile:string;frame_id:string;unit:string;axes:string[];bounds_m:number[][];data_kind:string;construction:{model_points:number;used_frames:number;input_frames:number};source:{input_binding?:{id:string}};human_view:{path:string;source_model_sha256:string};agent_view:{path:string;source_model_sha256:string;resolution_m:number;surface_cells:number;unlisted_state:string};members:Record<string,{bytes:number;sha256:string}>};
type Release={id:string;candidate_id:string;source_model_sha256:string;lifecycle_state?:string;selection_review?:{reviewed_at?:string}};
type Snapshot={inputs:Input[];jobs:Job[];job?:Job;model?:Model;stages?:BuildStages;modelIssue?:string;selection:{candidate_id:string|null;revision:number;selected_at?:string;selection_review?:{reviewed_at?:string}};releases:Release[]};
const buildVersion=(job:Job)=>job.display_code||job.build_code||`历史记录 · ${job.id.slice(-8).toUpperCase()}`;
const elapsed=(start?:string,end?:string)=>{if(!start||!end)return '待记录';const ms=Date.parse(end)-Date.parse(start);if(!Number.isFinite(ms)||ms<0)return '待记录';const minutes=Math.floor(ms/60000);if(ms>0&&minutes===0)return '不足1分钟';return `${Math.floor(minutes/60)}小时${minutes%60}分钟`;};
const shortTime=(value?:string)=>value?new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'待开始';
const bytes=(value:number)=>value>=1024*1024?`${(value/1024/1024).toFixed(2)} MB`:`${(value/1024).toFixed(1)} KB`;

/** Explain actual saved artifacts; reading this page never starts, selects or publishes a build. */
export function ConstructionFlow({active=true}:{active?:boolean}={}){
 const target=useRecordNavigation();
 const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(true),[revision,setRevision]=useState(0);
 const [step,setStep]=useState('model'),[assistantOpen,setAssistantOpen]=useState(()=>innerWidth>=1200),[assistantWide,setAssistantWide]=useState(false),[restart,setRestart]=useState(false),[historyOpen,setHistoryOpen]=useState(()=>innerWidth>=1100);
 const draft=target.tab==='tasks';
 const [buildInfo,setBuildInfo]=useState<BuildInfo>({name:'',purpose:'',changes:''});
 useEffect(()=>{setBuildInfo({name:'',purpose:'',changes:''});},[target.space,target.tab,target.job]);
 useEffect(()=>{const toggle=()=>setAssistantOpen(v=>!v);window.addEventListener('cospace-build-assistant-toggle',toggle);return()=>window.removeEventListener('cospace-build-assistant-toggle',toggle);},[]);
 useEffect(()=>{window.dispatchEvent(new CustomEvent('cospace-build-assistant-state',{detail:assistantOpen}));return()=>{window.dispatchEvent(new CustomEvent('cospace-build-assistant-state',{detail:false}));};},[assistantOpen]);
 useEffect(()=>{setStep(draft?'prepare':target.tab==='candidate'?'review':'model');},[target.job,target.space,target.tab,draft]);
 const [preflightOpen,setPreflightOpen]=useState(false);
 const [review,setReview]=useState<{candidate:string;revision:number}|null>(null);
 useEffect(()=>{setReview(null);setPreflightOpen(false);setData(null);},[target.space,target.input,target.job,active]);
 useEffect(()=>{const refresh=()=>setRevision(n=>n+1);window.addEventListener('cospace-selection-changed',refresh);window.addEventListener('focus',refresh);return()=>{window.removeEventListener('cospace-selection-changed',refresh);window.removeEventListener('focus',refresh);};},[]);
 useEffect(()=>{if(!active)return;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;setBusy(true);setError('');
  const read=async(path:string)=>{const r=await fetch(`${endpoint}${path}`,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error(r.status===403?'当前场景或记录没有访问权限。':'构建流程暂时无法读取，请刷新重试。');return r.json();};
  const query='?'+new URLSearchParams({space_id:target.space});
  (async()=>{
   const [inputResult,jobResult,selection,releaseResult]=await Promise.all([read('/api/inputs'+query),read('/api/builds'+query),read('/api/selection'+query),read('/api/publications'+query)]);
   const inputs:Input[]=inputResult.inputs,jobs:Job[]=jobResult.jobs;
   if(!Array.isArray(inputs)||!Array.isArray(jobs)||!Array.isArray(releaseResult.publications)||inputs.some(i=>i.space_id!==target.space)||jobs.some(j=>j.space_id!==target.space))throw Error('记录与当前场景不一致。');
   if(target.input&&!inputs.some(i=>i.id===target.input))throw Error('指定资料不属于当前场景或已不可读。');
   const scoped=jobs.filter(j=>!target.input||j.input_id===target.input).sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at)||b.id.localeCompare(a.id));
   const job=target.tab==='tasks'?undefined:target.job?scoped.find(j=>j.id===target.job):scoped[0];
   if(target.tab!=='tasks'&&target.job&&!job)throw Error('指定构建任务不属于当前场景或资料；请重新选择。');
   let model:Model|undefined,modelIssue:string|undefined,stages:BuildStages|undefined;
   if(job?.pipeline){stages=await read('/api/build-stages?'+new URLSearchParams({space_id:target.space,candidate_id:job.id}));if(stages!.space_id!==target.space||stages!.job_id!==job.id)throw Error('阶段记录与当前任务不一致。');}
   if(job?.state==='succeeded'){
    try{
    const response=await fetch(`${endpoint}/candidates/${encodeURIComponent(job.id)}/api/preview`,{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error(response.status===403?'成果当前无访问权限。':response.status>=500?'成果服务暂时不可读，请刷新核查。':'成果不可用或校验未通过，请核查产物。');
    model=await response.json();
    if(!model||model.id!==job.id||model.space_id!==target.space||model.profile!=='cospace.real-model-preview/0.1')throw Error('模型与当前任务绑定不一致。');
    const canonical=model.members?.['spatial.npz']?.sha256;
    if(!canonical||!model.members?.[model.human_view?.path]||!model.members?.[model.agent_view?.path]||model.human_view.source_model_sha256!==canonical||model.agent_view.source_model_sha256!==canonical||model.source?.input_binding?.id!==job.input_id)throw Error('模型来源或双视图绑定不一致，请核查产物。');
    }catch(e){if(controller.signal.aborted)return;model=undefined;modelIssue=e instanceof Error?e.message:'成果读取失败，请刷新核查。';}
   }
   if(controller.signal.aborted)return;
   setData({inputs,jobs,job,model,stages,modelIssue,selection,releases:releaseResult.publications});
   if(job&&['queued','running'].includes(job.state))timer=setTimeout(()=>setRevision(n=>n+1),3000);
  })().catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>{controller.abort();clearTimeout(timer);};
 },[target.space,target.input,target.job,target.tab,active,revision]);
 const job=data?.job,model=data?.model,stages=data?.stages,input=data?.inputs.find(i=>i.id===(job?.input_id||target.input));
 const release=model&&data?.releases.find(r=>r.candidate_id===model.id&&r.source_model_sha256===model.members['spatial.npz'].sha256&&(!r.lifecycle_state||r.lifecycle_state==='active'));
 const selected=!!model&&data?.selection.candidate_id===model.id;
 const reviewTime=(selected?data?.selection.selection_review?.reviewed_at:undefined)||data?.releases.find(r=>r.candidate_id===job?.id&&r.selection_review?.reviewed_at)?.selection_review?.reviewed_at;
 const [clockNow,setClockNow]=useState(()=>new Date().toISOString());
 useEffect(()=>{const timer=setInterval(()=>setClockNow(new Date().toISOString()),30000);return()=>clearInterval(timer);},[]);
 const state=data?.modelIssue?'成果待核查':job?.state==='succeeded'?'候选已就绪':job?.state==='views_failed'?'视图待恢复':job?.state==='failed'?'构建失败':job?.state==='interrupted'?'构建中断':job?.state==='queued'?'排队中':job?.stage==='deriving_views'?'模型已冻结 · 表达派生中':job?'构建中':input?'待构建':'待资料';
 const currentInput=input?.label||job?.input_binding?.label||'选择本次资料';
 const jobTitle=job?`${new Date(job.created_at).toLocaleDateString('zh-CN')} · ${currentInput}`:'新建构建';
 const newBuild=()=>appNavigate(recordLink('build',{tab:'tasks'}));
 const history=[...(data?.jobs||[])].sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at));
 const labels:Record<string,string>={queued:'排队中',running:'构建中',succeeded:'已完成',failed:'失败',interrupted:'中断',views_failed:'视图待恢复'};
 const publicationStatus=(id:string)=>{const releases=data?.releases.filter(r=>r.candidate_id===id)||[];return releases.some(r=>!r.lifecycle_state||r.lifecycle_state==='active')?'已发布':releases.some(r=>r.lifecycle_state==='paused')?'发布已暂停':releases.length?'发布已退役':'未发布';};
 const modelReady=!!(model||stages?.frozen_model);
 const failed=!!job&&['failed','interrupted','views_failed'].includes(job.state);
 const running=!!job&&['queued','running'].includes(job.state);
 const steps=[{id:'prepare',title:'资料准备',icon:Database,status:input||job?'已登记':'待准备',tone:input||job?'success':'neutral',mark:input||job?CheckCircle:Circle},
  {id:'check',title:'检查整理',icon:ListChecks,status:modelReady?'已通过':job?'待核查':'待检查',tone:modelReady?'success':'neutral',mark:modelReady?CheckCircle:Circle},
  {id:'model',title:'模型构建',icon:Cpu,status:data?.modelIssue?'待核查':job?.state==='succeeded'?'已完成':failed?'异常':running?(job.state==='queued'?'排队中':'进行中'):'待构建',tone:data?.modelIssue||failed?'danger':job?.state==='succeeded'?'success':running?'info':'neutral',mark:data?.modelIssue||failed?WarningCircle:job?.state==='succeeded'?CheckCircle:running?SpinnerGap:Circle},
  {id:'review',title:'成果核对',icon:Eye,status:selected?'已核对':model?'待核对':'待生成',tone:selected?'success':model?'warning':'neutral',mark:selected?CheckCircle:model?Clock:Circle}];
 // Legacy demo selection timestamps approximate confirmation; never present them as recorded reviews.
 const confirmedAt=reviewTime||(selected?data?.selection.selected_at:undefined);
 const totalStart=job?.demo_timeline?.stages[0]?.start||input?.registered_at||job?.created_at;
 const reviewEstimated=!!confirmedAt&&!reviewTime;
 const boundaries=[input?.registered_at,job?.created_at,job?.started_at,job?.finished_at,confirmedAt];
 const stageTimes=job?.demo_timeline?.stages||steps.map((s,i)=>({start:boundaries[i],end:boundaries[i+1]||((i===2&&running)||(i===3&&model&&!selected)?clockNow:undefined),estimated:i===0?!!input?.registered_at_estimated:i===1?true:i===3?reviewEstimated:false}));
 const flowDone=!!(confirmedAt||job?.demo_timeline?.stages[3]?.end);
 const totalEnd=job?.demo_timeline?.stages[3]?.end||confirmedAt||(failed?job?.finished_at:job?clockNow:undefined);
 const totalEstimated=!!job?.demo_timeline?.estimated||!!input?.registered_at_estimated||reviewEstimated;
 const stepNavigation=<nav className="build-step-nav" aria-label="构建环节">{steps.map((s,i)=>{const timing=stageTimes[i];return <div className="build-step-entry" key={s.id}><Button variant={step===s.id?'secondary':'ghost'} aria-current={step===s.id?'step':undefined} onClick={()=>void runGuarded(()=>{setStep(s.id);if(innerWidth<1100)setHistoryOpen(false);})}><s.icon size={16}/><strong>{String(i+1).padStart(2,'0')} {s.title}</strong><span className={`build-step-state build-step-state-${s.tone}`}><s.mark size={12}/>{s.status}</span></Button><dl className="build-step-timing"><div><dt>开始时间：</dt><dd>{shortTime(timing.start)}{timing.estimated&&<small title={job?.demo_timeline?.basis}>估算</small>}</dd></div><div><dt>完成时间：</dt><dd>{timing.end?shortTime(timing.end):'待完成'}</dd></div><div><dt>总计耗时：</dt><dd title={timing.start&&timing.end?`${Math.max(0,(Date.parse(timing.end)-Date.parse(timing.start))/1000).toFixed(1)} 秒${timing.estimated?'；依据登记、提交或选定时间估算':''}`:undefined}>{elapsed(timing.start,timing.end)}{timing.estimated&&timing.start&&timing.end&&<small>估算</small>}</dd></div></dl></div>;})}</nav>;
 const materialPreparation=<BuildMaterials endpoint={endpoint} space={target.space} items={data?.inputs||[]} selectedId={job?.input_id||target.input} locked={!!job} onRegistered={id=>{setRevision(n=>n+1);if(draft)appNavigate(recordLink('build',{tab:'tasks',input:id}));}} onNext={()=>setStep('check')}/>;
 return <section className={`construction-flow build-desk ${historyOpen?'':'build-history-hidden'}`} aria-label="构建工作操作台">
  <aside className="build-history workflow-nav-panel" aria-label="构建导航与记录" id="build-navigation-panel">
   <div className="build-nav-heading workflow-nav-heading"><Layout size={18}/><h2>构建中心</h2><Badge variant="outline" className="build-nav-count" aria-label={`${history.length} 次构建`}>{history.length}</Badge><WorkflowNavigationToggle open={true} label="构建" panelId="build-navigation-panel" onToggle={()=>setHistoryOpen(false)}/></div>
   <section className="build-nav-section build-records-section" aria-label="构建版本与流程">
    <BuildSceneLink selected={step==='info'} onSelect={()=>void runGuarded(()=>setStep('info'))}/>
    <Select value={draft?'draft':job?.id||'draft'} disabled={busy&&!data} onValueChange={id=>{if(id==='draft'){newBuild();return;}const picked=history.find(j=>j.id===id);if(picked)appNavigate(recordLink('build',{tab:'flow',job:picked.id,...(picked.input_id?{input:picked.input_id}:{})}));}}><SelectTrigger aria-label="选择构建版本" className="build-version-select"><SelectValue placeholder="选择构建版本"><span className="build-version-current"><strong>{draft||!job?'本次新建构建':buildVersion(job)}</strong><span><time>{job?shortTime(job.created_at):'尚未提交'}</time><span>{job?labels[job.state]||job.state:'待准备'}</span></span></span></SelectValue></SelectTrigger><SelectContent className="build-version-menu"><SelectItem value="draft"><span className="build-version-option"><strong>本次新建构建</strong><span>未提交 · 未发布</span></span></SelectItem>{history.map(j=><SelectItem key={j.id} value={j.id} textValue={buildVersion(j)}><span className="build-version-option"><strong>{buildVersion(j)}</strong><span><time dateTime={j.created_at}>{new Date(j.created_at).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}</time><span>{labels[j.state]||j.state} · {publicationStatus(j.id)}</span></span></span></SelectItem>)}</SelectContent></Select>
    <article className="build-record-group build-record-active">{stepNavigation}</article>
    <section className="build-flow-stat" aria-label="流程统计"><header><strong>全程耗时</strong><StatusBadge tone={failed?'danger':flowDone?'success':job?'info':'neutral'}>{failed?'异常':flowDone?'已完成':job?'进行中':'未开始'}</StatusBadge></header><p title="从资料准备到成果核对完成，包含人工等待时间">{elapsed(totalStart,totalEnd)}</p><span>包含人工确认{totalEstimated?' · 估算':''}</span></section>
   </section>

  </aside>
  {!historyOpen&&<WorkflowNavigationToggle open={false} label="构建" panelId="build-navigation-panel" onToggle={()=>setHistoryOpen(true)}/>}
  <div className="build-work">
   <div className="build-work-scroll" tabIndex={0} aria-label="构建内容">
   <header className="build-work-header"><div className="build-title-block"><Cube size={32} className="build-title-icon"/><div className="build-title-copy"><div className="build-title-line"><h2>{job?(job.build_info?.name||currentInput):'新建构建'}</h2><StatusBadge tone={model?'success':job?.state==='failed'?'danger':'info'}>{draft?'待准备':state}</StatusBadge></div><div className="build-work-meta">{job?<><span title={job.id}>{buildVersion(job)}</span><time dateTime={job.created_at}>{new Date(job.created_at).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}</time></>:null}<BuildContext endpoint={endpoint} space={target.space} draft={draft} value={draft?buildInfo:job?.build_info||{name:'',purpose:'',changes:''}} onChange={setBuildInfo} jobId={job?.id} revision={job?.build_info_revision||0} onSaved={()=>setRevision(n=>n+1)}/></div></div></div><div className="build-header-actions">{job&&<Button asChild variant="secondary" size="sm"><a href={buildScanHref(target.space,job.id,job.input_id||'')} target="_blank" rel="noopener noreferrer"><Eye size={16}/>{model?'查看成果':'查看过程'}</a></Button>}{job&&<Button size="sm" variant="secondary" onClick={()=>setRestart(true)}><ClockCounterClockwise size={16}/>重新构建</Button>}<Button size="sm" onClick={newBuild}><Plus size={16}/>新建构建</Button></div></header>
   {busy&&!data?<p role="status">正在读取构建工作…</p>:error?<div role="alert" className="construction-flow-message">{error}</div>:<>

    {step==='info'?<section className="build-stage-content build-scene-information"><SpaceSettings embedded/></section>:<>

    <section className="build-stage-content" aria-label={steps.find(s=>s.id===step)?.title}>

     <div className="build-stage-heading workspace-section-heading"><div><h3>{React.createElement(steps.find(s=>s.id===step)!.icon,{size:20})}{steps.find(s=>s.id===step)?.title}</h3></div></div>
     {step==='prepare'&&<>{draft&&<div className="build-entry-modes" aria-label="构建接入方式">{[{icon:UploadSimple,title:'资料包构建',note:'上传已有资料，检查后构建',ready:true},{icon:Broadcast,title:'实时接入构建',note:'设备直连 · 增量触发',ready:false},{icon:Desktop,title:'客户端协同构建',note:'缓存补传 · 完整后触发',ready:false}].map(mode=><Button key={mode.title} variant={mode.ready?'secondary':'outline'} disabled={!mode.ready} className="build-entry-mode"><mode.icon size={20}/><span><strong>{mode.title}</strong><small>{mode.note}</small></span>{!mode.ready&&<span className="build-planned">规划中</span>}</Button>)}</div>}</>}
     {(step==='prepare'||step==='check')&&<>
      {!draft&&job?<>
       {step==='prepare'?<>
        {materialPreparation}
       </>:<>
        <div className="build-check-list" aria-label="构建核验结果">{[
         {title:'资料与输入',passed:!!model,summary:input?`${input.label} · ${inputFormat(input.format)}`:'等待资料核验',items:[`构建输入：${job.input_id||'未记录'}`, '采用任务绑定快照；历史预检仅用于追溯，不替代构建时核验']},
         {title:'模型完整性',passed:!!model,summary:model?`${model.construction.model_points.toLocaleString()} 点 · ${bytes(model.members['spatial.npz'].bytes)} · 文件摘要与资料绑定已核对`:data?.modelIssue||'等待模型产物核验',items:model?[`采用帧数：${model.construction.used_frames} / ${model.construction.input_frames}`]:['模型清单、文件摘要与资料绑定需同时匹配']},
         {title:'表达一致性',passed:!!model,summary:model?'空间可视表达与智能体空间表达均匹配空间基准模型':'等待两类表达的来源核验',items:model?[`空间可视表达：${bytes(model.members[model.human_view.path].bytes)}`,`智能体空间表达：${model.agent_view.surface_cells.toLocaleString()} 个表面单元 · ${bytes(model.members[model.agent_view.path].bytes)}`]:['两类表达必须绑定同一空间基准模型']},
         {title:'空间基准与精度',passed:false,summary:'现场对齐与精度需独立验收',items:[`坐标声明：${model?.frame_id||'待读取'} · 单位：${model?.unit||'待读取'} · 坐标轴：${model?.axes.join(' / ')||'待读取'}`,'文件检查不代表精度通过']}
        ].map((item,i)=><section className="build-check-row" key={item.title}>{item.passed?<CheckCircle size={18}/>:<WarningCircle size={18}/>}<div><strong>{item.title}</strong><p className="build-check-overview">{item.summary}</p>{<details className="build-check-item-details"><summary>{i===0?'资料与预检记录':i===1?'模型核验依据':i===2?'表达核验依据':'基准与验收说明'}{i===0&&job.input_id&&<Button variant="ghost" size="sm" className="build-preflight-history-trigger" onClick={e=>{e.preventDefault();e.stopPropagation();setPreflightOpen(true);}}><ClockCounterClockwise size={14}/>预检历史</Button>}</summary><div className="build-check-detail-body"><ul>{item.items.map(text=><li key={text}>{text}</li>)}</ul><dl>{model&&Object.entries(model.members).filter(([name])=>i===1?name==='spatial.npz':i===2?name!=='spatial.npz':false).map(([name,member])=><div key={name}><dt>{name} · {bytes(member.bytes)}</dt><dd>SHA-256：{member.sha256}</dd></div>)}</dl></div></details>}</div><StatusBadge tone={item.passed?'success':i===3?'warning':'neutral'}>{item.passed?'已通过':i===3?'未验收':'待核验'}</StatusBadge></section>)}</div>
        <div className="build-stage-footer"><span>文件完整性与表达同源检查，不替代现场精度验收</span><Button onClick={()=>setStep('model')}>模型构建<ArrowRight size={14}/></Button></div>
       </>}
      </>:<>
       {step==='prepare'&&materialPreparation}
       {step==='check'&&<BuildJobs key={`${target.space}:${target.input}`} active={active} compact buildInfo={buildInfo}/>}
      </>}
     </>}
     {step==='model'&&<>
      {!job?<div className="build-empty"><Cube size={36}/><h4>准备本次构建</h4><p>先上传或选择资料，再检查并提交构建。</p><Button onClick={()=>{if(!draft)newBuild();else setStep('prepare');}}>准备资料<ArrowRight size={14}/></Button></div>:<>
       {stages?.frozen_model?<ViewDerivations key={`${target.space}:${job.id}`} stages={stages} state={job.state} input={job.input_id} modelPoints={(model?.construction||stages.metadata?.construction)?.model_points} surfaceCells={model?.agent_view.surface_cells} artifacts={{model:{bytes:model?.members['spatial.npz']?.bytes,completedAt:data?.jobs.find(j=>j.id===stages.frozen_model?.job_id)?.finished_at},human:{bytes:model?.members[model.human_view.path]?.bytes},agent:{bytes:model?.members[model.agent_view.path]?.bytes}}}/>:<div className="build-result-grid">{[{icon:Cube,label:'空间基准模型',value:model?`${model.construction.model_points.toLocaleString()} 点`:state},{icon:Eye,label:'空间可视表达',value:model?'已生成':'待生成'},{icon:Robot,label:'智能体空间表达',value:model?`${model.agent_view.surface_cells.toLocaleString()} 单元`:'待生成'}].map(item=><article key={item.label}><item.icon size={20}/><span>{item.label}</span><strong>{item.value}</strong></article>)}</div>}
       {data?.modelIssue&&<p role="alert">{data.modelIssue}</p>}
       {!stages?.frozen_model&&['failed','interrupted'].includes(job.state)&&<BuildRecovery key={`${target.space}:${job.id}`} job={job} inputState={input?.lifecycle_state}/>}
       {model&&<div className="build-stage-footer"><span><CheckCircle size={16}/>两类表达来源一致</span><Button onClick={()=>setStep('review')}>核对成果<ArrowRight size={14}/></Button></div>}
      </>}
     </>}
     {step==='review'&&<>{model?<>
      <div className="build-review-summary"><CheckCircle size={28}/><div><h4>{release?'本次成果已有固定发布':selected?'已保存核对并选择候选':'构建完成，等待成果核对'}</h4><p>{release?release.id:selected?'可前往服务发布确认交付':'检查模型与两类表达，核对后选择候选。'}</p></div><StatusBadge tone="warning">精度待验收</StatusBadge></div>
      <div className="build-result-grid build-artifact-grid build-review-result-grid">{[{name:'spatial.npz',title:'空间基准模型',icon:Cube,value:`${model.construction.model_points.toLocaleString()} 点`,finished:data?.jobs.find(j=>j.id===(stages?.frozen_model?.job_id||job?.id))?.finished_at},{name:model.human_view.path,title:'空间可视表达',icon:Eye,value:`${model.construction.model_points.toLocaleString()} 点`,finished:stages?.views.human?.finished_at},{name:model.agent_view.path,title:'智能体空间表达',icon:Robot,value:`${model.agent_view.surface_cells.toLocaleString()} 单元`,finished:stages?.views.agent?.finished_at}].map(item=><article key={item.name}><header><div className="build-artifact-title"><item.icon size={20}/><h4>{item.title}</h4></div><StatusBadge tone="success">已校验</StatusBadge></header><div className="build-artifact-metric"><strong>{item.value}</strong><small>{bytes(model.members[item.name].bytes)}</small></div><footer><time dateTime={item.finished}>完成于 {item.finished?new Date(item.finished).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未记录'}</time><span className="build-review-proof"><CheckCircle size={14}/>{item.name==='spatial.npz'?'文件完整':'来源一致'}</span></footer></article>)}</div>
      <section className="build-reference-review"><header><MapPin size={18}/><h4>空间基准核对</h4><StatusBadge tone="warning">待独立复核</StatusBadge></header><dl><div><dt>坐标基准</dt><dd>{model.frame_id}</dd></div><div><dt>计量单位</dt><dd>{model.unit}</dd></div><div><dt>坐标轴</dt><dd>{model.axes.join(' / ')}</dd></div></dl><p>构建采用以上坐标声明；现场对齐与精度尚未验收。</p></section>

      <div className="build-stage-footer"><span>仅核对固定成果；现场质量未验收</span>{selected?<Button asChild><a href={recordLink('delivery',{job:model.id,...(release?{publication:release.id}:{})})}>服务发布<ArrowRight size={14}/></a></Button>:<Button onClick={()=>setReview({candidate:model.id,revision:data!.selection.revision})}>核对并选择候选<ArrowRight size={14}/></Button>}</div>
     </>:<div className="build-empty"><Eye size={32}/><h4>尚无可核对成果</h4><p>模型与两类表达完成并通过同源校验后，在这里核对。</p><Button variant="outline" onClick={()=>setStep('model')}>查看构建状态</Button></div>}</>}
    </section>
    </>}
    {step!=='info'&&job&&<details className="build-execution"><summary>执行记录与技术信息</summary><dl className="build-facts"><div><dt>创建时间</dt><dd>{new Date(job.created_at).toLocaleString('zh-CN',{hour12:false})}</dd></div><div><dt>执行状态</dt><dd>{labels[job.state]||job.state}</dd></div>{job.retry_of&&<div><dt>重试来源</dt><dd><a href={recordLink('build',{tab:'flow',job:job.retry_of})}>{job.retry_of}</a></dd></div>}{job.view_parent_id&&<div><dt>派生来源</dt><dd><a href={recordLink('build',{tab:'flow',job:job.view_parent_id})}>{job.view_parent_id}</a></dd></div>}{job.error&&<div><dt>错误代码</dt><dd>{job.error}</dd></div>}{model&&<div><dt>模型 SHA-256</dt><dd>{model.members['spatial.npz'].sha256}</dd></div>}</dl></details>}
   </>}
   </div>
  </div>
  {assistantOpen&&<aside className={`build-assistant-column ${assistantWide?'build-assistant-wide':''}`} aria-label="构建智能助手" id="build-assistant-panel"><header><Sparkle size={18}/><h2>构建助手</h2><div className="build-assistant-header-actions"><Button variant="ghost" size="sm" aria-label={assistantWide?'收窄助手面板':'加宽助手面板'} title={assistantWide?'收窄至 320px':'加宽至 640px'} aria-pressed={assistantWide} onClick={()=>setAssistantWide(v=>!v)}>{assistantWide?<ArrowsInSimple size={16}/>:<ArrowsOutSimple size={16}/>}</Button><Button variant="ghost" size="sm" aria-label="关闭构建助手" onClick={()=>setAssistantOpen(false)}><X size={16}/></Button></div></header><div className="build-assistant-scroll" tabIndex={0}><div className="build-assistant-context"><span>当前构建</span><strong title={currentInput}>{currentInput}</strong></div><section className="build-support-body"><div className="build-assistant-welcome"><Sparkle size={16}/>构建指引 · {step==='info'?'基本信息':steps.find(s=>s.id===step)?.title}</div><p>{step==='info'?'场景基本信息由当前空间统一维护，修改后同步用于场景目录。地址和地图锚点不改变构建模型坐标。':step==='prepare'?'上传资料会登记到当前场景，也可使用已登记资料。已有点云执行整理与表达派生，不自动配准或重建。':step==='check'?'先选择本次资料并执行预检，再提交构建。文件完整性检查不代表坐标与精度验收。':step==='model'?'空间基准模型保留本次固定成果；可视表达与智能体空间表达来自同一模型，可以分别重新生成。新候选经核对后再发布。':'核对模型与两类表达的来源后，保存候选选择，再前往服务发布。已有固定发布不会自动切换。'}</p><details><summary>构建与重建</summary><p>补充资料后新建构建，或沿用空间基准模型重新生成指定表达。历史构建与固定发布保留。</p></details><details><summary>成果说明</summary><p>空间基准模型是本次构建保存的空间成果，尚不等同于独立验收的空间真值。智能体空间表达仅覆盖观测表面；未知区域不代表可通行。</p></details><details><summary>接入与自动构建</summary><p>实时接入与客户端协同为规划能力，预留增量、批次完整与补传完成触发条件，尚未启用。</p></details></section></div><footer><StatusBadge tone="info">智能问答规划中</StatusBadge><p>当前提供与构建环节关联的操作指引。</p><div className="build-assistant-composer"><Textarea aria-label="向构建助手提问" placeholder="描述构建目标，或询问当前任务…" disabled/><div><small>智能问答尚未接入</small><Button disabled size="sm">发送<ArrowRight size={14}/></Button></div></div></footer></aside>}

  <Drawer open={preflightOpen} onClose={()=>setPreflightOpen(false)} side="right" width={400} title="预检历史" description={currentInput} closeLabel="关闭预检历史">{job?.input_id&&<PreflightHistory endpoint={endpoint} identity={job.input_id} embedded/>}</Drawer>
  <Dialog open={restart} onOpenChange={setRestart}><DialogContent><DialogHeader><DialogTitle>从哪个环节重新开始</DialogTitle><DialogDescription>将在新构建中选择或添加资料，当前构建与已有发布保持不变。</DialogDescription></DialogHeader><div className="build-restart-options"><Button variant="outline" onClick={()=>{setRestart(false);newBuild();}}><UploadSimple size={20}/><span><strong>资料准备</strong><small>补充或更换资料，检查后新建构建</small></span><ArrowRight size={16}/></Button><Button variant="outline" onClick={()=>{setRestart(false);appNavigate(recordLink('build',{tab:'tasks',...(job?.input_id?{input:job.input_id}:{}),...(job?.batch_ref?{batch:job.batch_ref.batch_id}:{})}));}}><Cube size={20}/><span><strong>模型构建</strong><small>重新选择并核验资料，生成模型与两类表达</small></span><ArrowRight size={16}/></Button><Button variant="outline" disabled={!stages?.frozen_model} onClick={()=>{setRestart(false);setStep('model');}}><Eye size={20}/><span><strong>表达派生</strong><small>沿用冻结模型，选择需要重新生成的空间表达</small></span><ArrowRight size={16}/></Button></div></DialogContent></Dialog>
  {review&&data&&<CandidateReview key={review.candidate} candidate={review.candidate} space={target.space} revision={data.selection.revision} onClose={()=>setReview(null)} onSelected={async()=>{setReview(null);window.dispatchEvent(new Event('cospace-selection-changed'));}}/>}
 </section>;
}
