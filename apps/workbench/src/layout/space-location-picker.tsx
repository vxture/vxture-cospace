import React,{useEffect,useRef,useState} from 'react';
import {MagnifyingGlass} from '@phosphor-icons/react';
import {Button,Dialog,DialogContent,DialogDescription,DialogFooter,DialogHeader,DialogTitle,Field,FieldLabel,Input,NativeSelect} from '@vxture/design-system';
import {displayPoints,loadAmap,type AmapMap,type AmapMarker,type AmapSDK,type Point} from './amap-sdk';
import {validLocation,type GeographicLocation} from './geographic-location';

export type PickedLocation=Pick<GeographicLocation,'longitude'|'latitude'|'crs'|'source'>;
type Place={name:string;address:string;point:Point};
const mapUnavailable='地图暂不可用，可直接输入坐标。';
function searchResults(pois:unknown):Place[]{
 if(!Array.isArray(pois))return [];
 return pois.slice(0,8).flatMap(item=>{
  if(typeof item?.name!=='string'||typeof item.location!=='string')return [];
  const parts:string[]=item.location.split(',');
  if(parts.length!==2||parts.some(value=>!value.trim()))return [];
  const [longitude,latitude]=parts.map(Number);
  if(!validLocation({longitude,latitude,crs:'GCJ02'}))return [];
  const address=[item.cityname,item.adname,item.address].filter(value=>typeof value==='string').join(' ');
  return [{name:item.name,address,point:[longitude,latitude] as Point}];
 });
}

export function SpaceLocationPicker({initial,hasHeight,onClose,onPick}:{initial:GeographicLocation|null;hasHeight:boolean;onClose:()=>void;onPick:(point:PickedLocation)=>void}){
 const host=useRef<HTMLDivElement>(null), searchRequest=useRef<AbortController|null>(null);
 const [camera,setCamera]=useState<{map:AmapMap;sdk:AmapSDK}|null>(null);
 const [longitude,setLongitude]=useState(initial?String(initial.longitude):''),[latitude,setLatitude]=useState(initial?String(initial.latitude):'');
 const [crs,setCrs]=useState<GeographicLocation['crs']>(initial?.crs||'GCJ02'),[source,setSource]=useState(initial?.source||'');
 const [mapState,setMapState]=useState('地图加载中…'),[pointStatus,setPointStatus]=useState('');
 const [query,setQuery]=useState(''),[places,setPlaces]=useState<Place[]>([]),[searchStatus,setSearchStatus]=useState(''),[searching,setSearching]=useState(false);
 const point:PickedLocation={longitude:Number(longitude),latitude:Number(latitude),crs,source:source||'手动输入'};
 const valid=!!longitude.trim()&&!!latitude.trim()&&validLocation(point);
 const changed=!initial||point.longitude!==initial.longitude||point.latitude!==initial.latitude||point.crs!==initial.crs;

 function chooseMapPoint([lon,lat]:Point,origin:string){
  setLongitude(String(Number(lon.toFixed(6))));setLatitude(String(Number(lat.toFixed(6))));
  setCrs('GCJ02');setSource(origin);setPointStatus('');
 }
 useEffect(()=>{
  let active=true,map:AmapMap|undefined;
  const timeout=setTimeout(()=>{if(active)setMapState(mapUnavailable);},25000);
  loadAmap().then(sdk=>{
   if(!active||!host.current)return;
   const center:Point=initial?[initial.longitude,initial.latitude]:[104,35];
   const instance=new sdk.Map(host.current,{center,zoom:initial?13:4,viewMode:'2D',resizeEnable:true});
   map=instance;
   instance.on('complete',()=>{if(active){clearTimeout(timeout);setCamera({map:instance,sdk});setMapState('');}});
   instance.on('click',({lnglat})=>{
    const lon=lnglat.getLng(),lat=lnglat.getLat();
    if(active&&validLocation({longitude:lon,latitude:lat,crs:'GCJ02'}))chooseMapPoint([lon,lat],'高德地图选点');
   });
  }).catch(()=>{if(active){clearTimeout(timeout);setMapState(mapUnavailable);}});
  return()=>{active=false;clearTimeout(timeout);map?.destroy();};
 },[initial]);
 useEffect(()=>{
  if(!camera||!longitude.trim()||!latitude.trim())return;
  const coordinate={longitude:Number(longitude),latitude:Number(latitude),crs};
  if(!validLocation(coordinate))return;
  let active=true,marker:AmapMarker|undefined;
  const timer=setTimeout(async()=>{
   try{
    const [position]=crs==='GCJ02'?[[coordinate.longitude,coordinate.latitude] as Point]:await displayPoints(camera.sdk,[coordinate]);
    if(!active)return;
    marker=new camera.sdk.Marker({position});
    marker.setMap(camera.map);camera.map.setZoomAndCenter(Math.max(camera.map.getZoom(),13),position);
    setPointStatus('');
   }catch{if(active)setPointStatus('地图无法定位该坐标，仍可应用原始坐标。');}
  },300);
  return()=>{active=false;clearTimeout(timer);marker?.setMap(null);};
 },[camera,longitude,latitude,crs]);
 useEffect(()=>()=>searchRequest.current?.abort(),[]);

 async function search(){
  if(query.trim().length<2)return;
  searchRequest.current?.abort();
  const request=new AbortController();searchRequest.current=request;
  setSearching(true);setPlaces([]);setSearchStatus('正在搜索…');
  try{
   const response=await fetch('/_AMapService/place-search?'+new URLSearchParams({keywords:query.trim()}),{signal:AbortSignal.any([request.signal,AbortSignal.timeout(15000)])});
   if(!response.ok)throw Error();
   const body=await response.json();
   if(body.status!=='1')throw Error();
   if(request.signal.aborted)return;
   const results=searchResults(body.pois);
   setPlaces(results);setSearchStatus(results.length?'':'没有找到地点，试试加上城市或区县名。');
  }catch{if(!request.signal.aborted)setSearchStatus('地点搜索暂不可用，可点图或输入坐标。');}
  finally{if(!request.signal.aborted)setSearching(false);}
 }

 return <Dialog open onOpenChange={open=>{if(!open)onClose();}}><DialogContent className="space-location-picker">
  <DialogHeader><DialogTitle>地图选点</DialogTitle><DialogDescription>搜索地点、点击地图，或直接输入坐标。</DialogDescription></DialogHeader>
  <div className="space-location-search">
   <Input aria-label="搜索地点" placeholder="输入城市、地址或地点名称" value={query} maxLength={80} onChange={e=>{setQuery(e.target.value);searchRequest.current?.abort();setSearching(false);setPlaces([]);setSearchStatus('');}} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();void search();}}}/>
   <Button type="button" size="lg" variant="outline" disabled={searching||query.trim().length<2} onClick={()=>void search()}><MagnifyingGlass size={16}/>搜索</Button>
  </div>
  {searchStatus&&<p role="status" className="text-body-small text-muted-foreground">{searchStatus}</p>}
  {!!places.length&&<ul className="space-location-results" aria-label="地点搜索结果">{places.map((place,index)=><li key={index}><button type="button" onClick={()=>{chooseMapPoint(place.point,'高德地点搜索');setQuery(place.name);setPlaces([]);}}><strong>{place.name}</strong>{place.address&&<span>{place.address}</span>}</button></li>)}</ul>}
  <div className="space-location-map">
   <div ref={host} className="space-location-map-canvas" aria-label="高德地图选点区域"/>
   {mapState&&<div className="space-location-map-status" role="status">{mapState}</div>}
  </div>
  <div className="space-location-coordinate-fields">
   <Field><FieldLabel htmlFor="picker-longitude">经度（°）</FieldLabel><Input id="picker-longitude" type="number" step="any" min={-180} max={180} value={longitude} onChange={e=>{setLongitude(e.target.value);setSource('');setPointStatus('');}}/></Field>
   <Field><FieldLabel htmlFor="picker-latitude">纬度（°）</FieldLabel><Input id="picker-latitude" type="number" step="any" min={-90} max={90} value={latitude} onChange={e=>{setLatitude(e.target.value);setSource('');setPointStatus('');}}/></Field>
   <Field><FieldLabel htmlFor="picker-crs">输入坐标系</FieldLabel><NativeSelect id="picker-crs" value={crs} onChange={e=>{setCrs(e.target.value as GeographicLocation['crs']);setSource('');setPointStatus('');}}><option value="GCJ02">GCJ02（高德）</option><option value="WGS84">WGS84（GPS）</option></NativeSelect></Field>
  </div>
  <p role="status" className="text-body-small text-muted-foreground">{pointStatus||((longitude||latitude)&&!valid?'请填写有效的经纬度。':'搜索结果与地图点选采用 GCJ02。')}{hasHeight&&changed?' 应用新坐标会清除原高度和基准。':''}</p>
  <DialogFooter className="space-location-picker-footer">
   <Button type="button" size="lg" variant="outline" onClick={onClose}>取消</Button>
   <Button type="button" size="lg" disabled={!valid||!changed} onClick={()=>{if(valid&&changed)onPick(point);}}>应用坐标</Button>
  </DialogFooter>
 </DialogContent></Dialog>;
}
