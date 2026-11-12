import {useSceneControls} from './scene-selection';
import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Input,Tabs,TabsList,TabsTrigger,Tooltip,TooltipContent,TooltipTrigger} from '@vxture/design-system';
import {InfoIcon,PaperPlaneIcon,Plus,Minus,Crosshair,GlobeHemisphereEast,Stack,SquaresFour,ListBullets,MagnifyingGlass,CaretUp,CaretDown} from '@phosphor-icons/react';
import {GlobeCanvas} from '@vxture/globe/react';
import type {GlobeController,GlobeScene,GlobeSelection,Binding,GlobeState} from '@vxture/globe';
import {useGlobeConfiguration} from './globe-configuration';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import type {SceneSpace} from './scene-directory';
import {SceneDetail} from './scene-detail';
import {globePosition} from './globe-coordinates';
import {locationLabel} from './geographic-location';
import {MapSettings} from './map-settings';
import {readMapPreferences,defaultMapPreferences,mapPreferenceKey,type MapPreferences} from './map-preferences';
import {filterScenes,scenePhase,scenePhases} from './scene-catalog-contract';
import './scene-map.css';

export function SceneGlobe({spaces,loading,error,onBack,onRefresh,onViewChange,onController,onSelection,publicationId,embedded=false}:{onController?:(api:GlobeController|null)=>void;onSelection?:(selection:GlobeSelection|null)=>void;publicationId?:string;embedded?:boolean;onViewChange:(value:'2D'|'3D')=>void;spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void}){
 const {selectScene}=useSceneControls();
 const viewer=useRef<GlobeController|null>(null);
 const {configuration,error:configurationError,loading:configurationLoading,retry:retryConfiguration}=useGlobeConfiguration();
 const [engineRevision,setEngineRevision]=useState(0);
 function retryGlobe(){setReady(false);setFailure('');setEngineRevision(value=>value+1);retryConfiguration();}
 const [ready,setReady]=useState(false),[failure,setFailure]=useState(''),[query,setQuery]=useState(''),[selected,setSelected]=useState(''),[heading,setHeading]=useState(0),[tilted,setTilted]=useState(false);
 const [preferences,setPreferences]=useState(readMapPreferences),[preferenceError,setPreferenceError]=useState(''),[phase,setPhase]=useState('all'),[focusError,setFocusError]=useState('');

 function updatePreference<K extends keyof MapPreferences>(key:K,value:MapPreferences[K]){const next={...preferences,[key]:value};setPreferences(next);try{localStorage.setItem(mapPreferenceKey,JSON.stringify(next));setPreferenceError('');}catch{setPreferenceError('浏览器禁止保存偏好，本次设置仅在当前页面生效。');}}
 const visible=useMemo(()=>filterScenes(spaces,query,phase,'phase'),[spaces,query,phase]);
 const selectedScene=visible.find(item=>item.id===selected);
 const globeScenes=useMemo<GlobeScene[]>(()=>visible.flatMap(item=>{const position=globePosition(item.location);return position?[{spaceId:item.id,publicationId,name:item.name,position}]:[];}),[visible,publicationId]);
 function binding(item:SceneSpace):Binding{return {spaceId:item.id,publicationId};}
 function choose(item:SceneSpace){
  if(!embedded)selectScene(item.id);setSelected(item.id);setFocusError('');
  if(!globePosition(item.location)){setFocusError(item.location?.crs==='GCJ02'?'此场景为 GCJ02 坐标，三维定位待转换。':'此场景尚无有效位置，请在基本信息中登记。');return;}
  try{viewer.current?.command({type:'focus',binding:binding(item)});}catch{setFocusError('场景定位暂不可用，请重试。');}
 }
 useEffect(()=>{viewer.current?.select(selected?{spaceId:selected,publicationId}:null);},[selected,publicationId,ready]);
 useEffect(()=>{if(selected&&!visible.some(item=>item.id===selected)){setSelected('');setFocusError('');}},[visible,selected]);
 const fitted=useRef<GlobeScene[]|null>(null);
 useEffect(()=>{if(ready&&preferences.autoFit&&globeScenes.length&&fitted.current!==globeScenes){try{viewer.current?.command({type:'fit'});fitted.current=globeScenes;}catch{setFocusError('自动取景暂不可用。');}}},[ready,preferences.autoFit,globeScenes]);
 function stateChanged(state:GlobeState){setReady(state.ready);setFailure(state.failure?'三维渲染异常，请重新打开三维地球或检查浏览器 WebGL 支持。':'');}

 const tools=[{name:'恢复正北',icon:<PaperPlaneIcon style={{transform:`rotate(${-heading}deg)`}}/>,action:()=>viewer.current?.command({type:'north'})},{name:'复位地球视图',hint:globeScenes.length?'定位筛选场景':'恢复全球视图',icon:<Crosshair/>,action:()=>{try{viewer.current?.command({type:globeScenes.length?'fit':'reset'});setFocusError('');}catch{setFocusError('场景取景暂不可用。');}}},{name:tilted?'切换俯视':'切换倾斜视角',icon:<Stack/>,action:()=>viewer.current?.command({type:'tilt'})},{name:'放大地球',icon:<Plus/>,action:()=>viewer.current?.command({type:'zoom-in'})},{name:'缩小地球',icon:<Minus/>,action:()=>viewer.current?.command({type:'zoom-out'})}];

 return <main className="scene-map-workspace scene-globe" aria-label="三维地球">{configuration&&<GlobeCanvas key={engineRevision} className="scene-map-canvas" configuration={configuration} scenes={globeScenes} satellite={preferences.basemap==='satellite'} scrollZoom={preferences.scrollZoom} onReady={api=>{viewer.current=api;onController?.(api);}} onSelect={selection=>{if(selection&&!embedded)selectScene(selection.spaceId);setSelected(selection?.spaceId||'');setFocusError('');onSelection?.(selection);}} onCamera={camera=>{setHeading(camera.heading);setTilted(camera.tilted);}} onState={stateChanged} onError={()=>setFailure('无法启动三维地球，请检查浏览器 WebGL 支持或重新打开。')}/>}<div className="scene-map-heading"><ListBullets size={16}/><h1>场景目录</h1><span className="scene-map-total">{spaces.length}</span><Button variant="ghost" size="icon-xl" aria-label={preferences.directoryExpanded?'收起场景清单':'展开场景清单'} onClick={()=>updatePreference('directoryExpanded',!preferences.directoryExpanded)}>{preferences.directoryExpanded?<CaretUp size={16}/>:<CaretDown size={16}/>}</Button></div><Tabs className="scene-map-phases" value={phase} onValueChange={setPhase}><TabsList aria-label="地图场景状态"><TabsTrigger value="all">全部</TabsTrigger>{Object.entries(scenePhases).map(([value,state])=><TabsTrigger key={value} value={value}>{state.label}</TabsTrigger>)}</TabsList></Tabs>{!embedded&&<Button className="scene-map-back" variant="secondary" onClick={onBack}><SquaresFour size={16}/>清单模式</Button>}{preferences.directoryExpanded&&<aside className="scene-map-directory" aria-label="地球场景清单"><div className="scene-map-search"><MagnifyingGlass size={16}/><Input aria-label="搜索地球场景" placeholder="搜索场景" value={query} onChange={event=>setQuery(event.target.value)}/></div><div className="scene-map-items">{loading&&<output>正在读取场景…</output>}{error&&<div role="alert">{error}<Button onClick={onRefresh}>重新读取</Button></div>}{visible.map(item=><button className="scene-map-item" key={item.id} onClick={()=>choose(item)} aria-pressed={selected===item.id}><span className="scene-map-item-copy"><span className="scene-map-item-title"><strong>{item.name}</strong><span className="scene-map-tag">{scenePhases[scenePhase(item)].label}</span></span><small>{item.project_name}</small><small>{locationLabel(item.location)}</small></span></button>)}</div><footer><InfoIcon size={14} aria-hidden="true"/>{globeScenes.length} 个场景已定位 · {visible.length-globeScenes.length} 个位置待补充</footer></aside>}{(failure||configurationError||focusError)&&<div className="scene-map-status" role="alert"><span>{failure||configurationError||focusError}</span>{(failure||configurationError)&&<Button variant="secondary" disabled={configurationLoading} onClick={retryGlobe}>重新加载地球</Button>}</div>}<section className="scene-map-tools" aria-label="地球操作">{tools.map(tool=><Tooltip key={tool.name}><TooltipTrigger asChild><Button size="icon-xl" variant="ghost" disabled={!ready||!!failure||!!configurationError} title={tool.hint||tool.name} aria-label={tool.name} onClick={tool.action}>{tool.icon}</Button></TooltipTrigger><TooltipContent side="left">{tool.hint||tool.name}</TooltipContent></Tooltip>)}<MapSettings preferences={preferences} updatePreference={updatePreference} viewMode="3D" onViewChange={onViewChange} onReset={()=>{const next={...defaultMapPreferences,viewMode:'3D' as const};setPreferences(next);try{localStorage.setItem(mapPreferenceKey,JSON.stringify(next));}catch{setPreferenceError('偏好未能保存。');}}} preferenceError={preferenceError}/></section>{preferences.legend&&<div className="scene-map-legend" aria-label="场景状态图例">{Object.entries(scenePhases).map(([key,value])=><span key={key} data-tone={value.tone}>{value.label}</span>)}</div>}<SceneDetail mapOverlay scene={selectedScene} onClose={()=>{setSelected('');setFocusError('');}}/></main>;
}
