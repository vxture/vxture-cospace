import {useUnsavedNavigation,runGuarded,navigateSafely} from './unsaved-navigation';
import React,{useEffect,useState} from 'react';
import {Button,Field,FieldLabel,Input,NativeSelect,Textarea,Separator,StatusBadge} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {useRecordNavigation,recordLink} from './record-navigation';

type Space={id:string;name:string;description:string;project_id:string;address?:string;location?:{longitude:number;latitude:number;crs:'WGS84'|'GCJ02'}|null};
type Event={revision:number;actor:string;changed_at:string;reason:string;before:Pick<Space,'name'|'description'|'address'|'location'>;after:Pick<Space,'name'|'description'|'address'|'location'>};
type Settings={space:Space;revision:number;can_manage:boolean;history:Event[]};
export function SpaceSettings(){
 const target=useRecordNavigation();
 const [spaces,setSpaces]=useState<Space[]>([]),[data,setData]=useState<Settings|null>(null);
 const [name,setName]=useState(''),[description,setDescription]=useState(''),[reason,setReason]=useState('');
 const [address,setAddress]=useState(''),[longitude,setLongitude]=useState(''),[latitude,setLatitude]=useState(''),[crs,setCrs]=useState<'WGS84'|'GCJ02'>('WGS84');
 function readLocation(space:Space){setAddress(space.address||'');setLongitude(space.location?String(space.location.longitude):'');setLatitude(space.location?String(space.location.latitude):'');setCrs(space.location?.crs||'WGS84');}
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [refresh,setRefresh]=useState(0);
 useEffect(()=>{let active=true;fetch(`${endpoint}/api/spaces`,{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('空间目录暂不可用');const body=await r.json();if(active)setSpaces(body.spaces);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[refresh]);
 useEffect(()=>{let active=true;setData(null);setNotice('');setError('');setReason('');
  if(!target.space)return;
  setLoading(true);
  fetch(`${endpoint}/api/space-settings?`+new URLSearchParams({space_id:target.space}),{cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'无权查看此空间配置。':'空间配置暂不可用，请重试。');
   const body:Settings=await r.json();if(active){setData(body);setName(body.space.name);setDescription(body.space.description);readLocation(body.space);}
  }).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
 },[target.space,refresh]);
 async function save(e?:React.FormEvent){e?.preventDefault();if(!data||busy)return false;setBusy(true);setError('');setNotice('');
  try{const r=await fetch(`${endpoint}/api/space-settings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:data.space.id,expected_revision:data.revision,name:name.trim(),description:description.trim(),address:address.trim(),location:longitude.trim()&&latitude.trim()?{longitude:Number(longitude),latitude:Number(latitude),crs}:null,reason:reason.trim()})});
   if(!r.ok)throw Error(r.status===409?'配置已被其他人修改，请重新读取后核对。':r.status===403?'当前无管理权限，未保存。':'保存失败，请稍后重新读取配置确认。');
   const body:Settings=await r.json();setData(body);setName(body.space.name);setDescription(body.space.description);readLocation(body.space);setReason('');
   setSpaces(old=>old.map(s=>s.id===body.space.id?{...s,...body.space}:s));setNotice('已保存到服务端，空间目录将显示新信息。');
   return true;
  }catch(e){setError(e instanceof Error?e.message:'保存失败');return false;}finally{setBusy(false);}
 }
 const dirty=!!data&&(name.trim()!==data.space.name||description.trim()!==data.space.description||address.trim()!==(data.space.address||'')||longitude!==(data.space.location?String(data.space.location.longitude):'')||latitude!==(data.space.location?String(data.space.location.latitude):'')||crs!==(data.space.location?.crs||'WGS84'));
 useUnsavedNavigation(dirty,'场景信息',{discard:()=>{if(data){setName(data.space.name);setDescription(data.space.description);readLocation(data.space);}setReason('');},save:()=>save(),canSave:!busy&&!!data?.can_manage&&!!reason.trim()&&!!name.trim()});
 return <div className="flex flex-col gap-xl" aria-label="空间基本配置">
  <div className="flex flex-wrap items-center justify-between gap-md"><div><h2 className="text-heading-2">空间基本信息</h2><p className="mt-sm text-body-small text-muted-foreground">按授权空间保存。名称与用途描述用于目录展示。</p></div><Button variant="outline" disabled={busy||loading} onClick={()=>void runGuarded(()=>setRefresh(v=>v+1))}>重新读取配置</Button></div>
  <Field><FieldLabel htmlFor="settings-space">选择空间</FieldLabel><NativeSelect id="settings-space" disabled={busy} value={target.space} onChange={e=>{const id=e.target.value;e.target.value=target.space;void navigateSafely(recordLink('settings',{space:id}));}}><option value="" disabled>请选择授权空间</option>{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect></Field>
  {loading&&<p role="status">正在读取空间配置…</p>}
  {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
  {notice&&<p role="status" className="text-body-small text-primary">{notice}</p>}
  {!target.space&&<p className="text-body-small text-muted-foreground">选择空间后查看配置。空间管理员可修改基本信息。</p>}
  {data&&<><div className="flex flex-wrap items-center gap-md"><StatusBadge tone={data.can_manage?'info':'neutral'}>{data.can_manage?'可管理':'只读'}</StatusBadge><span className="text-label-small text-muted-foreground">修订 {data.revision} · {data.space.id}</span></div>
   <form onSubmit={save} className="flex flex-col gap-lg"><Field><FieldLabel htmlFor="settings-name">空间名称</FieldLabel><Input id="settings-name" value={name} maxLength={100} required disabled={!data.can_manage||busy} onChange={e=>setName(e.target.value)}/></Field><Field><FieldLabel htmlFor="settings-description">用途描述</FieldLabel><Textarea id="settings-description" value={description} maxLength={500} disabled={!data.can_manage||busy} onChange={e=>setDescription(e.target.value)}/></Field>
    <Field><FieldLabel htmlFor="settings-address">物理空间地址</FieldLabel><Input id="settings-address" value={address} maxLength={500} disabled={!data.can_manage||busy} onChange={e=>setAddress(e.target.value)} placeholder="填写场景实际所在地址"/></Field>
    <div className="grid grid-cols-1 gap-md md:grid-cols-3"><Field><FieldLabel htmlFor="settings-longitude">经度</FieldLabel><Input id="settings-longitude" type="number" step="any" min={-180} max={180} required={!!latitude} value={longitude} disabled={!data.can_manage||busy} onChange={e=>setLongitude(e.target.value)} placeholder="未登记"/></Field><Field><FieldLabel htmlFor="settings-latitude">纬度</FieldLabel><Input id="settings-latitude" type="number" step="any" min={-90} max={90} required={!!longitude} value={latitude} disabled={!data.can_manage||busy} onChange={e=>setLatitude(e.target.value)} placeholder="未登记"/></Field><Field><FieldLabel htmlFor="settings-crs">坐标系</FieldLabel><NativeSelect id="settings-crs" value={crs} disabled={!data.can_manage||busy} onChange={e=>setCrs(e.target.value as 'WGS84'|'GCJ02')}><option value="WGS84">WGS84（原始经纬度）</option><option value="GCJ02">GCJ02（高德坐标）</option></NativeSelect></Field></div><p className="text-body-small text-muted-foreground">仅登记场景的地图锚点；不改变模型坐标。WGS84 在地图显示时通过高德转换，原始登记值保留。</p>
    {data.can_manage&&<><Field><FieldLabel htmlFor="settings-reason">修改原因</FieldLabel><Input id="settings-reason" value={reason} maxLength={500} required disabled={busy} placeholder="说明本次修改的目的" onChange={e=>setReason(e.target.value)}/></Field><div className="flex justify-end"><Button type="submit" disabled={busy||!dirty||!name.trim()||!reason.trim()}>{busy?'保存中…':'保存空间信息'}</Button></div></>}
   </form><Separator/><p className="text-body-small text-muted-foreground">此处更新空间目录的名称和用途描述。地址和地图锚点可在此登记；资料、本体与发布设置请前往对应模块。</p>
   {data.can_manage&&<section className="flex flex-col gap-md" aria-label="空间配置修改历史"><h3 className="text-body-small font-medium">修改历史</h3>{!data.history.length?<p className="text-body-small text-muted-foreground">暂无修改记录。</p>:data.history.slice().reverse().map(item=><article key={item.revision} className="rounded-md border border-border p-lg text-body-small"><div className="flex flex-wrap justify-between gap-sm"><span>修订 {item.revision} · {item.actor}</span><time className="text-muted-foreground" dateTime={item.changed_at}>{new Date(item.changed_at).toLocaleString('zh-CN',{hour12:false})}</time></div><p className="mt-sm break-words">{item.reason}</p><dl className="mt-md grid grid-cols-1 gap-sm text-muted-foreground"><div><dt>名称</dt><dd className="break-words">{item.before.name} → {item.after.name}</dd></div><div><dt>用途描述</dt><dd className="whitespace-pre-wrap break-words">{item.before.description||'（空）'} → {item.after.description||'（空）'}</dd></div>{(item.before.address!==undefined||item.after.address!==undefined)&&<div><dt>物理空间地址</dt><dd>{item.before.address||'（未登记）'} → {item.after.address||'（未登记）'}</dd></div>}{(item.before.location!==undefined||item.after.location!==undefined)&&<div><dt>地图锚点</dt><dd>{item.before.location?`${item.before.location.longitude}, ${item.before.location.latitude} (${item.before.location.crs})`:'（未登记）'} → {item.after.location?`${item.after.location.longitude}, ${item.after.location.latitude} (${item.after.location.crs})`:'（未登记）'}</dd></div>}</dl></article>)}</section>}
  </>}
 </div>;
}
