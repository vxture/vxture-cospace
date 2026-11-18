import {FileText,TextAlignLeft,MapPin,ClockCounterClockwise,MapTrifold,PencilSimple} from '@phosphor-icons/react';
import {useUnsavedNavigation,runGuarded} from './unsaved-navigation';
import React,{useEffect,useState} from 'react';
import {Button,Field,FieldLabel,Input,NativeSelect,Textarea,StatusBadge,useToast} from '@vxture/design-system';
import {altitudeLabel,locationFromDraft,validLocation,type GeographicLocation} from './geographic-location';
import {businessEndpoint as endpoint} from './business-endpoint';
import {useRecordNavigation} from './record-navigation';
import {SpaceLocationPicker} from './space-location-picker';
import './space-settings.css';

type Space={scene_code?:string;id:string;name:string;description:string;project_id:string;address?:string;location?:GeographicLocation|null};
type Event={revision:number;actor:string;changed_at:string;reason:string;before:Pick<Space,'name'|'description'|'address'|'location'>;after:Pick<Space,'name'|'description'|'address'|'location'>};
type Section='identity'|'location';
type Settings={editable_fields:string[];space:Space;revision:number;can_manage:boolean;history:Event[]};
const mapSources=['高德地图选点','高德地点搜索','手动输入'];
function locationReference(location?:GeographicLocation|null){
 if(location?.altitude==null)return '—';
 return ({ellipsoid:'椭球高（WGS84）',orthometric:'海拔',unknown:'未明确'})[location.altitude_reference||'unknown'];
}
function InformationFact({label,value,full=false}:{label:string;value?:React.ReactNode;full?:boolean}){
 return <div className={full?'space-information-fact-full':undefined}><dt>{label}</dt><dd>{value||'—'}</dd></div>;
}
function LocationSummary({space}:{space:Space}){
 const location=space.location;
 return <dl className="space-information-facts">
    <InformationFact label="物理空间地址" value={space.address} full/>
    <InformationFact label="经度" value={location&&`${location.longitude}°`}/><InformationFact label="纬度" value={location&&`${location.latitude}°`}/><InformationFact label="高度 Z" value={location?.altitude!=null?`${location.altitude} 米`:null}/>
    <InformationFact label="坐标系" value={location?.crs}/><InformationFact label="高度基准" value={locationReference(location)}/><InformationFact label="坐标来源" value={location?.source}/>
   </dl>;
}
function SettingsSection({section,editable,onEdit,children}:{section:Section;editable:boolean;onEdit:()=>void;children:React.ReactNode}){
 const identity=section==='identity', Icon=identity?TextAlignLeft:MapPin, title=identity?'场景描述':'空间位置';
 return <section className="space-information-section" aria-label={title}>
  <header className="space-information-section-heading material-section-heading"><Icon size={24}/><div className="material-library-heading-copy"><h4>{title}</h4></div>
   {editable&&<Button type="button" variant="outline" size="sm" aria-label={`编辑${title}`} onClick={onEdit}><PencilSimple size={16}/>编辑</Button>}
  </header>
  {children}
 </section>;
}
type InformationRevision={space:string;revision:number};
export function useSpaceInformationRevision(space:string){
 const [value,setValue]=useState<InformationRevision|null>(null);
 return {revision:value?.space===space?value.revision:undefined,onRevisionChange:setValue};
}
export function SpaceSettings({embedded=false,onRevisionChange} :Readonly<{embedded?:boolean;onRevisionChange?:(value:InformationRevision)=>void}>){
 const target=useRecordNavigation(),{toast}=useToast();
 const [data,setData]=useState<Settings|null>(null);
 const [name,setName]=useState(''),[description,setDescription]=useState(''),[reason,setReason]=useState('');
 const [address,setAddress]=useState(''),[longitude,setLongitude]=useState(''),[latitude,setLatitude]=useState(''),[altitude,setAltitude]=useState(''),[crs,setCrs]=useState<'WGS84'|'GCJ02'>('WGS84');
 const [reference,setReference]=useState<NonNullable<GeographicLocation['altitude_reference']>>('unknown'),[locationSource,setLocationSource]=useState('');
 function readLocation(space:Space){setAddress(space.address||'');setLongitude(space.location?String(space.location.longitude):'');setLatitude(space.location?String(space.location.latitude):'');setAltitude(space.location?.altitude!=null?String(space.location.altitude):'');setCrs(space.location?.crs||'WGS84');setReference(space.location?.altitude_reference||'unknown');setLocationSource(space.location?.source||'');}
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const [refresh,setRefresh]=useState(0),[editing,setEditing]=useState<Section|null>(null);
 const [picker,setPicker]=useState<{initial:GeographicLocation|null}|null>(null);
 function discard(){
  if(data){setName(data.space.name);setDescription(data.space.description);readLocation(data.space);}
  setReason('');setError('');setPicker(null);setEditing(null);
 }
 function openPicker(){
  const initial:GeographicLocation={longitude:Number(longitude),latitude:Number(latitude),crs};
  setPicker({initial:longitude.trim()&&latitude.trim()&&validLocation(initial)?initial:null});
 }
 function clearMapSource(){if(mapSources.includes(locationSource))setLocationSource('');}

 useEffect(()=>{let active=true;setData(null);setError('');setReason('');setEditing(null);setPicker(null);setLoading(false);
  if(!target.space)return;
  setLoading(true);
  fetch(`${endpoint}/api/space-settings?`+new URLSearchParams({space_id:target.space}),{cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'无权查看此空间配置。':'空间配置暂不可用，请重试。');
   const body:Settings=await r.json();if(active){setData(body);setName(body.space.name);setDescription(body.space.description);readLocation(body.space);}
  }).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
 },[target.space,refresh]);
 useEffect(()=>{if(data)onRevisionChange?.({space:data.space.id,revision:data.revision});},[data,onRevisionChange]);
 const canEditIdentity=!!data?.editable_fields.includes('name');
 const canEditLocation=!!data?.editable_fields.includes('location');
 const canEdit=editing==='identity'?canEditIdentity:canEditLocation;
 function begin(section:Section){
  if(busy)return;
  void runGuarded(()=>{setReason('');setError('');setPicker(null);setEditing(section);});
 }
 async function save(e?:React.FormEvent){e?.preventDefault();if(!editing||!data||!canEdit||busy)return false;setBusy(true);setError('');
  try{
   const fields=editing==='identity'?{name:name.trim(),description:description.trim()}:
    {address:address.trim(),location:locationFromDraft({longitude,latitude,altitude,crs,reference,source:locationSource})};
   const r=await fetch(`${endpoint}/api/space-settings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:data.space.id,expected_revision:data.revision,section:editing,...fields,reason:reason.trim()})});
   if(!r.ok)throw Error(r.status===409?'配置已被其他人修改，请重新读取后核对。':r.status===403?'当前无管理权限，未保存。':'保存失败，请稍后重新读取配置确认。');
   const body:Settings=await r.json();setData(body);setName(body.space.name);setDescription(body.space.description);readLocation(body.space);setReason('');setEditing(null);
   window.dispatchEvent(new Event('cospace:scene-information-saved'));toast({title:'基本信息已保存',tone:'success'});
   return true;
  }catch(e){setError(e instanceof Error?e.message:'保存失败');return false;}finally{setBusy(false);}
 }
 const identityDirty=!!data&&(name.trim()!==data.space.name||description.trim()!==data.space.description);
 const locationDirty=!!data&&(address.trim()!==(data.space.address||'')||longitude!==(data.space.location?String(data.space.location.longitude):'')||latitude!==(data.space.location?String(data.space.location.latitude):'')||altitude!==(data.space.location?.altitude!=null?String(data.space.location.altitude):'')||crs!==(data.space.location?.crs||'WGS84')||reference!==(data.space.location?.altitude_reference||'unknown')||locationSource.trim()!==(data.space.location?.source||''));
 const dirty=editing==='identity'?identityDirty:editing==='location'&&locationDirty;
 const canSave=!busy&&canEdit&&!!reason.trim()&&(editing!=='identity'||!!name.trim());
 useUnsavedNavigation(dirty,'基本信息',{discard,save:()=>save(),canSave});
 const editActions=<><Field><FieldLabel htmlFor="settings-reason">修改原因</FieldLabel><Input id="settings-reason" value={reason} maxLength={500} required disabled={busy} onChange={e=>setReason(e.target.value)}/></Field>
  <div className="flex justify-end gap-sm"><Button type="button" variant="outline" disabled={busy} onClick={discard}>放弃</Button><Button type="submit" disabled={!dirty||!canSave}>{busy?'保存中…':'保存'}</Button></div>
 </>;
 return <div className="space-information-form flex flex-col gap-xl" aria-label="基本信息">
  <header className="space-information-heading build-stage-heading workspace-section-heading"><div className="workspace-section-heading-copy"><h3><FileText size={20}/>基本信息{data&&!canEditIdentity&&!canEditLocation&&<StatusBadge tone="neutral">只读</StatusBadge>}</h3>{!embedded&&data&&<p className="text-label-small text-muted-foreground">{data.revision?`R${String(data.revision).padStart(2,'0')}`:'历史快照'} · {data.space.scene_code||data.space.id}</p>}</div></header>
  {loading&&<p role="status">正在读取空间配置…</p>}
  {error&&<p role="alert" className="text-body-small text-destructive">{error} <Button type="button" variant="link" size="sm" disabled={busy||loading} onClick={()=>void runGuarded(()=>setRefresh(v=>v+1))}>重新读取</Button></p>}
  {!target.space&&<p className="text-body-small text-muted-foreground">选择场景后查看基本信息。</p>}
  {data&&<>
   <div className="space-information-sections">
    <SettingsSection section="identity" editable={canEditIdentity&&editing!=='identity'&&!busy} onEdit={()=>begin('identity')}>
     {editing==='identity'?<form className="space-information-group" onSubmit={save}>
      <Field><FieldLabel htmlFor="settings-name">空间名称</FieldLabel><Input id="settings-name" value={name} maxLength={100} required disabled={busy} onChange={e=>setName(e.target.value)}/></Field><Field><FieldLabel htmlFor="settings-description">用途描述</FieldLabel><Textarea id="settings-description" value={description} maxLength={500} disabled={busy} onChange={e=>setDescription(e.target.value)}/></Field>
      {editActions}
     </form>:<dl className="space-information-group space-information-summary"><InformationFact label="空间名称" value={data.space.name} full/><InformationFact label="用途描述" value={data.space.description} full/></dl>}
    </SettingsSection>
    <SettingsSection section="location" editable={canEditLocation&&editing!=='location'&&!busy} onEdit={()=>begin('location')}>
     {editing==='location'?<form className="space-information-group" onSubmit={save}>
      <div className="space-information-location-heading"><Button type="button" size="sm" variant="outline" disabled={busy} onClick={openPicker}><MapTrifold size={16}/>地图选点</Button></div>
      <Field><FieldLabel htmlFor="settings-address">物理空间地址</FieldLabel><Input id="settings-address" value={address} maxLength={500} disabled={busy} onChange={e=>setAddress(e.target.value)} placeholder="填写场景实际所在地址"/></Field>
    <div className="space-information-facts"><Field><FieldLabel htmlFor="settings-longitude">经度（°）</FieldLabel><Input id="settings-longitude" type="number" step="any" min={-180} max={180} required={!!latitude||!!altitude} value={longitude} disabled={busy} onChange={e=>{setLongitude(e.target.value);clearMapSource();}} placeholder="未登记"/></Field><Field><FieldLabel htmlFor="settings-latitude">纬度（°）</FieldLabel><Input id="settings-latitude" type="number" step="any" min={-90} max={90} required={!!longitude||!!altitude} value={latitude} disabled={busy} onChange={e=>{setLatitude(e.target.value);clearMapSource();}} placeholder="未登记"/></Field><Field><FieldLabel htmlFor="settings-altitude">高度 Z（米）</FieldLabel><Input id="settings-altitude" type="number" step="any" min={-12000} max={100000} required={false} value={altitude} disabled={busy} onChange={e=>setAltitude(e.target.value)} placeholder="未登记"/></Field></div><div className="space-information-facts"><Field><FieldLabel htmlFor="settings-crs">坐标系</FieldLabel><NativeSelect id="settings-crs" value={crs} disabled={busy} onChange={e=>{setCrs(e.target.value as 'WGS84'|'GCJ02');clearMapSource();}}><option value="WGS84">WGS84（原始经纬度）</option><option value="GCJ02">GCJ02（高德坐标）</option></NativeSelect></Field><Field><FieldLabel htmlFor="settings-altitude-reference">高度基准</FieldLabel><NativeSelect id="settings-altitude-reference" value={reference} disabled={busy||!altitude.trim()} onChange={e=>setReference(e.target.value as NonNullable<GeographicLocation['altitude_reference']>)}><option value="unknown">未明确</option><option value="ellipsoid">椭球高（WGS84）</option><option value="orthometric">海拔（待高程转换）</option></NativeSelect></Field><Field><FieldLabel htmlFor="settings-location-source">坐标来源</FieldLabel><Input id="settings-location-source" value={locationSource} maxLength={160} disabled={busy||!longitude.trim()||!latitude.trim()} onChange={e=>setLocationSource(e.target.value)} placeholder="测量记录、资料名称或定位来源"/></Field></div><p className="text-body-small text-muted-foreground">GCJ02 用于二维地图，三维定位需转换。位置登记不改变模型坐标。</p>
      {editActions}
     </form>:<div className="space-information-group"><LocationSummary space={data.space}/></div>}
    </SettingsSection>
   </div>
   {picker&&editing==='location'&&<SpaceLocationPicker initial={picker.initial} hasHeight={!!altitude.trim()} onClose={()=>setPicker(null)} onPick={point=>{
    setLongitude(String(point.longitude));setLatitude(String(point.latitude));setCrs(point.crs);setLocationSource(point.source||'');setAltitude('');setReference('unknown');setPicker(null);
   }}/>}
   {!editing&&data.can_manage&&<section className="flex flex-col gap-md" aria-label="空间配置修改历史"><header className="space-information-section-heading material-section-heading"><ClockCounterClockwise size={24}/><div className="material-library-heading-copy"><h4>修改记录</h4></div></header>{!data.history.length?<p className="text-body-small text-muted-foreground">暂无修改记录。</p>:data.history.slice().reverse().map(item=><article key={item.revision} className="rounded-md border border-border p-lg text-body-small"><div className="flex flex-wrap justify-between gap-sm"><span>修订 {item.revision} · {item.actor}</span><time className="text-muted-foreground" dateTime={item.changed_at}>{new Date(item.changed_at).toLocaleString('zh-CN',{hour12:false})}</time></div><p className="mt-sm break-words">{item.reason}</p><dl className="mt-md grid grid-cols-1 gap-sm text-muted-foreground"><div><dt>名称</dt><dd className="break-words">{item.before.name} → {item.after.name}</dd></div><div><dt>用途描述</dt><dd className="whitespace-pre-wrap break-words">{item.before.description||'（空）'} → {item.after.description||'（空）'}</dd></div>{(item.before.address!==undefined||item.after.address!==undefined)&&<div><dt>物理空间地址</dt><dd>{item.before.address||'（未登记）'} → {item.after.address||'（未登记）'}</dd></div>}{(item.before.location!==undefined||item.after.location!==undefined)&&<div><dt>地图锚点</dt><dd>{item.before.location?`${item.before.location.longitude}, ${item.before.location.latitude} · ${altitudeLabel(item.before.location)} (${item.before.location.crs}) · ${item.before.location.source||'来源未登记'}`:'（未登记）'} → {item.after.location?`${item.after.location.longitude}, ${item.after.location.latitude} · ${altitudeLabel(item.after.location)} (${item.after.location.crs}) · ${item.after.location.source||'来源未登记'}`:'（未登记）'}</dd></div>}</dl></article>)}</section>}
  </>}
 </div>;
}
