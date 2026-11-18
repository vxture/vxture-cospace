import React,{useEffect,useRef,useState} from 'react';
import {Button,Card,CardContent,CardHeader,CardTitle,Input,NativeSelect} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {useOperationConfirmation} from './operation-confirmation';
import type {Attachment} from './scene-attachments';

const path='/api/scene-ifc/references';
const digest=/^[a-f0-9]{64}$/;
const attachmentId=/^attachment-[a-f0-9]{16}$/;
const statuses={queued:'排队中',running:'解析中',ready:'待启用',failed:'解析失败'} as const;
const errors:Record<string,string>={parse_timeout:'解析超时，请重试或选择更简单的 IFC。',parser_unavailable:'解析服务暂不可用，请稍后重试。',worker_interrupted:'解析服务中断，请重试。',parse_rejected:'无法提取构件，请检查 IFC 后重试。'};
const commandErrors:Record<string,string>={ifc_current_changed:'当前版本已被修改，请刷新后核对。',ifc_queue_full:'当前场景还有待处理任务，请等待后再提交。',ifc_legacy_migration_required:'现有参考使用旧版配置，需要先迁入版本记录，才能安全切换。',ifc_parser_unavailable:'解析暂不可用。如已上传原件，恢复后可从已有 IFC 中选择。'};
type Task={id:string;attachment_id:string;name:string;actor:string;state:keyof typeof statuses;requested_at:string;finished_at?:string;catalog_sha256?:string;error?:string};
type Listing={space_id:string;can_manage:boolean;can_submit?:boolean;revision:number;current:string|null;tasks:Task[];switches:{to:string;actor:string;at:string}[]};
type Preview={space_id:string;task_id:string;catalog_sha256:string;assessment:'unverified';entity_count:number;role_counts:Record<string,number>;geometry_counts:Record<string,number>;sample:{entity_id:string;name:string;role:string;ifc_type:string}[]};
const url=(route:string,params:Record<string,string>)=>`${endpoint}${route}?${new URLSearchParams(params)}`;
const time=(date:string)=>new Date(date).toLocaleString('zh-CN');

export function IfcReferences({space,onActivated}:Readonly<{space:string;onActivated:()=>void}>){
 const [value,setValue]=useState<Listing|null>(null),[items,setItems]=useState<Attachment[]>([]),[adding,setAdding]=useState(false);
 const [choice,setChoice]=useState(''),[upload,setUpload]=useState<File|null>(null),[version,setVersion]=useState<Task|null>(null);
 const [preview,setPreview]=useState<Preview|null>(null),[previewError,setPreviewError]=useState(''),[attachmentError,setAttachmentError]=useState('');
 const [message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[pollError,setPollError]=useState(''),[refresh,setRefresh]=useState(0);
 const live=useRef(true),operation=useRef<AbortController|null>(null);
 const confirm=useOperationConfirmation(`${space}:${value?.revision??0}`);
 useEffect(()=>{live.current=true;return()=>{live.current=false;operation.current?.abort();};},[]);
 useEffect(()=>{
  const controller=new AbortController();let timer:number|undefined;
  async function read(){
   try{
    const result=await fetch(url(path,{space_id:space}),{cache:'no-store',signal:controller.signal});
    if([401,403,404].includes(result.status)){if(!controller.signal.aborted){setValue(null);setPollError('');}return;}
    if(!result.ok)throw new Error('IFC response validation failed');
    const body=await result.json();
    if(body.profile!=='cospace.ifc-reference/0.1'||body.space_id!==space||typeof body.can_manage!=='boolean'||!Number.isSafeInteger(body.revision)||!Array.isArray(body.tasks)||!Array.isArray(body.switches))throw new Error('IFC response validation failed');
    if(body.tasks.some((t:Task)=>!digest.test(t.id)||!attachmentId.test(t.attachment_id)||!Object.hasOwn(statuses,t.state)))throw new Error('IFC response validation failed');
    if(!controller.signal.aborted){setValue(body);setPollError('');if(body.tasks.some((t:Task)=>t.state==='queued'||t.state==='running'))timer=window.setTimeout(()=>void read(),2500);else if(body.can_manage&&body.can_submit!==true)timer=window.setTimeout(()=>void read(),10000);}
   }catch{if(!controller.signal.aborted)setPollError('解析任务暂时无法读取，请重试。');}
  }
  if(space)void read();
  return()=>{controller.abort();if(timer!==undefined)window.clearTimeout(timer);};
 },[space,refresh]);
 useEffect(()=>{
  if(!adding)return;
  const controller=new AbortController();setAttachmentError('');
  fetch(url('/api/scene-attachments',{space_id:space}),{cache:'no-store',signal:controller.signal}).then(async result=>{
   if(!result.ok)throw new Error('IFC response validation failed');
   const body=await result.json();
   if(body.profile!=='cospace.scene-attachments/0.1'||body.space_id!==space||!Array.isArray(body.attachments))throw new Error('IFC response validation failed');
   if(!controller.signal.aborted)setItems(body.attachments.filter((a:Attachment)=>a.space_id===space&&attachmentId.test(a.id)&&a.name.toLowerCase().endsWith('.ifc')));
  }).catch(()=>{if(!controller.signal.aborted)setAttachmentError('已有 IFC 暂时无法读取，仍可选择上传。');});
  return()=>controller.abort();
 },[adding,space]);
 useEffect(()=>{
  setPreview(null);setPreviewError('');if(!version)return;
  const controller=new AbortController();
  fetch(url(`${path}/preview`,{space_id:space,task_id:version.id}),{cache:'no-store',signal:controller.signal}).then(async result=>{
   if(!result.ok)throw new Error('IFC response validation failed');
   const body=await result.json();
   if(body.space_id!==space||body.task_id!==version.id||body.catalog_sha256!==version.catalog_sha256||body.assessment!=='unverified'||!Array.isArray(body.sample))throw new Error('IFC response validation failed');
   if(!controller.signal.aborted)setPreview(body);
  }).catch(()=>{if(!controller.signal.aborted)setPreviewError('无法读取此版本的预览，请重新选择。');});
  return()=>controller.abort();
 },[space,version]);

 async function mutate(work:(signal:AbortSignal)=>Promise<void>){
  if(operation.current)return false;
  const controller=new AbortController();operation.current=controller;setBusy(true);setError('');setMessage('');
  try{await work(controller.signal);if(live.current){setRefresh(x=>x+1);return true;}}
  catch(e){if(live.current&&!controller.signal.aborted){setRefresh(x=>x+1);setError(e instanceof Error?e.message:'操作未确认，请检查后重试。');}}
  finally{operation.current=null;if(live.current)setBusy(false);}
  return false;
 }
 async function post(route:string,body:Record<string,unknown>,signal:AbortSignal){
  const response=await fetch(`${endpoint}${route}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  const result=await response.json();
  if(!response.ok)throw new Error(commandErrors[result.detail]||'操作未完成，请核对资料和权限后重试。');
  if(result.space_id!==space)throw new Error('操作结果与当前场景不一致。');
  return result;
 }
 function queue(retry?:Task){void mutate(async signal=>{
  let id=retry?.attachment_id||choice;
  if(upload&&!retry){
   if(!upload.name.toLowerCase().endsWith('.ifc')||upload.size<=0||upload.size>32*1024*1024)throw new Error('请选择不超过 32 MiB 的 IFC 文件。');
   const response=await fetch(url('/api/scene-attachments',{space_id:space,name:upload.name}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:upload,signal});
   if(!response.ok)throw new Error('原件未成功登记，请检查文件大小、文件名和场景权限。');
   const result=await response.json();
   if(result.attachment?.space_id!==space||!attachmentId.test(result.attachment?.id))throw new Error('原件登记结果与当前场景不一致。');
   id=result.attachment.id;
  }
  if(!attachmentId.test(id))throw new Error('请先选择一个 IFC 原文件。');
  const task=await post(path,{space_id:space,attachment_id:id,retry:!!retry},signal);
  if(!live.current)return;
  setAdding(false);setChoice('');setUpload(null);
  const feedback:Record<string,string>={ready:'已有解析结果，可预览后启用。',failed:'已有失败记录，可在待处理中重试。'};
  setMessage(feedback[task.state]||'已提交解析，可以离开此页面。');
 });}
 function activate(task:Task){
  if(!value||preview?.task_id!==task.id)return;
  const previous=value.tasks.find(t=>t.id===value.current),revision=value.revision;
  const historic=value.switches.some(s=>s.to===task.id);
  const execute=()=>mutate(async signal=>{
   const result=await post(`${path}/activate`,{space_id:space,task_id:task.id,expected_revision:revision},signal);
   if(result.catalog_sha256!==task.catalog_sha256)throw new Error('返回版本与预览不一致，请重新读取。');
   if(live.current){setVersion(null);setMessage('当前 IFC 参考已更新。');onActivated();}
  });
  const currentReference=previous?'当前参考：'+previous.name+'。':'';
  void confirm({verb:historic?'恢复':'启用',target:task.name,consequence:`${currentReference}构件浏览、查询及导出将改用此版本；对象关联和已发布成果不会自动变更。`},execute);
 }
 if(!value?.can_manage&&!pollError)return null;
 const current=value?.tasks.find(t=>t.id===value.current);
 const previous=new Set(value?.switches.map(s=>s.to));
 const pending=value?.tasks.filter(t=>!previous.has(t.id))||[];
 const historic=value?.tasks.filter(t=>previous.has(t.id)&&t.id!==current?.id)||[];
 return <Card className="module-surface"><CardHeader className="flex flex-row flex-wrap items-center justify-between gap-md"><CardTitle>IFC 参考资料</CardTitle>{value?.can_submit&&!adding&&<Button size="sm" onClick={()=>setAdding(true)}>添加 IFC</Button>}</CardHeader><CardContent className="flex flex-col gap-md">
  {current&&<p><strong>当前参考：</strong>{current.name} · 设计资料 · 待核验</p>}
  {pollError&&<div><p role="alert">{pollError}</p><Button size="sm" variant="outline" onClick={()=>setRefresh(n=>n+1)}>重新读取</Button></div>}
  {message&&<output className="block">{message}</output>}{error&&<p role="alert">{error}</p>}
  {value?.can_manage&&value.can_submit!==true&&<output className="block">解析暂不可用，可继续查看已有参考。</output>}
  {adding&&value?.can_manage&&<form className="flex flex-col gap-md" onSubmit={e=>{e.preventDefault();queue();}}>
   <label>选择已有 IFC<NativeSelect value={choice} disabled={busy} onChange={e=>{setChoice(e.target.value);setUpload(null);}}><option value="">选择本场景已上传文件</option>{items.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</NativeSelect></label>
   {attachmentError&&<output className="block">{attachmentError}</output>}
   <label>或上传新 IFC<Input key={choice||'upload'} type="file" accept=".ifc" disabled={busy} onChange={e=>{const file=e.currentTarget.files?.[0]||null;setChoice('');setUpload(file);}}/></label>
   {upload&&<p>已选：{upload.name}</p>}
   <div className="flex justify-end gap-sm"><Button type="button" size="sm" variant="ghost" disabled={busy} onClick={()=>{setAdding(false);setUpload(null);setChoice('');}}>取消</Button><Button type="submit" size="sm" disabled={busy||!value.can_submit||!choice&&!upload}>{busy?'正在提交…':'开始解析'}</Button></div>
  </form>}
  {!!pending.length&&<section><h4>待处理</h4><ul className="flex flex-col gap-sm">{pending.map(t=><li key={t.id} className="flex flex-wrap items-center justify-between gap-sm"><span>{t.name} · {statuses[t.state]}{t.error&&` · ${errors[t.error]||'请重试。'}`}</span>{t.state==='ready'&&<Button size="sm" variant="outline" disabled={busy} onClick={()=>setVersion(t)}>预览</Button>}{t.state==='failed'&&<Button size="sm" variant="outline" disabled={busy||!value?.can_submit} onClick={()=>queue(t)}>重试</Button>}</li>)}</ul></section>}
  {!!historic.length&&<details><summary>版本记录（{historic.length}）</summary><ul className="flex flex-col gap-sm">{historic.map(t=>{const entry=[...(value?.switches||[])].reverse().find(s=>s.to===t.id);return <li key={t.id} className="flex flex-wrap items-center justify-between gap-sm"><span>{t.name} · {entry&&`${time(entry.at)} · ${entry.actor}`}</span><Button size="sm" variant="outline" disabled={busy} onClick={()=>setVersion(t)}>预览</Button></li>;})}</ul></details>}
  {version&&<section className="flex flex-col gap-sm" aria-label="IFC 版本预览"><h4>{version.name} · 预览</h4>{previewError&&<p role="alert">{previewError}</p>}{!previewError&&!preview&&<output className="block">正在读取版本…</output>}{preview&&<><p>{preview.role_counts.level||0} 层 · {preview.role_counts.door||0} 扇门 · {preview.role_counts.stair||0} 部楼梯 · {preview.entity_count} 个实体</p><p>{preview.geometry_counts.extraction_failed||0} 个几何提取失败{!preview.role_counts.space?' · 未提供空间声明':''}</p>{!!preview.sample.length&&<details><summary>查看构件样例</summary><ul>{preview.sample.map(item=><li key={item.entity_id}>{item.name||item.ifc_type} · {item.ifc_type}</li>)}</ul></details>}</>}<div className="flex justify-end gap-sm"><Button variant="ghost" size="sm" disabled={busy} onClick={()=>setVersion(null)}>关闭预览</Button><Button size="sm" disabled={busy||!preview||value?.current===version.id} onClick={()=>activate(version)}>{previous.has(version.id)?'恢复为当前参考':'设为当前参考'}</Button></div></section>}
 </CardContent></Card>;
}
