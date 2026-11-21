import React,{useMemo,useRef,useState} from 'react';
import {Button} from '@vxture/design-system';
import {GlobeCanvas} from '@vxture/globe/react';
import type {GlobeController,GlobeLayer,GlobeScene} from '@vxture/globe';
import {useGlobeConfiguration} from './globe-configuration';
import type {RegistrationMapData} from './registration-map';
import 'cesium/Build/Cesium/Widgets/widgets.css';

export default function RegistrationGlobe({data,onSelect}:{data:RegistrationMapData;onSelect:(id:string)=>void}){
 const {configuration,error}=useGlobeConfiguration(),controller=useRef<GlobeController|null>(null),[failure,setFailure]=useState('');
 const objects=data.objects.filter(p=>p.available);
 const binding=useMemo(()=>({spaceId:data.space_id!,...(data.publication_id?{publicationId:data.publication_id}:{})}),[data.space_id,data.publication_id]);
 const scenes=useMemo<GlobeScene[]>(()=>objects.length?[{...binding,name:'核准对象范围',position:[objects[0].longitude_deg!,objects[0].latitude_deg!,objects[0].ellipsoidal_height_m!]}]:[],[data,binding]);
 const layers=useMemo<GlobeLayer[]>(()=>objects.length?[{id:'approved-anchors',binding,features:objects.map(p=>({id:p.object_id,name:p.name,heightMode:'absolute',geometry:{type:'point',position:[p.longitude_deg!,p.latitude_deg!,p.ellipsoidal_height_m!]}}))}]:[],[data,binding]);
 return <div><div className="registration-map-canvas" style={{position:'relative'}}>{configuration&&<GlobeCanvas className="scene-map-canvas" configuration={configuration} scenes={scenes} layers={layers} satellite scrollZoom onReady={api=>{controller.current=api;if(scenes.length)api?.command({type:'fit'});}} onSelect={selection=>{if(selection?.featureId)onSelect(selection.featureId);}} onError={()=>setFailure('三维渲染暂不可用，请检查 WebGL 支持。')}/>}</div>{(error||failure)&&<p role="alert">{error||failure}</p>}<Button size="sm" variant="outline" disabled={!scenes.length||!!error||!!failure} onClick={()=>controller.current?.command({type:'fit'})}>适配对象范围</Button></div>;
}
