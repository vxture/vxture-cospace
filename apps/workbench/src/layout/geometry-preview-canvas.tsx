import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three/webgpu';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {Button} from '@vxture/design-system';
import type {PreviewGeometry,XYZ} from './geometry-preview-data';
import {scanFocus} from './build-scan-data';
import {visibleCount,type ProcessPlayback} from './build-process-data';

function brandPaint(element:HTMLElement){const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const context=canvas.getContext('2d')!;context.fillStyle=getComputedStyle(element).getPropertyValue('--primary').trim();context.fillRect(0,0,1,1);const color=context.getImageData(0,0,1,1).data;return new THREE.Color().setRGB(color[0]/255,color[1]/255,color[2]/255,THREE.SRGBColorSpace);}

export type GeometryMarker={id:string;label:string;position:XYZ};
export type GeometryFocus={position:XYZ};
export default function GeometryPreviewCanvas({data,scan,process,onPick,markers,selected,onSelect,focus,anchor:verifiedAnchor}:{data:PreviewGeometry;scan?:React.RefObject<{progress:number}>;process?:React.RefObject<ProcessPlayback>;onPick?:(index:number)=>void;markers?:GeometryMarker[];selected?:string;onSelect?:(id:string)=>void;focus?:GeometryFocus;anchor?:XYZ}){
 const overlay=useRef({markers,focus,verifiedAnchor});overlay.current={markers,focus,verifiedAnchor};
 const markerNodes=useRef(new Map<string,HTMLButtonElement>());
 const pick=useRef(onPick);pick.current=onPick;
 const host=useRef<HTMLDivElement>(null),reset=useRef<()=>void>(()=>{});const [status,setStatus]=useState('初始化显示…');
 useEffect(()=>{
  const el=host.current!;let cancelled=false,ready=false,renderer:THREE.WebGPURenderer|undefined,controls:OrbitControls|undefined,observer:ResizeObserver|undefined;
  setStatus('初始化显示…');const scene=new THREE.Scene();
  const center=new THREE.Vector3(...data.bounds[0]).add(new THREE.Vector3(...data.bounds[1])).multiplyScalar(.5),span=new THREE.Vector3(...data.bounds[1]).sub(new THREE.Vector3(...data.bounds[0])),radius=Math.max(span.length()/2,.01);
  const focus=scan||process?scanFocus(data):null,target=focus?new THREE.Vector3(...focus.center).sub(center):new THREE.Vector3();
  const geometry=new THREE.BufferGeometry(),positions=new Float32Array(data.points.length*3),colors=new Float32Array(data.colors.length*3),color=new THREE.Color();
  data.points.forEach((p,i)=>positions.set([p[0]-center.x,p[1]-center.y,p[2]-center.z],i*3));data.colors.forEach((p,i)=>{color.setRGB(p[0]/255,p[1]/255,p[2]/255,THREE.SRGBColorSpace);colors.set(color.toArray(),i*3);});
  if(scan)geometry.setDrawRange(0,0);
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));const material=new THREE.PointsMaterial({vertexColors:true,size:2.5,sizeAttenuation:false});scene.add(new THREE.Points(geometry,material));
  const selectedGeometry=new THREE.BufferGeometry(),selectedMaterial=new THREE.PointsMaterial({color:0x335cff,size:11,sizeAttenuation:false,depthTest:false});
  selectedGeometry.setAttribute('position',new THREE.Float32BufferAttribute([],3));
  const selectedPoint=new THREE.Points(selectedGeometry,selectedMaterial);selectedPoint.renderOrder=10;selectedPoint.visible=false;scene.add(selectedPoint);
  const axes=new THREE.AxesHelper(radius*.3);if(!scan&&!process)scene.add(axes);
  const nyu=data.axes.join('/')==='right/down/forward';
  const scanColor=scan||process?brandPaint(el):new THREE.Color();
  const scanGeometry=new THREE.BufferGeometry(),scanMaterial=new THREE.MeshBasicMaterial({color:scanColor,transparent:true,opacity:.08,side:THREE.DoubleSide,depthWrite:false});
  const sweepRadius=focus?.radius||radius;
  const wedge:number[]=[];for(let i=0;i<12;i++){const a=(i/12)*.22,b=((i+1)/12)*.22;wedge.push(0,0,0,Math.cos(a)*sweepRadius,Math.sin(a)*sweepRadius,0,Math.cos(b)*sweepRadius,Math.sin(b)*sweepRadius,0);}
  scanGeometry.setAttribute('position',new THREE.Float32BufferAttribute(wedge,3));const beam=new THREE.Mesh(scanGeometry,scanMaterial);if(nyu)beam.rotation.x=-Math.PI/2;
  beam.position.copy(target);
  if(scan)scene.add(beam);
  const glowMaterial=new THREE.PointsMaterial({color:scanColor.clone().lerp(new THREE.Color(0xffffff),.4),size:3.5,sizeAttenuation:false,transparent:true,opacity:.8,depthWrite:false}),glowGeometry=new THREE.BufferGeometry();glowGeometry.setAttribute('position',geometry.getAttribute('position'));const glow=new THREE.Points(glowGeometry,glowMaterial);if(scan||process)scene.add(glow);
  const trailGeometry=new THREE.BufferGeometry(),trailMaterial=new THREE.LineBasicMaterial({color:scanColor,transparent:true,opacity:.65}),trail=new THREE.Line(trailGeometry,trailMaterial);
  const trailPositions=new Float32Array(500*3);trailGeometry.setAttribute('position',new THREE.BufferAttribute(trailPositions,3));trailGeometry.setDrawRange(0,0);
  const markerGeometry=new THREE.BufferGeometry(),markerMaterial=new THREE.LineBasicMaterial({color:scanColor});
  const corners=[[-.12,-.09,.22],[.12,-.09,.22],[.12,.09,.22],[-.12,.09,.22]],markerPoints:number[]=[];
  for(let i=0;i<4;i++)markerPoints.push(0,0,0,...corners[i],...corners[i],...corners[(i+1)%4]);
  markerGeometry.setAttribute('position',new THREE.Float32BufferAttribute(markerPoints,3));const marker=new THREE.LineSegments(markerGeometry,markerMaterial);marker.matrixAutoUpdate=false;marker.visible=false;
  if(process){scene.add(trail,marker);geometry.setDrawRange(0,0);}
  let renderedData:PreviewGeometry|null=process?null:data;
  const camera=new THREE.PerspectiveCamera(42,1,.001,Math.max(radius*100,100));camera.up.set(0,nyu?-1:0,nyu?0:1);
  const projected=new THREE.Vector3(),anchor=new THREE.Vector3(),offset=new THREE.Vector3();
  let lastFocus:GeometryFocus|undefined,lastAnchor:XYZ|undefined;
  function positionMarkers(){
   const state=overlay.current;
   if(state.focus!==lastFocus&&state.focus&&controls){
    anchor.set(...state.focus.position).sub(center);offset.copy(camera.position).sub(controls.target);
    offset.setLength(Math.max(radius*.22,.01));camera.position.copy(anchor).add(offset);controls.target.copy(anchor);controls.update();
   }
   lastFocus=state.focus;
   if(state.verifiedAnchor!==lastAnchor){
    lastAnchor=state.verifiedAnchor;
    selectedPoint.visible=!!lastAnchor;
    if(lastAnchor){selectedGeometry.setAttribute('position',new THREE.Float32BufferAttribute(anchor.set(...lastAnchor).sub(center).toArray(),3));selectedGeometry.computeBoundingSphere();}
   }
   if(!state.markers?.length)return;
   camera.updateMatrixWorld();
   const w=el.clientWidth,h=el.clientHeight;
   for(const item of state.markers){
    const node=markerNodes.current.get(item.id);if(!node)continue;
    projected.set(...item.position).sub(center).project(camera);
    const shown=projected.z>=-1&&projected.z<=1&&Math.abs(projected.x)<1&&Math.abs(projected.y)<1;
    node.hidden=!shown;
    if(shown)node.style.transform=`translate(${(projected.x+1)*w/2}px, ${(1-projected.y)*h/2}px) translate(-50%, -50%)`;
   }
  }
  function choose(event:MouseEvent){
   if(!pick.current||!renderer)return;const rect=renderer.domElement.getBoundingClientRect();
   const x=event.clientX-rect.left,y=event.clientY-rect.top;let best=-1,distance=81,depth=Infinity;
   camera.updateMatrixWorld();
   data.points.forEach((point,i)=>{const p=new THREE.Vector3(point[0]-center.x,point[1]-center.y,point[2]-center.z).project(camera);
    if(p.z< -1||p.z>1)return;const d=((p.x+1)*rect.width/2-x)**2+((1-p.y)*rect.height/2-y)**2;
    if(d<distance||d===distance&&p.z<depth){best=i;distance=d;depth=p.z;}});
   if(best<0)return;
   if(!overlay.current.markers){selectedGeometry.setAttribute('position',new THREE.Float32BufferAttribute([positions[best*3],positions[best*3+1],positions[best*3+2]],3));selectedGeometry.computeBoundingSphere();selectedPoint.visible=true;}
   pick.current(best*data.sampling.stride);
  }
  const fit=(all=true)=>{const latest=process?.current.data,b=latest?.bounds;const fullRadius=b?Math.max(new THREE.Vector3(...b[1]).sub(new THREE.Vector3(...b[0])).length()/2,.01):radius,fullTarget=b?new THREE.Vector3(...b[0]).add(new THREE.Vector3(...b[1])).multiplyScalar(.5).sub(center):new THREE.Vector3();const r=!all&&focus?focus.radius:fullRadius,t=!all&&focus?target:fullTarget;const d=r/Math.sin(THREE.MathUtils.degToRad(21))*Math.max(1,1/camera.aspect)*1.08;camera.position.copy(new THREE.Vector3(1,nyu?-1:-1,nyu?-1:.7).normalize().multiplyScalar(d)).add(t);camera.near=Math.max(d/10000,.00001);camera.far=Math.max(d*100,fullRadius*4,1);camera.updateProjectionMatrix();controls?.target.copy(t);controls?.update();};reset.current=()=>fit();
  void(async()=>{try{renderer=new THREE.WebGPURenderer({antialias:true,alpha:true});await renderer.init();ready=true;if(cancelled){renderer.dispose();return;}renderer.setPixelRatio(Math.min(devicePixelRatio,2));el.appendChild(renderer.domElement);renderer.domElement.setAttribute('aria-label','点云资料三维画布');renderer.domElement.dataset.points=String(data.sampling.count);controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
   renderer.domElement.addEventListener('dblclick',choose);
   const resize=()=>{if(!renderer)return;const w=Math.max(el.clientWidth,1),h=Math.max(el.clientHeight,1);renderer.setSize(w,h);camera.aspect=w/h;fit(!scan&&!process);};observer=new ResizeObserver(resize);observer.observe(el);resize();renderer.setAnimationLoop(()=>{if(!cancelled){
   if(process){
    const current=process.current.data,frame=Math.max(0,Math.min(process.current.frame,current.frames.length-1));
    if(current!==renderedData){
     geometry.dispose();glowGeometry.dispose();
     const pos=new Float32Array(current.points.length*3),col=new Float32Array(current.points.length*3);
     current.points.forEach((p,i)=>pos.set([p[0]-center.x,p[1]-center.y,p[2]-center.z],i*3));
     current.colors.forEach((p,i)=>{color.setRGB(p[0]/255,p[1]/255,p[2]/255,THREE.SRGBColorSpace);col.set(color.toArray(),i*3);});
     geometry.setAttribute('position',new THREE.BufferAttribute(pos,3));geometry.setAttribute('color',new THREE.BufferAttribute(col,3));geometry.computeBoundingSphere();
     glowGeometry.setAttribute('position',geometry.getAttribute('position'));glowGeometry.computeBoundingSphere();
     current.frames.forEach((f,i)=>trailPositions.set([f.pose[0][3]-center.x,f.pose[1][3]-center.y,f.pose[2][3]-center.z],i*3));
     trailGeometry.getAttribute('position').needsUpdate=true;trailGeometry.computeBoundingSphere();renderedData=current;
    }
    const count=visibleCount(current,frame),start=visibleCount(current,frame-1);geometry.setDrawRange(0,count);glowGeometry.setDrawRange(start,count-start);trailGeometry.setDrawRange(0,frame+1);
    const pose=current.frames[frame]?.pose;marker.visible=!!pose;
    if(pose){marker.matrix.set(...pose.flat() as [number,number,number,number,number,number,number,number,number,number,number,number,number,number,number,number]);marker.matrix.setPosition(pose[0][3]-center.x,pose[1][3]-center.y,pose[2][3]-center.z);}
    renderer!.domElement.dataset.visiblePoints=String(count);renderer!.domElement.dataset.currentFrame=String(frame);renderer!.domElement.dataset.trailPoints=String(frame+1);renderer!.domElement.dataset.points=String(current.sampling.count);renderer!.domElement.dataset.cameraPosition=pose?JSON.stringify([pose[0][3],pose[1][3],pose[2][3]]):'';
   }
   if(scan){const progress=scan.current.progress,count=Math.floor(data.points.length*progress);geometry.setDrawRange(0,count);glowGeometry.setDrawRange(Math.max(0,count-180),Math.min(count,180));beam.visible=progress>0&&progress<1;glow.visible=progress>0&&progress<1;const edge=data.points[Math.max(0,count-1)],a=focus?Math.atan2(edge[nyu?2:1]-focus.center[nyu?2:1],edge[0]-focus.center[0]):progress*Math.PI*2-Math.PI;if(nyu)beam.rotation.z=-a;else beam.rotation.z=a;renderer!.domElement.dataset.visiblePoints=String(count);}controls?.update();positionMarkers();renderer?.render(scene,camera);}});setStatus('拖动旋转 · 滚轮缩放 · 右键平移');
  }catch{if(!cancelled)setStatus('三维渲染不可用；仍可核对点数与范围。');}})();
  return()=>{cancelled=true;observer?.disconnect();controls?.dispose();renderer?.domElement.removeEventListener('dblclick',choose);if(ready){renderer?.setAnimationLoop(null);renderer?.dispose();}renderer?.domElement.remove();selectedGeometry.dispose();selectedMaterial.dispose();geometry.dispose();material.dispose();glowGeometry.dispose();glowMaterial.dispose();scanGeometry.dispose();scanMaterial.dispose();trailGeometry.dispose();trailMaterial.dispose();markerGeometry.dispose();markerMaterial.dispose();axes.geometry.dispose();(Array.isArray(axes.material)?axes.material:[axes.material]).forEach(m=>m.dispose());reset.current=()=>{};};
 },[data,scan,process]);
 return <div className="geometry-canvas-wrap"><div className="geometry-canvas-stage"><div ref={host} className="geometry-canvas"/>{!!markers?.length&&<div className="geometry-object-markers" role="group" aria-label="模型对象标记" data-interactive={!!onSelect}>{markers.map(item=><button key={item.id} type="button" ref={el=>{if(el){markerNodes.current.set(item.id,el);}else{markerNodes.current.delete(item.id);}}} hidden={!markerNodes.current.has(item.id)} aria-label={`查看对象 ${item.label}`} aria-pressed={selected===item.id} disabled={!onSelect} onClick={()=>onSelect?.(item.id)}>{item.label}</button>)}</div>}</div><div className="geometry-canvas-controls" data-unavailable={status.startsWith('三维渲染')}><span role="status">{status}</span><Button size="sm" variant="outline" type="button" onClick={()=>reset.current()}>适配全图</Button></div></div>;
}
