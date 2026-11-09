import {appNavigate} from './app-router';
import React,{useEffect,useRef,useState} from 'react';
import {Button} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink} from './record-navigation';

export type RecoverableJob={id:string;space_id:string;state:string;input_id?:string;error?:string;retry_of?:string;retry_request_id?:string;batch_ref?:{batch_id:string;admitted_revision:number}};
const explanations:Record<string,string>={
 preview_service_restarted:'服务重启使本次任务中断。',build_failed:'构建程序未能完成。',build_timeout:'构建超时。',
 retry_input_file_unavailable:'原资料文件不可读，请到数据管理核查。',configured_input_missing:'原资料文件缺失，请到数据管理核查。',
 retry_input_binding_changed:'资料登记信息已变化，不能沿用原任务重试。',retry_input_unavailable:'原任务资料不可用。',
 lifecycle_disabled_new_use_blocked:'原资料已停用，请先核查使用状态。',lifecycle_archived_new_use_blocked:'原资料已归档，请先核查使用状态。',
 batch_changed_refresh_required:'原批次修订已变化，请核查批次后重新选择构建资料。',batch_not_sealed_or_disabled:'原批次未封存或已停用。',
 registered_input_changed:'原资料内容已变化，请重新登记并检查资料。',input_integrity:'原资料完整性校验失败，请核查文件。',
 build_already_running:'当前已有构建运行，请等待完成后重试。',retry_route_not_supported:'此任务需要从对应业务入口重新处理。',
};
export const buildErrorText=(code?:string)=>code?(explanations[code]||'任务未完成，请核查资料与批次。'):'';

/** A saved request token survives refresh; every replay uses the same admission. */
export function BuildRecovery({job,inputState}:{job:RecoverableJob;inputState?:string}){
 const key=`cospace:build-retry:${endpoint}:${job.space_id}:${job.id}`;
 const [token,setToken]=useState(''),[pending,setPending]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[storageReady,setStorageReady]=useState(false);
 const latch=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;try{const saved=sessionStorage.getItem(key);if(saved&&!/^[a-f0-9]{32}$/.test(saved))throw Error();setToken(saved||'');setPending(!!saved);setStorageReady(true);}catch{setMessage('浏览器无法保存提交记录，请允许本站会话存储后刷新。');}return()=>{alive.current=false;};},[key]);
 const unavailable=!!inputState&&inputState!=='active';
 const navigate=(next:RecoverableJob)=>{if(next.space_id!==job.space_id||next.retry_of!==job.id||next.input_id!==job.input_id)throw Error('重试结果与原场景或资料不一致。');appNavigate(recordLink('build',{space:job.space_id,tab:'flow',job:next.id,...(next.input_id?{input:next.input_id}:{})}));};
 async function act(check:boolean){
  if(latch.current)return;latch.current=true;setBusy(true);setMessage('');
  try{
   if(check){
    const response=await fetch(`${endpoint}/api/builds?${new URLSearchParams({space_id:job.space_id})}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
    if(!response.ok)throw Error('暂时无法核对提交结果，请恢复连接后再次核对。');
    const body=await response.json();if(!Array.isArray(body.jobs))throw Error('任务列表无法读取。');
    if(!alive.current)return;
    const existing=body.jobs.find((j:RecoverableJob)=>j.retry_request_id===token&&j.retry_of===job.id);
    if(existing){navigate(existing);return;}
    setPending(false);setMessage('尚未找到对应任务，可以使用原请求重新提交；系统会去重。');return;
   }
   const request=token||crypto.randomUUID().replaceAll('-','');
   sessionStorage.setItem(key,request);setToken(request);setPending(true);
   const response=await fetch(`${endpoint}/api/build-retries`,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(20000),body:JSON.stringify({space_id:job.space_id,retry_of:job.id,request_id:request})});
   if(!alive.current)return;
   if(response.status>=500)throw Error('服务暂不可用，提交结果尚未确认，请先核对。');
   const body=await response.json();
   if(!response.ok){setMessage(response.status===401||response.status===403?'当前登录或权限不允许重试，请重新登录并核对提交结果。':buildErrorText(String(body.detail)));return;}
   navigate(body.job);
  }catch(e){if(alive.current)setMessage(e instanceof Error&&e.message.includes('。')?e.message:'连接中断或提交结果未确认，请先核对提交结果。');}
  finally{latch.current=false;if(alive.current)setBusy(false);}
 }
 return <div className="construction-recovery" aria-label="失败任务恢复">
  <h3>{job.state==='interrupted'?'恢复中断的构建':'重新构建'}</h3>
  <p>{buildErrorText(job.error)}重试会创建新任务，原记录与历史发布保留。</p>
  {unavailable&&<p role="alert">原资料{inputState==='archived'?'已归档':'已停用'}，当前不能重新构建。</p>}
  {pending&&<p role="status">存在待核对的提交记录，请先核对结果；刷新不会自动提交。</p>}
  {message&&<p role="alert">{message}</p>}
  <div className="construction-flow-actions"><Button size="sm" disabled={busy||!storageReady||(!pending&&unavailable)} onClick={()=>act(pending)}>{busy?'正在处理…':pending?'核对提交结果':'使用原资料重新构建'}</Button>
   <Button asChild variant="outline" size="sm"><a href={recordLink('data',{space:job.space_id,tab:'inputs',...(job.input_id?{input:job.input_id}:{})})}>核查原资料</a></Button>
   {job.batch_ref&&<Button asChild variant="outline" size="sm"><a href={recordLink('data',{space:job.space_id,batch:job.batch_ref.batch_id})}>核查原批次</a></Button>}
  </div>
 </div>;
}
