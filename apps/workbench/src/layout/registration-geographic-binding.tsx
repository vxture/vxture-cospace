import React,{useState} from 'react';
import {Button,Drawer,Input,NativeSelect} from '@vxture/design-system';
import type {RegistrationInput} from './registration-preview-data';
export type GeographicBinding={adapter:'wgs84_local_enu/1';target_frame_id:string;longitude_deg:number;latitude_deg:number;ellipsoidal_height_m:number;realization:string;coordinate_epoch:number;evidence_ref:string};

export function RegistrationGeographicBinding({input,binding,enabled,onClose,onApply}:{input:RegistrationInput;binding:GeographicBinding|null;enabled:boolean;onClose:()=>void;onApply:(document:RegistrationInput,binding:GeographicBinding|null)=>void}){
 const [longitude,setLongitude]=useState(binding?String(binding.longitude_deg):''),[latitude,setLatitude]=useState(binding?String(binding.latitude_deg):''),[height,setHeight]=useState(binding?String(binding.ellipsoidal_height_m):''),[epoch,setEpoch]=useState(binding?String(binding.coordinate_epoch):''),[realization,setRealization]=useState(binding?.realization||'WGS84(G2139)'),[evidence,setEvidence]=useState(binding?.evidence_ref||''),[confirmed,setConfirmed]=useState(false);
 const valid=enabled&&confirmed&&[longitude,latitude,height,epoch].every(n=>n.trim()!==''&&Number.isFinite(Number(n)))&&Math.abs(Number(longitude))<=180&&Math.abs(Number(latitude))<89&&Number(height)>=-12000&&Number(height)<=100000&&Number(epoch)>=1984&&Number(epoch)<=2100&&evidence.trim();
 return <Drawer open onClose={onClose} side="right" width="md" title="地理基准" description="有测量依据的 WGS84 局部 ENU · 原点不是场景入口位置" closeLabel="关闭地理基准" footer={<div className="scene-registration-footer"><Button size="sm" variant="outline" onClick={onClose}>取消</Button><Button size="sm" disabled={!valid} onClick={()=>onApply({...input,target:{...input.target,kind:'engineering',horizontal_reference:'WGS84 local ENU',vertical_reference:'WGS84 local ENU up'}},{adapter:'wgs84_local_enu/1',target_frame_id:input.target.frame_id,longitude_deg:Number(longitude),latitude_deg:Number(latitude),ellipsoidal_height_m:Number(height),realization,coordinate_epoch:Number(epoch),evidence_ref:evidence})}>核对基准</Button></div>}>
  <div className="scene-registration-form">{!enabled&&<p role="status">管理员尚未启用此适配器，请在部署配置中完成启用。</p>}
   <p>目标点坐标须来自以此原点建立的米制切平面：E 东、N 北、U 局部法线上向。U 不是绝对椭球高；转换后另计算椭球高。首版范围限制为原点周围 20 km。</p>
   <label><span>WGS84 实现</span><NativeSelect value={realization} onChange={event=>setRealization(event.target.value)}>{['WGS84(G1762)','WGS84(G2139)','WGS84(G2296)'].map(n=><option key={n}>{n}</option>)}</NativeSelect></label>
   {([{title:'坐标历元（十进制年）',value:epoch,set:setEpoch},{title:'原点经度（°）',value:longitude,set:setLongitude},{title:'原点纬度（°）',value:latitude,set:setLatitude},{title:'原点椭球高（m）',value:height,set:setHeight}]).map(field=><label key={field.title}><span>{field.title}</span><Input type="number" step="any" value={field.value} onChange={event=>field.set(event.target.value)} aria-label={field.title}/></label>)}
   <label><span>原点与基准测量依据</span><Input maxLength={160} value={evidence} onChange={event=>setEvidence(event.target.value)}/></label>
   <label className="scene-registration-check"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/><span>确认现有目标控制点与转换参数属于上述局部 ENU 基准，未将投影坐标、正高或场景入口坐标代入。</span></label>
   {binding&&<Button size="sm" variant="outline" onClick={()=>onApply(input,null)}>移除地理适配资料</Button>}
  </div>
 </Drawer>;
}
