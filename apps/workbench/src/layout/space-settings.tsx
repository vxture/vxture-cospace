import {useUnsavedNavigation,runGuarded,navigateSafely} from './unsaved-navigation';
import React,{useEffect,useState} from 'react';
import {Button,Field,FieldLabel,Input,NativeSelect,Textarea,Separator,StatusBadge} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {useRecordNavigation,recordLink} from './record-navigation';

type Space={id:string;name:string;description:string;project_id:string};
type Event={revision:number;actor:string;changed_at:string;reason:string;before:{name:string;description:string};after:{name:string;description:string}};
type Settings={space:Space;revision:number;can_manage:boolean;history:Event[]};
export function SpaceSettings(){
 const target=useRecordNavigation();
 const [spaces,setSpaces]=useState<Space[]>([]),[data,setData]=useState<Settings|null>(null);
 const [name,setName]=useState(''),[description,setDescription]=useState(''),[reason,setReason]=useState('');
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [refresh,setRefresh]=useState(0);
 useEffect(()=>{let active=true;fetch(`${endpoint}/api/spaces`,{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('空间目录暂不可用');const body=await r.json();if(active)setSpaces(body.spaces);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[refresh]);
 useEffect(()=>{let active=true;setData(null);setNotice('');setError('');setReason('');
  if(!target.space)return;
  setLoading(true);
  fetch(`${endpoint}/api/space-settings?`+new URLSearchParams({space_id:target.space}),{cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'无权查看此空间配置。':'空间配置暂不可用，请重试。');
   const body:Settings=await r.json();if(active){setData(body);setName(body.space.name);setDescription(body.space.description);}
  }).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
 },[target.space,refresh]);
 async function save(e?:React.FormEvent){e?.preventDefault();if(!data||busy)return false;setBusy(true);setError('');setNotice('');
  try{const r=await fetch(`${endpoint}/api/space-settings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:data.space.id,expected_revision:data.revision,name:name.trim(),description:description.trim(),reason:reason.trim()})});
   if(!r.ok)throw Error(r.status===409?'配置已被其他人修改，请重新读取后核对。':r.status===403?'当前无管理权限，未保存。':'保存失败，请稍后重新读取配置确认。');
   const body:Settings=await r.json();setData(body);setName(body.space.name);setDescription(body.space.description);setReason('');
   setSpaces(old=>old.map(s=>s.id===body.space.id?{...s,...body.space}:s));setNotice('已保存到服务端，空间目录将显示新信息。');
   return true;
  }catch(e){setError(e instanceof Error?e.message:'保存失败');return false;}finally{setBusy(false);}
 }
 const dirty=!!data&&(name.trim()!==data.space.name||description.trim()!==data.space.description);
 useUnsavedNavigation(dirty,'场景信息',{discard:()=>{if(data){setName(data.space.name);setDescription(data.space.description);}setReason('');},save:()=>save(),canSave:!busy&&!!data?.can_manage&&!!reason.trim()&&!!name.trim()});
 return <div className="flex flex-col gap-xl" aria-label="空间基本配置">
  <div className="flex flex-wrap items-center justify-between gap-md"><div><h2 className="text-heading-2">空间基本信息</h2><p className="mt-sm text-body-small text-muted-foreground">按授权空间保存。名称与用途描述用于目录展示。</p></div><Button variant="outline" disabled={busy||loading} onClick={()=>void runGuarded(()=>setRefresh(v=>v+1))}>重新读取配置</Button></div>
  <Field><FieldLabel htmlFor="settings-space">选择空间</FieldLabel><NativeSelect id="settings-space" disabled={busy} value={target.space} onChange={e=>{const id=e.target.value;e.target.value=target.space;void navigateSafely(recordLink('settings',{space:id}));}}><option value="" disabled>请选择授权空间</option>{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect></Field>
  {loading&&<p role="status">正在读取空间配置…</p>}
  {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
  {notice&&<p role="status" className="text-body-small text-primary">{notice}</p>}
  {!target.space&&<p className="text-body-small text-muted-foreground">选择空间后查看配置。空间管理员可修改基本信息。</p>}
  {data&&<><div className="flex flex-wrap items-center gap-md"><StatusBadge tone={data.can_manage?'info':'neutral'}>{data.can_manage?'可管理':'只读'}</StatusBadge><span className="text-label-small text-muted-foreground">修订 {data.revision} · {data.space.id}</span></div>
   <form onSubmit={save} className="flex flex-col gap-lg"><Field><FieldLabel htmlFor="settings-name">空间名称</FieldLabel><Input id="settings-name" value={name} maxLength={100} required disabled={!data.can_manage||busy} onChange={e=>setName(e.target.value)}/></Field><Field><FieldLabel htmlFor="settings-description">用途描述</FieldLabel><Textarea id="settings-description" value={description} maxLength={500} disabled={!data.can_manage||busy} onChange={e=>setDescription(e.target.value)}/></Field>
    {data.can_manage&&<><Field><FieldLabel htmlFor="settings-reason">修改原因</FieldLabel><Input id="settings-reason" value={reason} maxLength={500} required disabled={busy} placeholder="说明本次修改的目的" onChange={e=>setReason(e.target.value)}/></Field><div className="flex justify-end"><Button type="submit" disabled={busy||!dirty||!name.trim()||!reason.trim()}>{busy?'保存中…':'保存空间信息'}</Button></div></>}
   </form><Separator/><p className="text-body-small text-muted-foreground">此处更新空间目录的名称和用途描述。资料、本体与发布设置请前往对应模块。</p>
   {data.can_manage&&<section className="flex flex-col gap-md" aria-label="空间配置修改历史"><h3 className="text-body-small font-medium">修改历史</h3>{!data.history.length?<p className="text-body-small text-muted-foreground">暂无修改记录。</p>:data.history.slice().reverse().map(item=><article key={item.revision} className="rounded-md border border-border p-lg text-body-small"><div className="flex flex-wrap justify-between gap-sm"><span>修订 {item.revision} · {item.actor}</span><time className="text-muted-foreground" dateTime={item.changed_at}>{new Date(item.changed_at).toLocaleString('zh-CN',{hour12:false})}</time></div><p className="mt-sm break-words">{item.reason}</p><dl className="mt-md grid grid-cols-1 gap-sm text-muted-foreground"><div><dt>名称</dt><dd className="break-words">{item.before.name} → {item.after.name}</dd></div><div><dt>用途描述</dt><dd className="whitespace-pre-wrap break-words">{item.before.description||'（空）'} → {item.after.description||'（空）'}</dd></div></dl></article>)}</section>}
  </>}
 </div>;
}
