import React,{useEffect,useRef,useState} from 'react';
import {Button,Input} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {checkedSurface,type SurfaceRequest,type SurfaceResult} from './ifc-surface-contract';

type Subject={entity_id:string;element_id:string;ifc_type:string;name:string;geometry_status:string};
export function IfcSurfaceQuery(props:Readonly<{space:string;pin:string;frame:string;subjects:Subject[];onSelect:(id:string)=>void}>){
 const [open,setOpen]=useState(false);
 return <section className="flex flex-col gap-md"><Button variant="ghost" size="sm" className="self-start" aria-expanded={open} onClick={()=>setOpen(!open)}>坐标查找构件{open?' · 收起':' · 查询'}</Button>{open&&<QueryForm {...props}/>}</section>;
}
function QueryForm({space,pin,frame,subjects,onSelect}:Readonly<{space:string;pin:string;frame:string;subjects:Subject[];onSelect:(id:string)=>void}>){
 const [coordinates,setCoordinates]=useState(['','','']),[radius,setRadius]=useState('5'),[result,setResult]=useState<SurfaceResult|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const active=useRef<AbortController|null>(null);
 useEffect(()=>()=>active.current?.abort(),[]);
 function invalidate(){active.current?.abort();setBusy(false);setResult(null);setError('');}
 async function submit(event:React.FormEvent){
  event.preventDefault();invalidate();
  const point=coordinates.map(Number),distance=Number(radius);
  if(coordinates.some(v=>!v.trim())||point.some(v=>!Number.isFinite(v)||Math.abs(v)>1000000)||!Number.isFinite(distance)||distance<=0||distance>1000){setError('请填写有效坐标和 0–1000 米内的查询半径。');return;}
  const query:SurfaceRequest={space_id:space,catalog_sha256:pin,frame_id:frame,point_xyz_m:point,max_distance_m:distance};
  const controller=new AbortController();active.current=controller;setBusy(true);
  try{
   const response=await fetch(`${endpoint}/api/scene-ifc/nearest-surface`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(query)});
   if(!response.ok)throw new Error(response.status===409?'资料或坐标版本不一致，或超出本次查询预算。':'查询失败，请检查权限后重试。');
   const value=checkedSurface(await response.json(),query,subjects);
   if(!controller.signal.aborted)setResult(value);
  }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}
  finally{if(!controller.signal.aborted)setBusy(false);}
 }
 return <form onSubmit={e=>void submit(e)} className="flex flex-col gap-md">
  <p className="text-body-small text-muted-foreground">输入 IFC 原坐标（米），查找半径内最近的构件表面。不是点所在房间或通行判断。</p>
  <div className="grid grid-cols-2 md:grid-cols-4 gap-md">{['X','Y','Z'].map((axis,i)=><label key={axis} className="flex flex-col gap-xs text-body-small">{axis}（m）<Input required type="number" step="any" min={-1000000} max={1000000} value={coordinates[i]} onChange={e=>{invalidate();setCoordinates(coordinates.map((v,j)=>j===i?e.target.value:v));}}/></label>)}<label className="flex flex-col gap-xs text-body-small">半径（m）<Input required type="number" step="any" min={0.001} max={1000} value={radius} onChange={e=>{invalidate();setRadius(e.target.value);}}/></label></div>
  <Button type="submit" variant="outline" size="sm" className="self-start" disabled={busy}>{busy?'正在查询…':'查找最近构件'}</Button>
  {error&&<p role="alert" className="text-body-small">{error}</p>}
  {result&&<div role="status" className="flex flex-col gap-sm text-body-small">{result.match?<><strong>{result.match.name||result.match.entity_id}</strong><p>{result.match.ifc_type} · 距离 {result.match.distance_m.toFixed(3)} m</p><Button variant="ghost" size="sm" className="self-start" type="button" onClick={()=>onSelect(result.match!.element_id)}>定位构件</Button></>:<p>{result.status==='geometry_unavailable'?'没有可查询的结构网格。':'指定半径内没有匹配的结构表面。'}</p>}<p className="text-label-small text-muted-foreground">查询了 {result.tested_components} 个结构网格 · {result.without_geometry} 项无几何未参与 · 设计资料待核验</p></div>}
 </form>;
}
