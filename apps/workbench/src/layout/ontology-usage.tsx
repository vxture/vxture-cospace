import React,{useEffect,useState} from 'react';
import {Button,NativeSelect} from '@vxture/design-system';
import {useRecordNavigation} from './record-navigation';
type Ref={ontology_id:string;version:string;sha256:string};
type Report={profile:string;space_id:string;ontology_ref:Ref;status:string;total:number;offset:number;next_offset:number|null;observed_at:string;items:{id:string;kind:string;href:string}[]};
const same=(a:Ref,b:Ref)=>a.ontology_id===b.ontology_id&&a.version===b.version&&a.sha256===b.sha256;
export function OntologyUsage({endpoint,reference,chooseScene=true}:{endpoint:string;reference:Ref;chooseScene?:boolean}){
 const target=useRecordNavigation();
 const [spaces,setSpaces]=useState<{id:string;name:string}[]>([]),[offset,setOffset]=useState(0),[revision,setRevision]=useState(0);
 const [state,setState]=useState<{key:string;report?:Report;error?:string}|null>(null),[sceneError,setSceneError]=useState('');
 const space=target.space;
 const key=JSON.stringify([space,reference,offset,revision]);
 const current=state?.key===key?state:null;
 useEffect(()=>{const controller=new AbortController();fetch(`${endpoint}/api/spaces`,{cache:'no-store',signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('场景列表暂不可读。');return r.json();}).then(body=>{if(!controller.signal.aborted)setSpaces(body.spaces);}).catch(e=>{if(!controller.signal.aborted)setSceneError(e.message);});return()=>controller.abort();},[endpoint,revision]);
 useEffect(()=>{
  const controller=new AbortController();setState(null);
  if(!space)return()=>controller.abort();
  const query=new URLSearchParams({space_id:space,ontology_id:reference.ontology_id,version:reference.version,sha256:reference.sha256,offset:String(offset),limit:'20'});
  fetch(`${endpoint}/api/ontology-usage?${query}`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'当前身份无权查询此场景的规则引用。':'引用暂不可读，请核对场景权限和固定规则后刷新。');
   const report:Report=await r.json();
   if(report.profile!=='cospace.scene-ontology-usage/0.1'||report.space_id!==space||!same(report.ontology_ref,reference)||report.offset!==offset)throw Error('查询响应与所选场景或规则不一致。');
   if(!controller.signal.aborted)setState({key,report});
  }).catch(e=>{if(!controller.signal.aborted)setState({key,error:e.message});});
  return()=>controller.abort();
 },[key,endpoint]);
 return <section aria-label="单场景规则引用" className="flex min-w-0 flex-col gap-md border border-border rounded-md p-md"><h2>单场景规则引用 · V{reference.version}</h2><p className="break-all">固定摘要：{reference.sha256}</p>{chooseScene?<NativeSelect aria-label="选择引用查询场景" value={space} onChange={e=>{const params=new URLSearchParams(location.hash.split('?')[1]||'');params.set('space',e.target.value);location.hash='ontology?'+params;setOffset(0);}}><option value="">请选择一个场景</option>{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect>:<p>查询场景：{spaces.find(s=>s.id===space)?.name||space||'请在上方选择场景'}</p>}{sceneError&&<p role="alert">{sceneError}</p>}<Button variant="outline" size="sm" disabled={!space} onClick={()=>setRevision(v=>v+1)}>刷新场景引用</Button>{current?.error&&<p role="alert">{current.error}</p>}{space&&!current&&<p role="status">正在读取场景引用…</p>}{current?.report&&<><p>{current.report.status==='partial'?'查询不完整，不能据此判断无引用。':'已读取本次单场景元数据范围。'} 发现 {current.report.total} 条引用。</p><p>观察时间：{new Date(current.report.observed_at).toLocaleString('zh-CN',{hour12:false})}</p>{current.report.items.map(item=><a className="break-all" key={item.kind+item.id} href={item.href}>{item.kind==='candidate'?'候选':'固定发布'} · {item.id}</a>)}<div className="flex gap-md"><Button size="sm" variant="outline" disabled={!offset} onClick={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><Button size="sm" variant="outline" disabled={current.report.next_offset===null} onClick={()=>setOffset(current.report!.next_offset!)}>下一页</Button></div></>}<p>仅核对指定场景的候选及固定发布元数据；刷新和翻页可能观察到变化。不代表全局无人使用、实例兼容或可以安全迁移，不自动改选或发布。</p></section>;
}
