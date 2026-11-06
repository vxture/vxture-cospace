import React,{useEffect,useState} from 'react';
import {Button,Input,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter} from '@vxture/design-system';
import {Plus} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {businessEndpoint as endpoint} from './business-endpoint';
import {productQuotaMessage} from './product-quota-messages';

type Context={can_create:boolean;workspace_id:string;context_sha256:string};
type Pending={request_id:string;name:string;description:string};
export function CreateSceneButton({onCreated}:{onCreated:(space:string)=>void}){
 const session=usePlatformSession();
 const [context,setContext]=useState<Context|null>(null),[open,setOpen]=useState(false),[busy,setBusy]=useState(false);
 const [name,setName]=useState(''),[description,setDescription]=useState(''),[error,setError]=useState(''),[pending,setPending]=useState<Pending|null>(null);
 const key=`cospace-create-scene:${session?.user?.workspace_id}:${session?.user?.subject}`;
 useEffect(()=>{if(!session)return;const controller=new AbortController();setContext(null);
  fetch(`${endpoint}/api/workspace-scenes`,{signal:controller.signal,cache:'no-store'}).then(async r=>{if(!r.ok)return;const body=await r.json();if(!controller.signal.aborted&&body.workspace_id===session.user?.workspace_id)setContext(body);}).catch(()=>{});
  return()=>controller.abort();
 },[session?.user?.workspace_id,session?.user?.subject]);
 if(!session||!context?.can_create)return null;
 function show(){setError('');let saved:Pending|null=null;try{saved=JSON.parse(sessionStorage.getItem(key)||'null');}catch{}setPending(saved);setName(saved?.name||'');setDescription(saved?.description||'');setOpen(true);}
 async function submit(event:React.FormEvent){event.preventDefault();if(busy||!name.trim())return;setError('');setBusy(true);
  try{
   const current=await fetch(`${endpoint}/api/workspace-scenes`,{cache:'no-store'});if(!current.ok)throw Error('暂时无法核对创建权限，请稍后重试。');
   const checked:Context=await current.json();if(!checked.can_create||checked.workspace_id!==session?.user?.workspace_id)throw Error('当前 Workspace 已无创建权限，请联系管理员。');
   const request=pending||{request_id:crypto.randomUUID().replaceAll('-',''),name:name.trim(),description:description.trim()};
   sessionStorage.setItem(key,JSON.stringify(request));setPending(request);
   const response=await fetch(`${endpoint}/api/workspace-scenes`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...request,context_sha256:checked.context_sha256})});
   const result=await response.json();
   if(!response.ok)throw Error(productQuotaMessage(result.code||result.detail)||(response.status===403?'当前 Workspace 已无创建权限。':response.status===409?'创建条件发生变化，请核对后使用同一请求重试。':'暂时无法确认创建结果，请使用同一请求核对并重试。'));
   if(result.workspace_id!==checked.workspace_id||result.request_id!==request.request_id||!/^space-[a-f0-9]{16}$/.test(result.space_id))throw Error('创建结果无法确认，请使用同一请求重试。');
   sessionStorage.removeItem(key);setPending(null);setOpen(false);onCreated(result.space_id);
  }catch(e){setError(e instanceof Error?e.message:'暂时无法确认创建结果，请重试。');}finally{setBusy(false);}
 }
 return <><Button size="sm" onClick={show}><Plus size={16}/>新建场景</Button><Dialog open={open} onOpenChange={value=>{if(!busy)setOpen(value);}}><DialogContent><DialogHeader><DialogTitle>新建场景空间</DialogTitle><DialogDescription>一个真实场景对应一个场景空间，资料与历史版本在此独立管理。</DialogDescription></DialogHeader><form onSubmit={submit} className="flex flex-col gap-lg"><label className="flex flex-col gap-sm" htmlFor="new-scene-name"><span className="text-body-small">场景名称</span><Input id="new-scene-name" autoFocus required maxLength={100} value={name} onChange={e=>setName(e.target.value)} disabled={busy||!!pending} placeholder="例如：一层设备间与相连走廊"/></label><label className="flex flex-col gap-sm" htmlFor="new-scene-description"><span className="text-body-small">场景说明（选填）</span><Input id="new-scene-description" maxLength={500} value={description} onChange={e=>setDescription(e.target.value)} disabled={busy||!!pending} placeholder="位置、范围或用途"/></label><p className="text-label-small text-muted-foreground">创建后进入数据管理，上传资料包或从已配置来源导入。</p>{pending&&<p role="status" className="text-body-small text-muted-foreground">已保存本次请求。结果未确认时，重试会复用同一场景。</p>}{error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}<DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={()=>setOpen(false)}>暂时关闭</Button><Button type="submit" disabled={busy||!name.trim()}>{busy?'正在核对…':pending?'核对并重试':'创建场景'}</Button></DialogFooter></form></DialogContent></Dialog></>;
}
