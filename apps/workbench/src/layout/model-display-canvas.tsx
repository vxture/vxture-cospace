import React,{useEffect,useRef,useState} from 'react';
import {Button} from '@vxture/design-system';
import type {SceneData,XYZ} from './real-space-data';
import type {SceneControls} from './real-space-canvas';

const channel='cospace.pointcloud/1';
type Props={data:SceneData|null;view:'human'|'agent';geometry:boolean;markers:boolean;selected:string;select:(id:string)=>void;api:React.RefObject<SceneControls|null>;onPick?:(point:XYZ)=>void;onAccessLost?:()=>void;engineering?:boolean;dual?:boolean;onReady?:()=>void;onFirstFrame?:()=>void;onView?:(view:'human'|'agent')=>void;focus?:XYZ};
export function ModelDisplayCanvas({data,view,geometry,markers,selected,select,api,onPick,onAccessLost,engineering=false,dual=false,onReady,onFirstFrame,onView,focus}:Props){
 const frame=useRef<HTMLIFrameElement>(null),host=useRef<HTMLDivElement>(null),session=useRef(crypto.randomUUID()),initialized=useRef(false),runtimeReady=useRef(false),activeDisplay=useRef('');
 const labels=useRef(new Map<string,HTMLButtonElement>()),latest=useRef({data,view,geometry,markers,select,onPick,onAccessLost,engineering,dual,onReady,onFirstFrame,onView,focus});latest.current={data,view,geometry,markers,select,onPick,onAccessLost,engineering,dual,onReady,onFirstFrame,onView,focus};
 const [status,setStatus]=useState('正在打开空间…'),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 const [viewFault,setViewFault]=useState('');
 const display=data?.display;
 function post(type:string,values:Record<string,unknown>={}){frame.current?.contentWindow?.postMessage({channel,session:session.current,type,...values},location.origin);}
 function init(){
  const current=latest.current,config=current.data?.display;
  if(config?.state!=='ready')return;
  activeDisplay.current=config.id;
  post('init',{config,agent:current.dual?current.data?.agentDisplay:undefined,dual:current.dual,focus:current.focus});
 }
 function settings(){if(initialized.current){const current=latest.current;post('settings',{view:current.view,geometry:current.geometry,objects:current.data?.objects||[],picking:!!current.onPick,engineering:current.engineering});}}
 useEffect(()=>{settings();},[data?.objects,view,geometry,!!onPick,engineering]);
 useEffect(()=>{
  if(dual&&initialized.current)post('agent-descriptor',{config:data?.agentDisplay});
 },[dual,data?.agentDisplay]);
 useEffect(()=>{
  if(activeDisplay.current&&activeDisplay.current!==display?.id){setAttempt(n=>n+1);return;}
  if(display?.state==='ready'&&runtimeReady.current&&!initialized.current&&!activeDisplay.current)init();
 },[display?.id,display?.state]);
 useEffect(()=>{
  initialized.current=false;runtimeReady.current=false;activeDisplay.current='';session.current=crypto.randomUUID();setError('');setViewFault('');setStatus('正在加载当前视野…');
  function receive(event:MessageEvent){
   if(event.origin!==location.origin||event.source!==frame.current?.contentWindow||event.data?.channel!==channel)return;
   const message=event.data;
   if(message.type==='ready'){runtimeReady.current=true;init();return;}
   if(message.session!==session.current)return;
   if(message.type==='initialized'){
    initialized.current=true;settings();
    if(latest.current.dual)post('agent-descriptor',{config:latest.current.data?.agentDisplay});
    api.current={reset:()=>post('reset'),focus:(point:XYZ)=>post('focus',{point})};latest.current.onReady?.();
   }
   if(message.type==='first-frame'){setStatus('概览已显示 · 正在细化当前视野');latest.current.onFirstFrame?.();if(host.current){host.current.dataset.firstModelMs=String(performance.now());host.current.dataset.firstModelBytes=String(message.transferred);}}
   if(message.type==='frame'){
    if(message.view==='human'||message.view==='agent')latest.current.onView?.(message.view);
    const current=latest.current;
    if(!current.geometry)setStatus('几何已隐藏');
    else if(message.points>0)setStatus(message.diagnostics?.viewReadyMs?'当前视野已就绪':'可浏览 · 正在细化当前视野');
    else if(message.view==='agent'&&message.empty)setStatus('计算表达暂无表面单元');
    else setStatus('正在加载当前视野…');
    setViewFault(message.fault||'');
    if(host.current){host.current.dataset.displayPoints=String(message.points);host.current.dataset.renderedView=message.view;host.current.dataset.viewPending=String(message.pending);host.current.dataset.displayLoading=String(message.loading);host.current.dataset.rangeRequests=String(message.requests);host.current.dataset.transferredBytes=String(message.transferred);host.current.dataset.cachedPoints=String(message.cached_points);}
    if(host.current&&message.diagnostics){for(const [key,value] of Object.entries(message.diagnostics))host.current.dataset[key]=String(value);}
    for(const position of message.labels||[]){const label=labels.current.get(position.id);if(!label)continue;label.hidden=!current.markers||!position.visible;label.style.left=`${position.x*100}%`;label.style.top=`${position.y*100}%`;}
   }
   if(message.type==='pick'&&Array.isArray(message.point)&&message.point.length===3&&message.point.every((v:unknown)=>typeof v==='number'&&Number.isFinite(v)))latest.current.onPick?.(message.point);
   if(message.type==='error'){
    if(message.access){api.current=null;initialized.current=false;frame.current?.removeAttribute('src');}
    if(message.access&&latest.current.onAccessLost)latest.current.onAccessLost();else setError(message.message);
   }
  }
  addEventListener('message',receive);
  if(frame.current)frame.current.src=`/assets/pointcloud-runtime/index.html?attempt=${attempt}`;
  return()=>{removeEventListener('message',receive);initialized.current=false;api.current=null;frame.current?.removeAttribute('src');};
 },[attempt,api]);
 const state=display?.state;
 return <div ref={host} className="absolute inset-0 real-space-canvas" data-provider="potree/1.8.2" data-display-id={display?.id||''}>
  <iframe ref={frame} title="空间模型渐进画布" className="absolute inset-0 h-full w-full border-0"/>
  <div className="absolute inset-0 pointer-events-none" aria-label="空间对象锚点">{markers&&data?.objects.map(object=><button key={object.object_id} hidden ref={node=>{if(node)labels.current.set(object.object_id,node);else labels.current.delete(object.object_id);}} className="real-object-marker pointer-events-auto" data-selected={selected===object.object_id} data-purpose={engineering?object.properties.purpose:undefined} aria-label={`查看对象 ${object.properties.name||object.object_id}`} onClick={()=>select(object.object_id)}><span className="real-object-dot"/><span className="real-object-name">{object.properties.name||object.object_id}</span></button>)}</div>
  {state==='ready'&&<span role="status" className="real-render-status text-label-small text-muted-foreground">{status}</span>}
  {viewFault&&<div role="alert" className="absolute left-lg bottom-xl z-30 text-label-small">{viewFault}<Button variant="ghost" size="sm" onClick={()=>post('retry')}>重试</Button></div>}
  {state&&state!=='ready'&&<div className="real-space-message" role={state==='preparing'?'status':'alert'}><p>{state==='preparing'?'正在准备渐进显示数据…':state==='failed'?'显示数据生成失败，请联系管理员重建显示派生。':'此模型尚未准备渐进显示数据。'}</p></div>}
  {error&&<div className="real-space-message" role="alert"><p>{error}</p><Button variant="outline" size="sm" onClick={()=>{setError('');if(initialized.current)post('retry');else setAttempt(n=>n+1);}}>重试显示</Button></div>}
 </div>;
}
