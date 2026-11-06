import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three/webgpu';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {CloudDirectory,Bounds,TileCache,decodeTile,plan,fullBounds,intersects} from './scene-cloud-data';

export type CloudCamera={reset:()=>void;focus:()=>void;frame:(bounds:Bounds)=>void;pick:(enabled:boolean)=>void};
type Props={endpoint:string;data:CloudDirectory;sources:number[];bounds:Bounds;onBounds:(b:Bounds)=>void;api:React.RefObject<CloudCamera|null>};
export function SceneCloudCanvas({endpoint,data,sources,bounds,onBounds,api}:Props){
 const host=useRef<HTMLDivElement>(null),settings=useRef({sources,bounds,onBounds});settings.current={sources,bounds,onBounds};
 const [status,setStatus]=useState('正在打开空间…'),[error,setError]=useState('');
 const invalidate=useRef<()=>void>(()=>{});
 useEffect(()=>{invalidate.current();},[sources,bounds]);
 useEffect(()=>{
  const element=host.current!;let stopped=false,ready=false,revision=0,timer:ReturnType<typeof setTimeout>|undefined,request:AbortController|undefined,picking=false,startPoint:THREE.Vector3|null=null;
  let renderer:THREE.WebGPURenderer|undefined,controls:OrbitControls|undefined,resize:ResizeObserver|undefined;
  const scene=new THREE.Scene();scene.background=new THREE.Color('#090d16');
  const camera=new THREE.PerspectiveCamera(42,1,.01,10000);camera.up.set(0,0,1);
  const cache=new TileCache(data.cache_point_budget),meshes=new Map<string,THREE.Points>(),material=new THREE.PointsMaterial({size:2.1,sizeAttenuation:false,vertexColors:true});
  const box=new THREE.Box3Helper(new THREE.Box3(),new THREE.Color('#709bff'));scene.add(box);
  const all=fullBounds(data),center=new THREE.Vector3(...all[0]).add(new THREE.Vector3(...all[1])).multiplyScalar(.5);
  const ray=new THREE.Raycaster(),plane=new THREE.Plane(new THREE.Vector3(0,0,1),-center.z);
  function frame(b:Bounds){if(!controls)return;const target=new THREE.Box3(new THREE.Vector3(...b[0]),new THREE.Vector3(...b[1]));
   const c=target.getCenter(new THREE.Vector3()),size=target.getSize(new THREE.Vector3());const distance=Math.max(size.x/(camera.aspect||1),size.y,size.z,.2)/Math.tan(THREE.MathUtils.degToRad(21))*1.3;
   controls.target.copy(c);camera.position.copy(c).addScaledVector(new THREE.Vector3(.6,-.9,1).normalize(),distance);camera.near=Math.max(.001,distance/10000);camera.far=Math.max(1000,distance*100);camera.updateProjectionMatrix();controls.update();schedule();}
  function clear(){for(const mesh of meshes.values()){scene.remove(mesh);mesh.geometry.dispose();}meshes.clear();}
  function schedule(){clearTimeout(timer);request?.abort();revision++;if(stopped)return;timer=setTimeout(()=>void load(revision),180);}
  async function load(run:number){
   if(!controls||!ready||stopped)return;const controller=new AbortController();request=controller;setError('');
   const current=settings.current;box.box.set(new THREE.Vector3(...current.bounds[0]),new THREE.Vector3(...current.bounds[1]));
   camera.updateMatrixWorld();const frustum=new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse));
   const visible=data.tiles.filter(t=>current.sources.includes(t.source)&&intersects(t.bounds,current.bounds)&&frustum.intersectsBox(new THREE.Box3(new THREE.Vector3(...t.bounds[0]),new THREE.Vector3(...t.bounds[1]))));
   const scale=camera.position.distanceTo(controls.target)*2*Math.tan(THREE.MathUtils.degToRad(21))/Math.max(element.clientHeight,1);
   const wanted=scale<.25?0:scale<1.5?1:2;
   // Old geometry disappears at the start of a new scope/viewport, including failures.
   clear();
   try{
    const items=plan(visible,wanted,data.display_point_budget),keys=new Set(items.map(i=>i.tile.id+':'+i.lod.level));let read=0,hits=0,points=0;
    for(const item of items){
     if(stopped||run!==revision||controller.signal.aborted)return;
     const key=item.tile.id+':'+item.lod.level;let value=cache.get(key);
     if(value)hits++;else{
      const url=`${endpoint}/api/scene-pointclouds/tiles/${item.tile.id}/${item.lod.level}?`+new URLSearchParams({space_id:data.space_id,index_sha256:data.index_sha256});
      const response=await fetch(url,{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error(response.status===403?'没有读取当前场景的权限。':'显示分块不可读，请重新打开场景。');
      value=await decodeTile(await response.arrayBuffer(),item.lod);read++;
      if(stopped||run!==revision||controller.signal.aborted)return;cache.put(key,value);
     }
     const ids:number[]=[];for(let i=0;i<value.points;i++)if(current.bounds[0].every((v,j)=>value!.positions[i*3+j]>=v&&value!.positions[i*3+j]<current.bounds[1][j]))ids.push(i);
     const positions=new Float32Array(ids.length*3),colors=new Float32Array(ids.length*3);
     ids.forEach((id,i)=>{positions.set(value!.positions.subarray(id*3,id*3+3),i*3);colors.set(value!.colors.subarray(id*3,id*3+3),i*3);});
     const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
     const mesh=new THREE.Points(geometry,material);meshes.set(key,mesh);scene.add(mesh);points+=ids.length;
     setStatus(`读取 ${read} 块 · 缓存命中 ${hits} 块 · ${points.toLocaleString()} 显示点`);
    }
    if(!items.length)setStatus('当前视口没有所选来源的显示分块。');
    element.dataset.visibleTiles=String(keys.size);element.dataset.networkTiles=String(read);element.dataset.cacheHits=String(hits);element.dataset.cachePoints=String(cache.points);element.dataset.displayPoints=String(points);element.dataset.lod=String(items[0]?.lod.level??wanted);
   }catch(e){if(!controller.signal.aborted&&run===revision&&!stopped){clear();cache.clear();setError(e instanceof Error?e.message:'显示分块读取失败。');setStatus('显示已停止，请调整范围或重试。');}}
  }
  function point(event:PointerEvent){const rect=element.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),camera);return ray.ray.intersectPlane(plane,new THREE.Vector3());}
  function down(event:PointerEvent){if(picking&&event.button===0){startPoint=point(event);element.setPointerCapture(event.pointerId);}}
  function up(event:PointerEvent){if(!picking||!startPoint)return;const end=point(event);if(end&&startPoint.distanceTo(end)>.01){const b=settings.current.bounds;settings.current.onBounds([[Math.min(startPoint.x,end.x),Math.min(startPoint.y,end.y),b[0][2]],[Math.max(startPoint.x,end.x),Math.max(startPoint.y,end.y),b[1][2]]]);}startPoint=null;picking=false;if(controls)controls.enabled=true;element.style.cursor='';}
  async function start(){try{
   renderer=new THREE.WebGPURenderer({antialias:true});await renderer.init();if(stopped){renderer.dispose();return;}ready=true;
   renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.domElement.setAttribute('aria-label','场景分块三维画布');element.appendChild(renderer.domElement);
   controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=false;controls.addEventListener('change',schedule);
   resize=new ResizeObserver(()=>{renderer!.setSize(element.clientWidth,Math.max(element.clientHeight,1));camera.aspect=element.clientWidth/Math.max(element.clientHeight,1);camera.updateProjectionMatrix();schedule();});resize.observe(element);
   camera.aspect=element.clientWidth/Math.max(element.clientHeight,1);frame(all);
   api.current={reset:()=>frame(all),focus:()=>{if(!controls)return;camera.position.copy(controls.target).add(camera.position.clone().sub(controls.target).multiplyScalar(.45));camera.updateProjectionMatrix();schedule();},frame,pick(enabled){picking=enabled;if(controls)controls.enabled=!enabled;element.style.cursor=enabled?'crosshair':'';}};
   invalidate.current=()=>{clear();schedule();};element.addEventListener('pointerdown',down,true);element.addEventListener('pointerup',up,true);
   renderer.setAnimationLoop(()=>{if(!stopped)renderer!.render(scene,camera);});schedule();
  }catch(e){if(!stopped)setError(`三维视图不可用：${e instanceof Error?e.message:'初始化失败'}`);}}
  void start();
  return()=>{stopped=true;revision++;clearTimeout(timer);request?.abort();api.current=null;invalidate.current=()=>{};resize?.disconnect();controls?.dispose();clear();cache.clear();material.dispose();box.geometry.dispose();(Array.isArray(box.material)?box.material:[box.material]).forEach(m=>m.dispose());element.removeEventListener('pointerdown',down,true);element.removeEventListener('pointerup',up,true);if(ready){renderer?.setAnimationLoop(null);renderer?.dispose();}renderer?.domElement.remove();};
 },[endpoint,data,api]);
 return <><div ref={host} className="scene-cloud-canvas" data-testid="scene-cloud-canvas"/><div className="scene-cloud-display-status" role="status">{status}</div>{error&&<div className="scene-cloud-display-error" role="alert">{error}<button onClick={()=>invalidate.current()}>重试显示</button></div>}</>;
}
