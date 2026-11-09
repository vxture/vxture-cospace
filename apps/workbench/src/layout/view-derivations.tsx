import {appNavigate} from './app-router';
import React,{useEffect,useRef,useState} from 'react';
import {Button,StatusBadge} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink} from './record-navigation';

export type BuildStages={job_id:string;space_id:string;legacy?:boolean;candidate_ready:boolean;frozen_model:null|{job_id:string;model_id:string;source_model_sha256:string;manifest_sha256:string};metadata?:{construction:{model_points:number;used_frames:number;input_frames:number}};views:Record<string,{id:string;job_id:string;state:string;error?:string;frozen_model:{source_model_sha256:string}}>};
const stateName:Record<string,string>={queued:'排队中',running:'派生中',succeeded:'已派生',failed:'派生失败',interrupted:'派生中断'};
export const viewState=(state?:string)=>stateName[state||'']||'待派生';

export function ViewDerivations({stages,state,input}:{stages:BuildStages;state:string;input?:string}){
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
 return <div className="construction-view-tasks" aria-label="独立视图派生">
  <div className="construction-flow-heading"><h3>独立视图任务</h3><StatusBadge tone={stages.candidate_ready?'success':'warning'}>{stages.candidate_ready?'可核对候选':'尚不可发布'}</StatusBadge></div>
  <p className="construction-flow-note">模型已冻结。每次只重新派生所选视图，另一类视图保留原任务引用；完成后形成新候选，核对后再发布。</p>
  <div className="construction-view-task-grid">{['human','agent'].map(kind=>{const task=stages.views[kind];return <article key={kind}><div><h4>{kind==='human'?'人视图':'智能体视图'}</h4><StatusBadge tone={task?.state==='succeeded'?'success':task?.state==='failed'?'danger':'warning'}>{viewState(task?.state)}</StatusBadge></div><code>{task?.id||'待创建'}</code>{task?.error&&<p role="alert">{task.state==='interrupted'?'服务中断，任务记录已保留。':'该视图未能完成，可以单独重试。'}</p>}<Button size="sm" variant="outline" disabled={!ready||!!busy||running} onClick={()=>start(kind)}>{busy===kind?'正在处理…':pending[kind]?'核对提交结果':task?.state==='succeeded'?`重新派生${kind==='human'?'人视图':'智能体视图'}`:`重试${kind==='human'?'人视图':'智能体视图'}`}</Button></article>;})}</div>
  {error&&<p role="alert" className="construction-flow-message">{error}</p>}
  <p className="construction-flow-note">固定模型：<a href={recordLink('build',{space:stages.space_id,tab:'flow',job:stages.frozen_model!.job_id})}>{stages.frozen_model!.model_id}</a> · SHA-256 {stages.frozen_model!.source_model_sha256.slice(0,16)}…</p>
 </div>;
}
