import React,{useEffect,useState} from 'react';
import {Button,Input,NativeSelect} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {usePlatformSession} from './platform-auth';
import {recordLink,useRecordNavigation} from './record-navigation';
import './shared-data-catalog.css';

type Item={key:string;record_id:string;space_id:string;space_name:string;category:string;kind:string;label:string;state:string;href:string};
type Report={profile:string;workspace_id:string;space_id:string|null;status:string;issues:{source:string;space_id:string|null}[];spaces:{id:string;name:string}[];items:Item[];counts:Record<string,number>;total:number;offset:number;next_offset:number|null;observed_at:string};
const labels:Record<string,string>={all:'全部数据',original:'原始与输入',process:'过程数据',result:'成果数据'};
const kinds:Record<string,string>={input:'登记输入',attachment:'配套原文件',batch:'采集批次',preflight:'最近预检记录',job:'构建任务',candidate:'模型候选',human_view:'人视图',agent_view:'智能体视图',publication:'固定发布',offline_package:'离线交付入口'};
const states:Record<string,string>={registered:'已登记',stored_original:'已保存原文件',draft:'整理中',sealed:'已封存',disabled:'已停用',passed:'检查通过',failed:'失败',registration_changed:'登记已变化',queued:'已排队',running:'运行中',interrupted:'已中断',views_failed:'视图待恢复',succeeded:'执行成功',candidate_recorded:'已有候选记录',view_declared:'已声明视图',publication_recorded:'已有发布记录',export_on_request:'按需导出，未生成',unknown:'状态待核查'};
export function SharedDataCatalog(){
 const target=useRecordNavigation(),platform=usePlatformSession();
 const hash=location.hash,params=new URLSearchParams(hash.split('?')[1]||'');
 const category=Object.hasOwn(labels,params.get('category')||'')?params.get('category')!:'all';
 const filter=params.has('filter_space')?params.get('filter_space')||'':params.get('scope')==='all'?'':target.space,search=params.get('search')||'';
 const offset=/^\d+$/.test(params.get('offset')||'')?Number(params.get('offset')):0;
 const [draft,setDraft]=useState(search),[saved,setSaved]=useState<{key:string;report:Report}|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const workspace=platform?.user?.workspace_id||'',key=JSON.stringify([workspace,filter,category,search,offset,revision]);
 const report=saved?.key===key?saved.report:null;
 function navigate(change:Record<string,string>){location.hash=recordLink('data',{space:target.space,scope:'all',category,filter_space:filter,search,offset:'0',...change});}
 useEffect(()=>setDraft(search),[search]);
 useEffect(()=>{
  const controller=new AbortController();setSaved(null);setBusy(true);setError('');
  const query=new URLSearchParams({category,search,offset:String(offset),limit:'50',...(filter?{space_id:filter}:{})});
  fetch(`${businessEndpoint}/api/data-catalog?${query}`,{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error(response.status===403?'当前筛选范围无数据管理权限，请调整范围。':response.status===404?'当前服务尚未提供共用数据目录。':'共用数据目录暂不可用，请重试。');
   const value:Report=await response.json();
   if(value.profile!=='cospace.workspace-data-catalog/0.1'||(workspace&&value.workspace_id!==workspace)||(value.space_id||'')!==filter||!Array.isArray(value.items)||!Array.isArray(value.spaces)||value.items.some(i=>!value.spaces.some(s=>s.id===i.space_id)||!/^#(data|build|delivery)\?/.test(i.href)||new URLSearchParams(i.href.split('?')[1]).get('space')!==i.space_id))throw Error('目录响应与当前范围不一致，请重新读取。');
   if(!controller.signal.aborted)setSaved({key,report:value});
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>controller.abort();
 },[key]);
 return <div className="shared-support-layout"><aside className="support-capabilities"><strong>数据管理</strong><nav aria-label="数据生命周期">{Object.entries(labels).map(([id,label])=><Button key={id} variant={id===category?'secondary':'ghost'} size="sm" onClick={()=>navigate({category:id})} aria-current={id===category?'page':undefined}>{label}</Button>)}</nav></aside><section className="shared-data-catalog" aria-label="共用数据管理">
  <header><div><p>共用支撑 · {workspace||'工程预览'}</p><h1>数据管理</h1><p>统一查看原始输入、过程记录与成果；原有归属、版本及操作权限保持明确。</p></div><Button variant="outline" size="sm" onClick={()=>setRevision(v=>v+1)} disabled={busy}>刷新目录</Button></header>
  <div className="shared-data-toolbar">
   <div className="shared-data-scope"><NativeSelect aria-label="筛选数据所属场景" value={filter} onChange={e=>navigate({filter_space:e.target.value})}><option value="">全部授权场景</option>{filter&&!report?.spaces.some(s=>s.id===filter)&&<option value={filter}>当前筛选场景</option>}{report?.spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect></div>
   <form onSubmit={e=>{e.preventDefault();navigate({search:draft});}}><Input aria-label="搜索共用数据" placeholder="搜索名称、标识或场景" value={draft} onChange={e=>setDraft(e.target.value)} maxLength={100}/><Button size="sm" variant="outline" type="submit">搜索</Button></form></div>
  {filter&&<p className="shared-data-note"><a href={recordLink('data',{space:filter,tab:'inputs'})}>管理此场景资料／导入数据</a></p>}
  {target.space&&<p className="shared-data-note">返回上下文：{target.space} <a href={recordLink('data',{space:target.space,tab:'inputs'})}>进入该场景资料工作面</a></p>}
  <p className="shared-data-note">本目录读取保存的元数据，不校验源文件或快照内容。离线导出不计作已生成或已启用；导入、编辑和构建请进入具体场景工作面。</p>
  {busy&&<p role="status">正在读取共用数据目录…</p>}{error&&<div role="alert"><p>{error}</p><Button variant="outline" size="sm" onClick={()=>setRevision(v=>v+1)}>重试</Button><Button variant="ghost" size="sm" onClick={()=>navigate({filter_space:''})}>查看全部授权范围</Button></div>}
  {report?.status==='partial'&&<p role="alert">部分记录暂不可读取，当前列表不完整。请刷新或进入场景核查。</p>}
  {report&&<><div className="shared-data-list" role="list" aria-label="共用数据列表">{report.items.map(item=><article role="listitem" key={item.key}><div><strong>{item.label}</strong><small>{item.record_id}</small></div><span>{kinds[item.kind]||item.kind}</span><span>{item.space_name}</span><span>{states[item.state]||'状态待核查'} · 元数据记录</span><a href={item.href}>查看记录</a></article>)}</div>{!report.items.length&&<p role="status">{report.status==='partial'?'当前未返回可读取记录，目录仍有读取问题。':report.spaces.length?'此筛选范围暂无数据。':'当前工作区暂无可管理的数据场景。'}</p>}<footer><span>{report.total} 项 · {new Date(report.observed_at).toLocaleString('zh-CN',{hour12:false})} 读取</span><Button size="sm" variant="outline" disabled={!offset} onClick={()=>navigate({offset:String(Math.max(0,offset-50))})}>上一页</Button><Button size="sm" variant="outline" disabled={report.next_offset===null} onClick={()=>navigate({offset:String(report.next_offset)})}>下一页</Button></footer></>}
 </section></div>;
}
