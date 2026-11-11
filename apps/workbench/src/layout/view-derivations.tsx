import {appNavigate} from './app-router';
import React,{useEffect,useRef,useState} from 'react';
import {Cube,Eye,Robot,ArrowUpRight} from '@phosphor-icons/react';
import {buildScanHref} from './build-scan-data';
import {Button,StatusBadge} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink} from './record-navigation';

export type BuildStages={job_id:string;space_id:string;legacy?:boolean;candidate_ready:boolean;frozen_model:null|{job_id:string;model_id:string;source_model_sha256:string;manifest_sha256:string};metadata?:{construction:{model_points:number;used_frames:number;input_frames:number}};views:Record<string,{id:string;job_id:string;state:string;error?:string;finished_at?:string;frozen_model:{source_model_sha256:string}}>};
const stateName:Record<string,string>={queued:'排队中',running:'派生中',succeeded:'已派生',failed:'派生失败',interrupted:'派生中断'};
export const viewState=(state?:string)=>stateName[state||'']||'待派生';

type ArtifactDetails=Record<string,{bytes?:number;completedAt?:string}>;
const artifactSize=(value?:number)=>value===undefined?'大小待记录':value>=1024**3?`${(value/1024**3).toFixed(2)} GB`:value>=1024**2?`${(value/1024**2).toFixed(2)} MB`:value>=1024?`${(value/1024).toFixed(1)} KB`:`${value} B`;
const completionTime=(value?:string)=>value?new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未记录';
export function ViewDerivations({stages,state,input,modelPoints,surfaceCells,artifacts={}}:{stages:BuildStages;state:string;input?:string;modelPoints?:number;surfaceCells?:number;artifacts?:ArtifactDetails}){
 const [pending,setPending]=useState<Record<string,string>>({}),[busy,setBusy]=useState(''),[error,setError]=useState(''),[ready,setReady]=useState(false);
 const alive=useRef(true),latch=useRef(false);
 const key=(kind:string)=>`cospace:view:${endpoint}:${stages.space_id}:${stages.job_id}:${kind}`;
 useEffect(()=>{alive.current=true;try{const saved:Record<string,string>={};for(const kind of ['human','agent']){const token=sessionStorage.getItem(key(kind));if(token){if(!/^[a-f0-9]{32}$/.test(token))throw Error();saved[kind]=token;}}setPending(saved);setReady(true);}catch{setError('浏览器无法保存提交记录，请允许会话存储后刷新。');}return()=>{alive.current=false;};},[stages.space_id,stages.job_id]);
 const go=(job:{id:string;space_id:string;view_parent_id:string;rerun_view:string},kind:string)=>{
  if(job.space_id!==stages.space_id||job.view_parent_id!==stages.job_id||job.rerun_view!==kind)throw Error('视图任务与当前场景不一致。');
  appNavigate(recordLink('build',{space:stages.space_id,tab:'flow',job:job.id,...(input?{input}:{})}));
 };
 async function start(kind:string){
  if(latch.current)return;latch.current=true;setBusy(kind);setError('');
  try{
   let token=sessionStorage.getItem(key(kind));
   if(pending[kind]){
    const response=await fetch(`${endpoint}/api/builds?${new URLSearchParams({space_id:stages.space_id})}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
    if(!response.ok)throw Error('暂时无法核对提交记录，请稍后重试。');
    const body=await response.json();const found=body.jobs.find((j:{view_request_id?:string;view_parent_id?:string})=>j.view_request_id===token&&j.view_parent_id===stages.job_id);
    if(!alive.current)return;if(found){go(found,kind);return;}
    setPending(p=>{const next={...p};delete next[kind];return next;});setError('尚未找到任务；可使用原请求重新提交，系统会去重。');return;
   }
   token=token||crypto.randomUUID().replaceAll('-','');sessionStorage.setItem(key(kind),token);setPending(p=>({...p,[kind]:token!}));
   const response=await fetch(`${endpoint}/api/view-derivations`,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(20000),body:JSON.stringify({space_id:stages.space_id,candidate_id:stages.job_id,view_kind:kind,request_id:token})});
   if(!alive.current)return;
   if(!response.ok){if(response.status>=500)throw Error('服务暂不可用，提交结果未确认，请先核对。');const body=await response.json();throw Error(body.detail==='build_already_running'?'已有构建运行，请等待后核对重试。':'当前模型或视图未通过准入检查，请核查状态与权限。');}
   const result=await response.json();go(result.job,kind);
  }catch(e){if(alive.current)setError(e instanceof Error&&e.message.includes('。')?e.message:'连接中断或提交结果未确认，请先核对。');}
  finally{latch.current=false;if(alive.current)setBusy('');}
 }
 const running=['queued','running'].includes(state);
 return <section className="build-artifact-section" aria-label="构建成果与表达派生">
  <div className="build-result-grid build-artifact-grid">
   <article><header><div className="build-artifact-title"><Cube size={20}/><h4>空间基准模型</h4></div><StatusBadge tone="info">已保存</StatusBadge></header><div className="build-artifact-metric"><strong>{modelPoints===undefined?'— 点':`${modelPoints.toLocaleString()} 点`}</strong><small>{artifactSize(artifacts.model?.bytes)}</small></div><footer><time dateTime={artifacts.model?.completedAt}>完成于 {completionTime(artifacts.model?.completedAt)}</time><Button asChild size="sm" variant="secondary"><a href={buildScanHref(stages.space_id,stages.job_id,input||'')} target="_blank" rel="noopener noreferrer">查看模型<ArrowUpRight size={14}/></a></Button></footer></article>
   {['human','agent'].map(kind=>{const task=stages.views[kind],title=kind==='human'?'空间可视表达':'智能体空间表达',Glyph=kind==='human'?Eye:Robot;return <article key={kind}><header><div className="build-artifact-title"><Glyph size={20}/><h4>{title}</h4></div><StatusBadge tone={task?.state==='succeeded'?'success':task?.state==='failed'?'danger':'warning'}>{viewState(task?.state)}</StatusBadge></header><div className="build-artifact-metric"><strong>{task?.state==='succeeded'?(kind==='human'?(modelPoints===undefined?'— 点':`${modelPoints.toLocaleString()} 点`):(surfaceCells===undefined?'— 单元':`${surfaceCells.toLocaleString()} 单元`)):(kind==='human'?'— 点':'— 单元')}</strong><small>{task?.state==='succeeded'?artifactSize(artifacts[kind]?.bytes):'大小待生成'}</small></div>{task?.error&&<p role="alert">{task.state==='interrupted'?'任务中断，记录已保留。':'生成失败，可单独重试。'}</p>}<footer>{task?.state==='succeeded'&&<time dateTime={task.finished_at}>完成于 {completionTime(task.finished_at)}</time>}<Button size="sm" variant="secondary" aria-label={`${pending[kind]?'核对提交结果':task?.state==='succeeded'?'重新生成':'重试生成'}${title}`} disabled={!ready||!!busy||running} onClick={()=>start(kind)}>{busy===kind?'正在处理…':pending[kind]?'核对提交结果':task?.state==='succeeded'?'重新生成':'重试生成'}</Button></footer></article>;})}
  </div>
  {error&&<p role="alert" className="construction-flow-message">{error}</p>}
 </section>;
}
