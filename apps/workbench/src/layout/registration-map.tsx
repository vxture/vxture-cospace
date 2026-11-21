import React,{lazy,Suspense,useEffect,useRef,useState} from 'react';
import {Button,Drawer,NativeSelect} from '@vxture/design-system';
import {displayPoints,loadAmap,type AmapMap,type AmapMarker} from './amap-sdk';
import './scene-registration.css';
const RegistrationGlobe=lazy(()=>import('./registration-globe'));

type ObjectPoint={object_id:string;name:string;available:boolean;reason?:string;longitude_deg?:number;latitude_deg?:number;ellipsoidal_height_m?:number};
export type RegistrationMapData={profile:string;publication_id?:string;space_id?:string;candidate_id?:string;registration_revision:number;status:string;crs:string;objects:ObjectPoint[]};
const reasons:Record<string,string>={registration_not_adopted:'尚未采用核准配准。',geographic_binding_not_recorded:'核准资料未包含已支持的地理基准，请维护有测量依据的适配资料。',registration_adapter_not_enabled:'管理员尚未启用此地理适配器。',registration_outside_valid_time:'核准资料不在有效期内。',registration_not_included:'此发布未纳入配准成果。'};

export function RegistrationMap({url,open,onClose,objectId}:{url:string;open:boolean;onClose:()=>void;objectId?:string}){
 const [data,setData]=useState<RegistrationMapData|null>(null),[error,setError]=useState(''),[mapError,setMapError]=useState(''),[selected,setSelected]=useState(''),[refresh,setRefresh]=useState(0),[mode,setMode]=useState('2D');
 const host=useRef<HTMLDivElement>(null),map=useRef<AmapMap|null>(null),markers=useRef<AmapMarker[]>([]),focus=useRef(new Map<string,[number,number]>());
 useEffect(()=>{if(!open)return;const abort=new AbortController();setData(null);setError('');setSelected('');
  fetch(url,{signal:abort.signal,cache:'no-store'}).then(async r=>{if(!r.ok)throw Error(r.status===403?'当前身份无权查看此成果。':'地图成果暂不可用，请重试。');return r.json();}).then((result:RegistrationMapData)=>{
   if(result.profile!=='cospace.registration-geographic-points/0.1'||!Array.isArray(result.objects))throw Error('地图成果格式不符合合同。');
   if(!abort.signal.aborted){setData(result);setSelected(result.objects.find(p=>p.object_id===objectId)?.object_id||result.objects.find(p=>p.available)?.object_id||result.objects[0]?.object_id||'');}
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();
 },[url,open,refresh,objectId]);
 useEffect(()=>{if(!open||mode!=='2D'||data?.status!=='available'||!host.current)return;let alive=true;setMapError('');
  loadAmap().then(async sdk=>{
   const available=data.objects.filter(p=>p.available);
   const positions=await displayPoints(sdk,available.map(p=>({longitude:p.longitude_deg!,latitude:p.latitude_deg!,crs:'WGS84'})));
   if(!alive||!host.current)return;
   const created=new sdk.Map(host.current,{center:positions[0]||[104,35],zoom:positions.length?18:4,viewMode:'2D'});map.current=created;
   markers.current=available.map((p,i)=>{focus.current.set(p.object_id,positions[i]);const button=document.createElement('button');button.type='button';button.className='registration-map-point';button.textContent=p.name;button.setAttribute('aria-label',`选择地图对象 ${p.name}`);button.onclick=()=>setSelected(p.object_id);return new sdk.Marker({position:positions[i],content:button,anchor:'bottom-center',map:created});});
   created.on('complete',()=>{if(alive&&markers.current.length)created.setFitView(markers.current,false,[40,40,40,40],19);});
  }).catch(e=>{if(alive)setMapError(e.message);});
  return()=>{alive=false;map.current?.destroy();map.current=null;markers.current=[];focus.current.clear();};
 },[open,data,refresh,mode]);
 useEffect(()=>{const point=focus.current.get(selected);if(point)map.current?.setZoomAndCenter(19,point);},[selected]);
 const object=data?.objects.find(p=>p.object_id===selected);
 return <Drawer open={open} onClose={onClose} side="right" width="xl" title="核准对象地图" description={data?`配准修订 ${data.registration_revision||'—'} · ${mode==='3D'?'WGS84 · 绝对椭球高':'WGS84 成果，GCJ02 显示副本'}`:''} closeLabel="关闭对象地图" footer={<div className="scene-registration-footer"><Button size="sm" variant="outline" onClick={()=>setRefresh(n=>n+1)}>重新读取</Button><Button size="sm" onClick={onClose}>关闭</Button></div>}>
  <div className="scene-registration-form">{error&&<p role="alert">{error}</p>}{!data&&!error&&<output>正在读取固定地理成果…</output>}{data?.status!=='available'&&data&&<p>{reasons[data.status]||'当前成果不能定位地图。'}</p>}
   {data?.status==='available'&&<><div role="group" aria-label="对象地图视图"><Button size="sm" variant={mode==='2D'?'secondary':'ghost'} onClick={()=>setMode('2D')}>二维地图</Button><Button size="sm" variant={mode==='3D'?'secondary':'ghost'} onClick={()=>setMode('3D')}>三维地球</Button></div>{mode==='2D'?<div ref={host} hidden={!!mapError} className="registration-map-canvas" role="region" aria-label="核准对象地理地图"/>:<Suspense fallback={<output>正在加载地球…</output>}><RegistrationGlobe data={data} onSelect={setSelected}/></Suspense>}{mode==='2D'&&mapError&&<p role="alert">{mapError} 标准坐标仍可核对。</p>}
    <NativeSelect aria-label="选择地图对象" value={selected} onChange={event=>setSelected(event.target.value)}>{data.objects.map(p=><option value={p.object_id} key={p.object_id}>{p.name}{p.available?'':' · 超出核准范围'}</option>)}</NativeSelect>
    {object&&<section><h3>{object.name}</h3>{object.available?<dl><dt>经度</dt><dd>{object.longitude_deg!.toFixed(9)}°</dd><dt>纬度</dt><dd>{object.latitude_deg!.toFixed(9)}°</dd><dt>椭球高</dt><dd>{object.ellipsoidal_height_m!.toFixed(3)} m</dd></dl>:<p>对象点锚超出核准适用范围，未提供地图位置。</p>}</section>}
    <p>点锚不代表完整实体轮廓；坐标显示位数及底图显示偏差不代表成果实测精度。</p></>}
  </div>
 </Drawer>;
}
