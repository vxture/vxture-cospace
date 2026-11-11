import {subscribeAppLocation} from './app-router';
import {appLocation} from './app-router';
import React,{useEffect,useState,useSyncExternalStore} from 'react';
import {Button} from '@vxture/design-system';
import {recordLink,useRecordNavigation} from './record-navigation';

type Check={input_id:string;sequence:number;checked_at:string;status:string;actor?:string;registration_matches:boolean;registration_sha256:string;notice?:string;issue?:{title:string;action:string}|null};
type History={input_id:string;items:Check[];next_before_sequence:number|null;current_files_checked:false};
const subscribe=subscribeAppLocation;

export function PreflightHistory({endpoint,identity,revision,embedded=false}:{endpoint:string;identity:string;revision?:number;embedded?:boolean}){
 const target=useRecordNavigation(),hash=useSyncExternalStore(subscribe,()=>appLocation());
 const requested=new URLSearchParams(hash.split('?')[1]||'').get('check')||'';
 const valid=!requested||/^[1-9]\d*$/.test(requested)&&Number.isSafeInteger(Number(requested));
 const [expanded,setExpanded]=useState(false),[cursor,setCursor]=useState<number|null>(null),[refresh,setRefresh]=useState(0);
 const [result,setResult]=useState<{key:string;data:History}|null>(null),[error,setError]=useState('');
 const open=embedded||expanded||!!requested,key=JSON.stringify([endpoint,identity,target.space,requested,cursor,refresh,revision]);
 const data=result?.key===key?result.data:null;
 useEffect(()=>{setCursor(null);if(requested)setExpanded(true);},[identity,target.space,requested]);
 useEffect(()=>{
  setResult(null);setError('');if(!open)return;
  if(!valid){setError('预检记录标识无效，请返回历史列表。');return;}
  const controller=new AbortController();
  const query=new URLSearchParams({space_id:target.space,limit:'20',...(requested?{sequence:requested}:cursor?{before_sequence:String(cursor)}:{})});
  fetch(`${endpoint}/api/inputs/${identity}/preflight/history?${query}`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'当前身份无权读取此资料的预检历史。':'预检历史暂不可读，请重试；不会用最近记录替代。');
   const value:History=await r.json();
   if(value.input_id!==identity||value.current_files_checked!==false||!Array.isArray(value.items)||value.items.some(i=>i.input_id!==identity||!Number.isSafeInteger(i.sequence)||i.sequence<1||requested&&i.sequence!==Number(requested)))throw Error('预检历史与当前资料不一致。');
   if(!controller.signal.aborted)setResult({key,data:value});
  }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'预检历史暂不可读。');});
  return()=>controller.abort();
 },[key,open,valid]);
 const listHref=recordLink('data',{space:target.space,tab:'inputs',input:identity});
 return <section aria-label="预检历史" className="flex flex-col gap-sm border-t border-border pt-md">
  <div className="flex flex-wrap gap-sm items-center">{!embedded&&<h3 className="text-body-small font-medium">预检历史</h3>}{!requested&&!embedded&&<Button size="sm" variant="ghost" onClick={()=>setExpanded(v=>!v)}>{open?'收起预检历史':'查看预检历史'}</Button>}{open&&<Button size="sm" variant="ghost" onClick={()=>{setCursor(null);setRefresh(v=>v+1);}}>刷新历史</Button>}{requested&&<a href={listHref}>返回全部预检历史</a>}</div>
  {open&&<><p className="text-label-small text-muted-foreground">以下为历次保存记录，不重新检查文件，不替代最近预检或构建提交时的实时校验。</p>
   {error?<p role="alert">{error}</p>:!data?<p role="status">正在读取预检历史…</p>:<>
    {!data.items.length&&<p role="status">{requested?'指定预检记录不存在，不自动切换到最近记录。':'此范围暂无保存的预检记录。'}</p>}
    <ol className="flex flex-col gap-sm">{data.items.map(item=><li key={item.sequence} className="flex flex-col gap-sm border border-border rounded-md p-sm">
     <strong>记录 #{item.sequence} · {item.status==='passed'?'检查通过':'检查失败'}</strong>
     <span className="text-body-small">{new Date(item.checked_at).toLocaleString('zh-CN',{hour12:false})}</span>
     <span className="text-body-small">{item.registration_matches?'与当前登记匹配；文件未重检':'登记已变化；此记录仅供追溯'}</span>
     {item.issue&&<p>{item.issue.title} · {item.issue.action}</p>}
     {requested?<details><summary>记录依据</summary><p className="break-all text-label-small">操作者：{item.actor||'未记录'}<br/>登记摘要：{item.registration_sha256}</p><p>{item.notice}</p></details>:<a href={recordLink('data',{space:target.space,tab:'inputs',input:identity,check:String(item.sequence)})}>查看记录 #{item.sequence}</a>}
    </li>)}</ol>
    {!requested&&(cursor!==null||data.next_before_sequence!==null)&&<div className="flex gap-sm"><Button size="sm" variant="ghost" disabled={cursor===null} onClick={()=>setCursor(null)}>返回最新历史</Button><Button size="sm" variant="ghost" disabled={data.next_before_sequence===null} onClick={()=>setCursor(data.next_before_sequence)}>更早记录</Button></div>}
   </>}
  </>}
 </section>;
}
