import React,{useEffect,useRef} from 'react';
import {createGlobe,type GlobeController,type GlobeCallbacks,type GlobeConfiguration,type GlobeScene,type GlobeLayer} from './index';
export type GlobeCanvasProps=GlobeCallbacks&{configuration:GlobeConfiguration;scenes:GlobeScene[];layers?:GlobeLayer[];satellite:boolean;scrollZoom:boolean;className?:string;onReady?:(controller:GlobeController|null)=>void;onError?:(error:unknown)=>void};
// Engine lifecycle is independent from UI controls, authentication and application routing.
export function GlobeCanvas(props:GlobeCanvasProps){
 const host=useRef<HTMLDivElement>(null),api=useRef<GlobeController|null>(null),latest=useRef(props);latest.current=props;
 useEffect(()=>{if(!host.current)return;try{api.current=createGlobe(host.current,props.configuration,{onState:value=>latest.current.onState?.(value),onCamera:value=>latest.current.onCamera?.(value),onSelect:value=>latest.current.onSelect?.(value)});api.current.setScenes(latest.current.scenes);api.current.setLayers(latest.current.layers||[]);api.current.setDisplay({satellite:latest.current.satellite,scrollZoom:latest.current.scrollZoom});latest.current.onReady?.(api.current);}catch(error){api.current?.destroy();api.current=null;latest.current.onError?.(error);}return()=>{latest.current.onReady?.(null);api.current?.destroy();api.current=null;};},[props.configuration]);
 useEffect(()=>{try{api.current?.setScenes(props.scenes);api.current?.setLayers(props.layers||[]);}catch(error){latest.current.onError?.(error);}},[props.scenes,props.layers]);
 useEffect(()=>{api.current?.setDisplay({satellite:props.satellite,scrollZoom:props.scrollZoom});},[props.satellite,props.scrollZoom]);
 return <div ref={host} className={props.className} style={{position:'absolute',inset:0}} aria-label="三维地球画布"/>;
}
