import {recordLink,useRecordNavigation} from './record-navigation';
import type {Preparation} from './data-intake';
import {usePlatformSession} from './platform-auth';
import React,{useEffect,useRef,useState} from 'react';
import {Button,StatusBadge} from '@vxture/design-system';
import {inputCounts,inputRoute,InputRoute,validRoute} from './input-format';

type Detail={route?:InputRoute;registration_ref?:{source_id?:string;settings_revision?:number;actor:string;method?:string;package_sha256?:string};id:string;snapshot:string;tracking?:string;format:string;input_frames:number;used_frames:number;point_count?:number;verified_image_members?:number;verified_messages?:number;supported_format:string;limitations:string[]};
type Check={space_id?:string;registration_matches?:boolean;sequence?:number;actor?:string;input_id:string;status:string;checked_at:string;issue:null|{title:string;action:string};notice:string};
export function InputDetails({endpoint,identity,showBuild=false,lifecycleState,onChecked,batchId,preparation}:{preparation?:Preparation|null;endpoint:string;identity:string;showBuild?:boolean;lifecycleState?:string;onChecked?:()=>void;batchId?:string}){
 const target=useRecordNavigation(),platform=usePlatformSession();
 const [detail,setDetail]=useState<Detail|null>(null),[check,setCheck]=useState<Check|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const generation=useRef(0);const [historical,setHistorical]=useState(false);
 useEffect(()=>{
  const run=++generation.current,controller=new AbortController();setDetail(null);setCheck(null);setError('');setBusy(false);setLoading(true);setHistorical(false);
  const read=async(path:string)=>{const r=await fetch(endpoint+path,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('资料或保存的预检记录无法读取，请刷新数据重试。');return r.json();};
  Promise.all([read(`/api/inputs/${identity}`),platform?read(`/api/inputs/${identity}/preflight`):Promise.resolve({last_check:null})]).then(([body,saved])=>{
   if(body.id!==identity||target.space&&body.space_id&&body.space_id!==target.space||saved.last_check&&saved.last_check.input_id!==identity)throw Error('资料与当前场景不一致，请重新选择。');
   if(run===generation.current){setDetail(body);setCheck(saved.last_check);setHistorical(true);}
  }).catch(e=>{if(!controller.signal.aborted&&run===generation.current)setError(e.message);}).finally(()=>{if(run===generation.current)setLoading(false);});
  return()=>{controller.abort();generation.current++;};
 },[endpoint,identity,target.space,!!platform]);
 async function inspect(){
  if(busy)return;const run=generation.current;setHistorical(false);setCheck(null);setError('');setBusy(true);
  try{
   const r=await fetch(`${endpoint}/api/inputs/${identity}/preflight`,{method:'POST'});
   if(!r.ok)throw Error('预检未完成，请检查服务和登记记录后重试。');
   const body:Check=await r.json();
   if(body.input_id!==identity||target.space&&body.space_id&&body.space_id!==target.space)throw Error('预检结果与当前资料不一致。');
   if(run===generation.current){setCheck(body);onChecked?.();}
  }catch(e){if(run===generation.current)setError(e instanceof Error?e.message:'预检失败');}
  finally{if(run===generation.current)setBusy(false);}
 }
 const inactive=lifecycleState==='disabled'||lifecycleState==='archived';
 const route=detail&&inputRoute(detail.format)?validRoute(detail.route)?detail.route:inputRoute(detail.format):null;
 const passed=check?.status==='passed'&&check.registration_matches!==false;
 return <section aria-label="资料详情与预检" className="data-input-preflight flex flex-col gap-md border-t border-border pt-md" tabIndex={-1}>
  <h3 className="text-body-small font-medium">预检与构建</h3>
  {loading&&<p role="status" className="text-body-small text-muted-foreground">正在读取资料与预检记录…</p>}
  {!check&&!loading&&!busy&&!error&&<p className="text-body-small text-muted-foreground">待预检。先核对文件完整性，再交给构建中心。</p>}
  {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
  {check&&<div className="flex flex-col gap-sm" role="status"><div className="flex flex-wrap items-center gap-sm"><StatusBadge tone={check.registration_matches===false?'warning':passed?'success':'danger'}>{check.registration_matches===false?'登记已变更，需重新预检':passed?(historical?'上次预检通过':'本次预检通过'):(historical?'上次预检失败':'预检失败')}</StatusBadge><span className="text-label-small text-muted-foreground">{new Date(check.checked_at).toLocaleString('zh-CN',{hour12:false})}</span></div>{check.issue&&<><p className="text-body-small font-medium">{check.issue.title}</p><p className="text-body-small">{check.issue.action}</p></>}<p className="text-label-small text-muted-foreground">{check.notice}</p></div>}
  {preparation&&preparation.selected_input_id===identity&&<p role="status" className="text-body-small">{preparation.detail}</p>}{detail&&<>{route&&<div className="text-body-small"><p className="font-medium">{route.category_label} · {route.label}</p><p className="text-muted-foreground">{route.result}</p><p className="text-label-small text-muted-foreground">需要：{route.requires.join('、')}</p></div>}<div className="flex flex-wrap gap-sm"><Button size="sm" variant={passed?'outline':'default'} disabled={busy} onClick={inspect}>{busy?'正在预检…':'执行预检'}</Button>{showBuild&&target.space&&(inactive?<Button size="sm" disabled>资料已停用或归档</Button>:<Button asChild size="sm" variant={passed?'default':'outline'}><a href={preparation?.selected_input_id===identity?recordLink(preparation.next_action.module,preparation.next_action.values):recordLink('build',{space:target.space,input:identity,tab:'tasks',...(batchId?{batch:batchId}:{})})}>{preparation?.selected_input_id===identity?preparation.next_action.label:'用于构建'}</a></Button>)}</div>{inactive&&<p className="text-body-small text-muted-foreground">此资料保留历史记录，当前不能新建构建任务。</p>}{!check&&<p className="text-label-small text-muted-foreground">预检为文件核对；构建提交会重新检查资料和批次，不代表精度验收。</p>}
   <details className="data-technical-details"><summary>资料技术信息</summary><dl className="grid gap-sm text-body-small"><div><dt className="text-muted-foreground">支持格式</dt><dd>{detail.supported_format}</dd></div><div><dt className="text-muted-foreground">登记数量</dt><dd>{inputCounts(detail)}</dd></div><div><dt className="text-muted-foreground">封存来源</dt><dd className="break-all">{detail.snapshot}</dd></div>{detail.tracking&&<div><dt className="text-muted-foreground">轨迹来源</dt><dd className="break-all">{detail.tracking}</dd></div>}</dl>{detail.registration_ref&&(detail.registration_ref.method==='uploaded_package'?<p className="text-label-small text-muted-foreground break-all">上传资料包 · {detail.registration_ref.actor}<br/>SHA-256 {detail.registration_ref.package_sha256}</p>:<p className="text-label-small text-muted-foreground break-words">登记来源：{detail.registration_ref.source_id} · 来源配置修订 {detail.registration_ref.settings_revision} · {detail.registration_ref.actor}</p>)}<p className="text-label-small text-muted-foreground">{detail.limitations.join('；')}。</p>{check?.sequence&&<p className="text-label-small text-muted-foreground">预检记录 #{check.sequence} · {check.actor}。历史结果不代表当前文件状态。</p>}</details>
  </>}
 </section>;
}
