import React,{useEffect,useState} from 'react';
import {Button,NativeSelect,StatusBadge} from '@vxture/design-system';
import {ArrowClockwise,ArrowUpRight,Database,Cube,Eye,Robot,ArrowRight} from '@phosphor-icons/react';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink,useRecordNavigation} from './record-navigation';
import {inputCounts,inputFormat} from './input-format';
import {CandidateReview} from './candidate-review';
import {realScreenHref} from './real-space-data';
import {BuildRecovery,RecoverableJob} from './build-recovery';
import {BuildStages,ViewDerivations,viewState} from './view-derivations';
import {BuildVisualization} from './build-visualization';
import './construction-flow.css';

type Input={id:string;space_id:string;label:string;format:string;input_frames:number;used_frames:number;verified_image_members?:number;verified_messages?:number;lifecycle_state?:string};
type Job=RecoverableJob&{created_at:string;candidate_url:string|null;pipeline?:string;view_parent_id?:string;stage?:string};
type Model={id:string;space_id:string;profile:string;frame_id:string;unit:string;axes:string[];bounds_m:number[][];data_kind:string;construction:{model_points:number;used_frames:number;input_frames:number};source:{input_binding?:{id:string}};human_view:{path:string;source_model_sha256:string};agent_view:{path:string;source_model_sha256:string;resolution_m:number;surface_cells:number;unlisted_state:string};members:Record<string,{bytes:number;sha256:string}>};
type Release={id:string;candidate_id:string;source_model_sha256:string;lifecycle_state?:string};
type Snapshot={inputs:Input[];jobs:Job[];job?:Job;model?:Model;stages?:BuildStages;modelIssue?:string;selection:{candidate_id:string|null;revision:number};releases:Release[]};
const bytes=(value:number)=>value>=1024*1024?`${(value/1024/1024).toFixed(2)} MB`:`${(value/1024).toFixed(1)} KB`;

/** Explain actual saved artifacts; reading this page never starts, selects or publishes a build. */
export function ConstructionFlow({active=true}:{active?:boolean}={}){
 const target=useRecordNavigation();
 const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(true),[revision,setRevision]=useState(0);
 const [review,setReview]=useState<{candidate:string;revision:number}|null>(null);
 useEffect(()=>{setReview(null);setData(null);},[target.space,target.input,target.job,active]);
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
   const job=target.job?scoped.find(j=>j.id===target.job):scoped[0];
   if(target.job&&!job)throw Error('指定构建任务不属于当前场景或资料；请重新选择。');
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
 },[target.space,target.input,target.job,active,revision]);
 const job=data?.job,model=data?.model,stages=data?.stages,input=data?.inputs.find(i=>i.id===(job?.input_id||target.input));
 const sameSource=!!model,release=model&&data?.releases.find(r=>r.candidate_id===model.id&&r.source_model_sha256===model.members['spatial.npz'].sha256&&(!r.lifecycle_state||r.lifecycle_state==='active'));
 const selected=!!model&&data?.selection.candidate_id===model.id;
 const values={...(input?{input:input.id}:{}),...(job?{job:job.id}:{})};
 const taskLink=recordLink('build',{tab:'tasks',...values,...(job?.batch_ref?{batch:job.batch_ref.batch_id}:target.batch?{batch:target.batch}:{})});
 const state=data?.modelIssue?'成果待核查':job?.state==='succeeded'?'候选已就绪':job?.state==='views_failed'?'视图待恢复':job?.state==='failed'?'构建失败':job?.state==='interrupted'?'构建中断':job?.state==='queued'?'排队中':job?.stage==='deriving_views'?'模型已冻结 · 视图派生中':job?'构建中':input?'待构建':'待资料';
 return <section className="construction-flow" aria-label="场景空间构建流程">
  <div className="construction-flow-heading"><div><h2>资料到双视图</h2><p>一个场景、一份三维模型，两类视图从同一模型派生。</p></div><Button variant="outline" size="sm" aria-label="刷新构建流程" disabled={busy} onClick={()=>setRevision(n=>n+1)}><ArrowClockwise size={15}/></Button></div>
  {busy&&!data?<p role="status">正在核对当前场景的构建成果…</p>:error?<div role="alert" className="construction-flow-message">{error}</div>:<>
   <div className="construction-flow-target"><label htmlFor="flow-job">本次构建</label><NativeSelect id="flow-job" value={job?.id||''} onChange={e=>{location.hash=recordLink('build',{tab:'flow',...(target.input?{input:target.input}:{}),...(e.target.value?{job:e.target.value}:{})});}}><option value="" disabled>{data?.jobs.length?'选择任务':'尚无构建任务'}</option>{data?.jobs.filter(j=>!target.input||j.input_id===target.input).map(j=><option key={j.id} value={j.id}>{new Date(j.created_at).toLocaleString('zh-CN',{hour12:false})} · {j.id}</option>)}</NativeSelect><StatusBadge tone={model?'success':job?.state==='failed'?'danger':'warning'}>{state}</StatusBadge></div>
   <ol className="construction-flow-stages">
    {[{icon:Database,title:'资料入库',status:input?'已登记':data?.inputs.length?'待选择':'待导入',detail:input?input.label:'在当前场景空间登记和检查资料。'},
      {icon:Cube,title:'三维模型 · 真值候选',status:stages?.frozen_model?'已冻结':model?'已生成':state,detail:(model||stages?.metadata)?`${(model?.construction||stages!.metadata!.construction).model_points.toLocaleString()} 个模型点 · ${(model?.construction||stages!.metadata!.construction).used_frames}/${(model?.construction||stages!.metadata!.construction).input_frames} 帧`:'将观测重建或已有成果整理为固定模型。'},
      {icon:Eye,title:'人视图',status:stages?.frozen_model?viewState(stages.views.human?.state):model?'已派生':'待派生',detail:'供人员浏览、空间复查与可视化系统使用。'},
      {icon:Robot,title:'智能体视图',status:stages?.frozen_model?viewState(stages.views.agent?.state):model?'已派生':'待派生',detail:'轻量表面单元，供空间查询与离线消费验证。'}].map((step,i)=><li key={step.title} data-state={i===0?input?'succeeded':'queued':i===1?stages?.frozen_model?'succeeded':job?.state:i===2?stages?.views.human?.state:stages?.views.agent?.state}><div className="construction-stage-top"><step.icon size={20}/><span>{String(i+1).padStart(2,'0')}</span></div><h3>{step.title}</h3><span className="construction-stage-status">{step.status}</span><p>{step.detail}</p>{i===1&&<ArrowRight className="construction-stage-arrow" size={16}/>}</li>)}
   </ol>
   <p className="construction-flow-note">{job?.pipeline?'模型冻结、两类视图派生分别保存状态。两类视图完成并校验同源后，才可核对候选。':'这是历史一体构建记录；新构建支持模型冻结和两类视图独立派生。'}精度仍未验收。</p>
   {job&&<BuildVisualization key={`visual-${target.space}:${job.id}`} endpoint={endpoint} space={target.space} job={job.id} input={job.input_id||''} stages={stages} state={job.state}/>}
   {job&&stages?.frozen_model&&<ViewDerivations key={`${target.space}:${job.id}`} stages={stages} state={job.state} input={job.input_id}/>}
   {job&&!stages?.frozen_model&&['failed','interrupted'].includes(job.state)&&<BuildRecovery key={`${target.space}:${job.id}`} job={job} inputState={input?.lifecycle_state}/>}
   {job?.view_parent_id&&<p className="construction-flow-note">视图派生来源：<a href={recordLink('build',{tab:'flow',job:job.view_parent_id})}>{job.view_parent_id}</a>；固定模型和原候选保留。</p>}
   {job?.retry_of&&<p className="construction-flow-note">本任务重试自 <a href={recordLink('build',{tab:'flow',job:job.retry_of,...(job.input_id?{input:job.input_id}:{})})}>{job.retry_of}</a>；原任务记录保留。</p>}
   {job&&data?.jobs.filter(j=>j.retry_of===job.id).map(j=><p key={j.id} className="construction-flow-note">重试记录：<a href={recordLink('build',{tab:'flow',job:j.id,...(j.input_id?{input:j.input_id}:{})})}>{j.id}</a> · {j.state==='succeeded'?'已生成':j.state==='failed'?'失败':j.state==='interrupted'?'中断':'运行中'}</p>)}
   {data?.modelIssue&&<p role="alert" className="construction-flow-message">{data.modelIssue} 原任务记录已保留，当前不能核对或发布该成果；请刷新或前往任务列表重新选择资料构建。</p>}
   <div className="construction-flow-actions">{model?(release?<Button asChild size="sm"><a href={realScreenHref(target.space,release.id)} target="_blank" rel="noopener noreferrer">打开发布空间<ArrowUpRight size={14}/></a></Button>:selected?<Button asChild size="sm"><a href={recordLink('delivery',{job:model.id})}>前往确认发布<ArrowRight size={14}/></a></Button>:<Button size="sm" onClick={()=>setReview({candidate:model.id,revision:data!.selection.revision})}>核对本次模型<ArrowRight size={14}/></Button>):<Button asChild variant={job?'outline':'default'} size="sm"><a href={taskLink}>{job?'更换资料或批次':'选择资料并构建'}<ArrowRight size={14}/></a></Button>}<Button asChild variant="outline" size="sm"><a href={recordLink('data',{tab:'inputs',...(input?{input:input.id}:{}),...(job?.batch_ref?{batch:job.batch_ref.batch_id}:{})})}>查看场景资料</a></Button>{job?.batch_ref&&<Button asChild variant="outline" size="sm"><a href={recordLink('data',{space:target.space,tab:'batches',batch:job.batch_ref.batch_id})}>查看来源批次</a></Button>}{model&&<Button asChild variant="outline" size="sm"><a href={`${endpoint}/candidates/${model.id}/`} target="_blank" rel="noopener noreferrer">预览双视图<ArrowUpRight size={14}/></a></Button>}</div>
   {model&&<>
    <div className="construction-artifacts"><div className="construction-flow-heading"><h3>本次构建成果</h3><StatusBadge tone={sameSource?'success':'warning'}>双视图来源一致</StatusBadge></div>
     <div className="construction-artifact-grid">{[{name:'spatial.npz',title:'三维模型',description:'统一坐标下的几何与颜色；本轮权威几何载体。'},{name:model.human_view.path,title:'人视图',description:'彩色点云 PLY；后续可扩展网格与分块表达。'},{name:model.agent_view.path,title:'智能体视图',description:`NPZ 表面索引 · ${model.agent_view.resolution_m} m · ${model.agent_view.surface_cells.toLocaleString()} 个单元。`}].map(item=><article key={item.name}><h4>{item.title}</h4><p>{item.description}</p><code>{item.name}</code><span>{bytes(model.members[item.name].bytes)}</span><small title={model.members[item.name].sha256}>SHA-256 {model.members[item.name].sha256.slice(0,16)}…</small></article>)}</div>
     <dl className="construction-model-meta"><dt>模型版本</dt><dd>{model.id}{data?.selection.candidate_id===model.id?' · 当前已选候选':' · 尚未选为当前候选'}</dd><dt>坐标与单位</dt><dd>{model.frame_id} · {model.unit}</dd><dt>原始资料</dt><dd>{input?`${inputFormat(input.format)} · ${inputCounts(input)}`:job?.input_id}</dd><dt>共同来源</dt><dd className="construction-digest">{model.members['spatial.npz'].sha256}</dd></dl>
    </div>
    <div className="construction-flow-handoff"><div><h3>{release?'已有匹配的固定发布':selected?'本次模型已选定，可以确认发布':'下一步：核对与固定发布'}</h3><p>{release?`发布 ${release.id} 固定引用本次模型；在线与离线均使用这个发布。`:selected?'进入发布与服务时携带本次候选；如候选选择变化，先重新核对。':'点击“核对本次模型”保存核对与选择，再确认发布。语义标注、台账与对象关系按用途补充。'}</p></div>{(release||selected)&&<Button asChild variant="outline" size="sm"><a href={recordLink('delivery',release?{publication:release.id,job:model.id}:{job:model.id})}>发布与服务<ArrowUpRight size={14}/></a></Button>}</div>
    <p className="construction-flow-note">{model.data_kind==='existing_pointcloud_candidate'?'此成果保留已有点云的声明坐标，未执行配准，场景对齐与独立精度均未验收。':model.data_kind==='real_lidar_multiframe_candidate'?'此成果由本次纯激光逐帧配准生成局部模型和估计轨迹；未做回环、现场对齐或独立精度验收。':model.data_kind==='real_lidar_sensor_local_candidate'?'此成果为单帧传感器局部空间，未执行多帧配准或 SLAM。':'使用已有估计位姿进行短序列点云累积，未完成全场景重建或独立精度验收。'}智能体视图仅声明观测表面候选，其余为未知；未提供已验证的空闲空间、ESDF 或导航能力。</p>
   </>}
  </>}
  {review&&data&&<CandidateReview key={review.candidate} candidate={review.candidate} space={target.space} revision={data.selection.revision} onClose={()=>setReview(null)} onSelected={async()=>{setReview(null);window.dispatchEvent(new Event('cospace-selection-changed'));}}/>}
 </section>;
}
