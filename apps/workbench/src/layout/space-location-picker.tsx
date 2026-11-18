import React,{useEffect,useRef,useState} from 'react';
import {Button,Dialog,DialogContent,DialogDescription,DialogFooter,DialogHeader,DialogTitle} from '@vxture/design-system';
import {loadAmap,type AmapMap,type AmapMarker,type Point} from './amap-sdk';
import {validLocation,type GeographicLocation} from './geographic-location';

export function SpaceLocationPicker({initial,hasHeight,onClose,onPick}:{initial:GeographicLocation|null;hasHeight:boolean;onClose:()=>void;onPick:(point:Point)=>void}){
 const host=useRef<HTMLDivElement>(null);
 const [point,setPoint]=useState<Point>();
 const [loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{
  let active=true,map:AmapMap|undefined,marker:AmapMarker|undefined;
  loadAmap().then(sdk=>{
   if(!active||!host.current)return;
   // Existing GPS coordinates only center the map approximately. The chosen
   // point is always a fresh GCJ02 coordinate from the map's click event.
   const center:Point=initial?[initial.longitude,initial.latitude]:[104,35];
   const instance=new sdk.Map(host.current,{center,zoom:initial?13:4,viewMode:'2D',resizeEnable:true});
   map=instance;
   instance.on('click',({lnglat})=>{
    if(!active)return;
    const longitude=lnglat.getLng(),latitude=lnglat.getLat();
    if(!validLocation({longitude,latitude,crs:'GCJ02'}))return;
    const selected:Point=[Number(longitude.toFixed(6)),Number(latitude.toFixed(6))];
    marker?.setMap(null);
    marker=new sdk.Marker({position:selected});
    marker.setMap(instance);
    setPoint(selected);
   });
  }).catch(()=>{if(active)setError('地图暂不可用，仍可手动填写经纬度。');})
    .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;marker?.setMap(null);map?.destroy();};
 },[initial]);
 return <Dialog open onOpenChange={open=>{if(!open)onClose();}}><DialogContent className="space-location-picker">
  <DialogHeader><DialogTitle>地图选点</DialogTitle><DialogDescription>点击地图选取经纬度（GCJ02）。{hasHeight?'应用新点会清除原高度和基准。':'高度请按测量资料填写。'}</DialogDescription></DialogHeader>
  <div className="space-location-map">
   <div ref={host} className="space-location-map-canvas" aria-label="高德地图选点区域"/>
   {(loading||error)&&<div className="space-location-map-status" role={error?'alert':'status'}>{error||'地图加载中…'}</div>}
  </div>
  <DialogFooter className="space-location-picker-footer">
   <p role="status" className="text-body-small text-muted-foreground">{point?point.map(value=>value.toFixed(6)+'°').join('，'):'尚未选点'}</p>
   <Button type="button" variant="outline" onClick={onClose}>取消</Button>
   <Button type="button" disabled={!point} onClick={()=>{if(point)onPick(point);}}>应用坐标</Button>
  </DialogFooter>
 </DialogContent></Dialog>;
}
