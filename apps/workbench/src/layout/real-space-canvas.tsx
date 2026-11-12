import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three/webgpu';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import type {SceneData,XYZ} from './real-space-data';

export type SceneControls={reset:()=>void;focus:(point:XYZ)=>void};
type Props={data:SceneData;view:'human'|'agent';geometry:boolean;markers:boolean;selected:string;select:(id:string)=>void;api:React.RefObject<SceneControls|null>};
// Resolve actual DS paint through the browser, including oklch tokens.
function paint(element:HTMLElement,token:string){const c=document.createElement('canvas');c.width=c.height=1;const ctx=c.getContext('2d')!;ctx.fillStyle=getComputedStyle(element).getPropertyValue(token).trim();ctx.fillRect(0,0,1,1);const b=ctx.getImageData(0,0,1,1).data;return new THREE.Color().setRGB(b[0]/255,b[1]/255,b[2]/255,THREE.SRGBColorSpace);}

export function RealSpaceCanvas({data,view,geometry,markers,selected,select,api}:Props){
 const host=useRef<HTMLDivElement>(null),labels=useRef(new Map<string,HTMLButtonElement>());
 const state=useRef({view,geometry,markers});state.current={view,geometry,markers};
 const [status,setStatus]=useState('初始化三维视图…');
 useEffect(()=>{
  const element=host.current!;let cancelled=false,initialized=false;
  let renderer:THREE.WebGPURenderer|undefined,controls:OrbitControls|undefined,observer:ResizeObserver|undefined;
  const scene=new THREE.Scene();scene.background=paint(element,'--background');
  const camera=new THREE.PerspectiveCamera(42,1,.01,10000);
  const nyu=data.model.axes.join('/')==='right/down/forward';camera.up.set(0,nyu?-1:0,nyu?0:1);
  const bounds=new THREE.Box3(new THREE.Vector3(...data.model.bounds_m[0]),new THREE.Vector3(...data.model.bounds_m[1]));
  const center=bounds.getCenter(new THREE.Vector3()),radius=Math.max(bounds.getSize(new THREE.Vector3()).length()/2,.1);
  const humanGeometry=new THREE.BufferGeometry(),agentGeometry=new THREE.BufferGeometry();
  humanGeometry.setAttribute('position',new THREE.BufferAttribute(data.positions,3));
  humanGeometry.setAttribute('color',new THREE.BufferAttribute(data.colors,3));
  agentGeometry.setAttribute('position',new THREE.Float32BufferAttribute(data.agent_points.flat(),3));
  const human=new THREE.Points(humanGeometry,new THREE.PointsMaterial({size:2.2,sizeAttenuation:false,vertexColors:true}));
  const agent=new THREE.Points(agentGeometry,new THREE.PointsMaterial({size:3,sizeAttenuation:false,color:paint(element,'--primary-text')}));
  scene.add(human,agent);
  function reset(){if(!controls)return;const direction=new THREE.Vector3(nyu?.18:1,nyu?-.12:-1,nyu?-1:.7).normalize();camera.position.copy(center).add(direction);camera.lookAt(center);const rotation=camera.quaternion.clone().invert(),tan=Math.tan(THREE.MathUtils.degToRad(21));let distance=.1;
   for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){const corner=new THREE.Vector3(x,y,z).sub(center).applyQuaternion(rotation);distance=Math.max(distance,Math.abs(corner.x)/(tan*Math.max(camera.aspect,.25))+corner.z,Math.abs(corner.y)/tan+corner.z);}
   distance*=1.08;camera.position.copy(center).addScaledVector(direction,distance);camera.near=Math.max(.001,distance/10000);camera.far=Math.max(100,distance*100);camera.updateProjectionMatrix();controls.target.copy(center);controls.update();}
  async function start(){try{
   renderer=new THREE.WebGPURenderer({antialias:true});await renderer.init();initialized=true;
   if(cancelled){renderer.dispose();return;}
   renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.domElement.setAttribute('aria-label','真实空间三维画布');
   renderer.domElement.dataset.publication=data.model.publication?.id||'';renderer.domElement.dataset.model=data.model.id;renderer.domElement.dataset.cameraUp=camera.up.toArray().join(',');
   renderer.domElement.dataset.humanPoints=String(data.positions.length/3);renderer.domElement.dataset.agentCells=String(data.agent_points.length);
   element.appendChild(renderer.domElement);controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
   observer=new ResizeObserver(()=>{const w=element.clientWidth,h=Math.max(element.clientHeight,1);renderer!.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();});observer.observe(element);
   camera.aspect=element.clientWidth/Math.max(element.clientHeight,1);reset();
   api.current={reset,focus(point){if(!controls)return;const next=new THREE.Vector3(...point),offset=camera.position.clone().sub(controls.target);offset.setLength(Math.max(.5,Math.min(offset.length(),radius*.65)));controls.target.copy(next);camera.position.copy(next).add(offset);controls.update();}};
   renderer.setAnimationLoop(()=>{if(cancelled)return;controls!.update();human.visible=state.current.geometry&&state.current.view==='human';agent.visible=state.current.geometry&&state.current.view==='agent';renderer!.render(scene,camera);
    for(const object of data.objects){const label=labels.current.get(object.object_id);if(!label)continue;const point=new THREE.Vector3(...object.anchor_m).project(camera);const x=(point.x+1)*element.clientWidth/2,y=(1-point.y)*element.clientHeight/2;
     label.hidden=!state.current.markers||point.z< -1||point.z>1||x<0||y<0||x>element.clientWidth||y>element.clientHeight;
     label.style.left=`${x}px`;label.style.top=`${y}px`;
    }
   });
   setStatus((renderer.backend as unknown as {isWebGPUBackend?:boolean}).isWebGPUBackend?'WebGPU':'WebGL2');
  }catch(error){if(!cancelled)setStatus(`三维渲染不可用：${error instanceof Error?error.message:'初始化失败'}`);}}
  void start();
  return()=>{cancelled=true;api.current=null;observer?.disconnect();controls?.dispose();if(initialized){renderer?.setAnimationLoop(null);renderer?.dispose();}renderer?.domElement.remove();humanGeometry.dispose();agentGeometry.dispose();human.material.dispose();agent.material.dispose();};
 },[data,api]);
 return <><div ref={host} className="absolute inset-0 real-space-canvas" data-view={view} data-geometry-visible={geometry}/>
  <div className="absolute inset-0 pointer-events-none" aria-label="空间对象锚点">{markers&&data.objects.map(object=><button key={object.object_id} hidden ref={node=>{if(node)labels.current.set(object.object_id,node);else labels.current.delete(object.object_id);}} className="real-object-marker pointer-events-auto" data-selected={selected===object.object_id} aria-label={`查看对象 ${object.properties.name||object.object_id}`} onClick={()=>select(object.object_id)}><span className="real-object-dot"/><span className="real-object-name">{object.properties.name||object.object_id}</span></button>)}</div>
  <span role="status" className="real-render-status text-label-small text-muted-foreground">{status}</span></>;
}
