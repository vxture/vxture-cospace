import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Input,Tooltip,TooltipContent,TooltipTrigger} from '@vxture/design-system';
import {PaperPlaneIcon,Plus,Minus,Crosshair,Stack,SquaresFour,ListBullets,MagnifyingGlass} from '@phosphor-icons/react';
import {Viewer,Cartesian2,Cartesian3,HeadingPitchRange,Matrix4,Color,Math as CesiumMath,ImageryLayer,TileMapServiceImageryProvider,UrlTemplateImageryProvider,ArcGISTiledElevationTerrainProvider,ScreenSpaceEventHandler,ScreenSpaceEventType,Entity} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import type {SceneSpace} from './scene-directory';
import {SceneDetail} from './scene-detail';
import {globePosition} from './globe-coordinates';
import {filterScenes,scenePhase,scenePhases} from './scene-catalog-contract';
import './scene-map.css';

export function SceneGlobe({spaces,loading,error,onBack,onRefresh}:{spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void}){
 const host=useRef<HTMLDivElement>(null),viewer=useRef<Viewer|null>(null);
 const [ready,setReady]=useState(false),[failure,setFailure]=useState(''),[terrain,setTerrain]=useState('地形加载中'),[imagery,setImagery]=useState('全球底图'),[query,setQuery]=useState(''),[selected,setSelected]=useState(''),[heading,setHeading]=useState(0),[tilted,setTilted]=useState(false);
 const visible=useMemo(()=>filterScenes(spaces,query,'all','phase'),[spaces,query]);
 const selectedScene=spaces.find(item=>item.id===selected);
 function home(){viewer.current?.camera.flyTo({destination:Cartesian3.fromDegrees(105,25,22000000),orientation:{heading:0,pitch:-Math.PI/2,roll:0},duration:1});}
 useEffect(()=>{
  if(!host.current)return;
  let alive=true,instance:Viewer|undefined,events:ScreenSpaceEventHandler|undefined;
  try{
   instance=new Viewer(host.current,{baseLayer:ImageryLayer.fromProviderAsync(TileMapServiceImageryProvider.fromUrl('/assets/cesium/Assets/Textures/NaturalEarthII')),animation:false,timeline:false,baseLayerPicker:false,geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true});
   viewer.current=instance;
   instance.camera.setView({destination:Cartesian3.fromDegrees(105,25,22000000)});
   const cameraChanged=()=>{if(alive){setHeading(CesiumMath.toDegrees(instance!.camera.heading));setTilted(Math.abs(instance!.camera.pitch+Math.PI/2)>.05);}};
   instance.camera.changed.addEventListener(cameraChanged);instance.camera.percentageChanged=.01;
   instance.scene.renderError.addEventListener(()=>{if(alive)setFailure('三维渲染异常，请重新打开三维地球或检查浏览器 WebGL 支持。');});
   events=new ScreenSpaceEventHandler(instance.scene.canvas);
   events.setInputAction((event:{position:import('cesium').Cartesian2})=>{const hit=instance!.scene.pick(event.position);setSelected(hit?.id instanceof Entity?String(hit.id.id):'');},ScreenSpaceEventType.LEFT_CLICK);
   const satellite=new UrlTemplateImageryProvider({url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',maximumLevel:19,credit:'Esri, Maxar, Earthstar Geographics, and the GIS User Community'});
   instance.imageryLayers.addImageryProvider(satellite);setImagery('卫星影像');
   satellite.errorEvent.addEventListener(()=>{if(alive)setImagery('卫星影像不可用 · 全球底图保留');});
   ArcGISTiledElevationTerrainProvider.fromUrl('https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer').then(provider=>{if(alive&&instance&&!instance.isDestroyed()){instance.terrainProvider=provider;provider.errorEvent.addEventListener(()=>{if(alive)setTerrain('部分地形加载失败');});setTerrain('全球地形');instance.scene.requestRender();}}).catch(()=>{if(alive)setTerrain('地形不可用 · 椭球模式');});
   setReady(true);
  }catch{setFailure('无法启动三维地球，请检查浏览器 WebGL 支持。');}
  return()=>{alive=false;events?.destroy();if(instance&&!instance.isDestroyed())instance.destroy();viewer.current=null;};
 },[]);
 useEffect(()=>{const current=viewer.current;if(!ready||!current)return;current.entities.removeAll();for(const item of visible){const location=globePosition(item.location);if(!location)continue;current.entities.add({id:item.id,name:item.name,position:Cartesian3.fromDegrees(...location),point:{pixelSize:10,color:Color.fromCssColorString('#4361ff'),outlineColor:Color.WHITE,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},label:{text:item.name,font:'12px sans-serif',show:false}});}current.scene.requestRender();},[visible,ready]);
 function choose(item:SceneSpace){setSelected(item.id);const location=globePosition(item.location);if(location)viewer.current?.camera.flyTo({destination:Cartesian3.fromDegrees(...location,12000),orientation:{heading:0,pitch:CesiumMath.toRadians(-50),roll:0},duration:1.5});}
 function orient(north:boolean){const current=viewer.current;if(!current)return;
  const center=new Cartesian2(current.canvas.clientWidth/2,current.canvas.clientHeight/2),ray=current.camera.getPickRay(center);
  const target=ray?current.scene.globe.pick(ray,current.scene):undefined;
  if(!target)return;
  current.camera.lookAt(target,new HeadingPitchRange(north?0:current.camera.heading,north?current.camera.pitch:tilted?-Math.PI/2:CesiumMath.toRadians(-45),Cartesian3.distance(current.camera.positionWC,target)));
  current.camera.lookAtTransform(Matrix4.IDENTITY);current.scene.requestRender();
 }

 const tools=[{name:'恢复正北',icon:<PaperPlaneIcon style={{transform:`rotate(${-heading}deg)`}}/>,action:()=>orient(true)},{name:tilted?'切换俯视':'切换倾斜视角',icon:<Stack/>,action:()=>orient(false)},{name:'复位三维地球',icon:<Crosshair/>,action:home},{name:'放大地球',icon:<Plus/>,action:()=>{const current=viewer.current;if(current){current.camera.zoomIn(Math.max(50,current.camera.positionCartographic.height*.4));current.scene.requestRender();}}},{name:'缩小地球',icon:<Minus/>,action:()=>{const current=viewer.current;if(current){current.camera.zoomOut(Math.max(50,current.camera.positionCartographic.height*.4));current.scene.requestRender();}}}];
 return <main className="scene-map-workspace scene-globe" aria-label="三维地球"><div className="scene-map-canvas" ref={host}/><div className="scene-map-heading"><ListBullets size={16}/><h1>场景目录</h1><span className="scene-map-total">{spaces.length}</span></div><Button className="scene-map-back" variant="secondary" onClick={onBack}><SquaresFour size={16}/>清单模式</Button><aside className="scene-map-directory" aria-label="地球场景清单"><div className="scene-map-search"><MagnifyingGlass size={16}/><Input aria-label="搜索地球场景" placeholder="搜索场景" value={query} onChange={event=>setQuery(event.target.value)}/></div><div className="scene-map-items">{loading&&<p role="status">正在读取场景…</p>}{error&&<div role="alert">{error}<Button onClick={onRefresh}>重新读取</Button></div>}{visible.map(item=><button className="scene-map-item" key={item.id} onClick={()=>choose(item)} aria-pressed={selected===item.id}><span className="scene-map-item-copy"><span className="scene-map-item-title"><strong>{item.name}</strong><span className="scene-map-tag">{scenePhases[scenePhase(item)].label}</span></span><small>{item.project_name}</small><small>{globePosition(item.location)?'已定位':item.location?'坐标待转换':'位置未登记'}</small></span></button>)}</div><footer>{visible.filter(item=>globePosition(item.location)).length} 个场景已定位</footer></aside>{failure&&<div className="scene-map-status" role="alert">{failure}</div>}<div className="scene-globe-status" role="status">{imagery} · {terrain}</div><div className="scene-map-tools" role="group" aria-label="地球操作">{tools.map(tool=><Tooltip key={tool.name}><TooltipTrigger asChild><Button size="icon-xl" variant="ghost" disabled={!ready||!!failure} aria-label={tool.name} onClick={tool.action}>{tool.icon}</Button></TooltipTrigger><TooltipContent side="left">{tool.name}</TooltipContent></Tooltip>)}</div><SceneDetail mapOverlay scene={selectedScene} onClose={()=>setSelected('')}/></main>;
}
