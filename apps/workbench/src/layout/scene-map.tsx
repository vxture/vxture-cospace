import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Input,SegmentedControl,Popover,PopoverTrigger,PopoverContent,Switch,Tabs,TabsList,TabsTrigger,Tooltip,TooltipTrigger,TooltipContent,useTheme} from '@vxture/design-system';
import {SquaresFour,MagnifyingGlass,CaretUp,CaretDown,Crosshair,Plus,Minus,SlidersHorizontal,PaperPlaneIcon,Cube,ListBullets,ArrowCounterClockwise,X} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {scenePhases,scenePhase,filterScenes,type ScenePhase} from './scene-catalog-contract';
import {SceneDetail} from './scene-detail';
import {loadAmap,displayPoints,createAdministrativeLayer,createSatelliteLayers,resetMapView,type AmapDistrictLayer,type AmapMap,type AmapMarker,type Point} from './amap-sdk';
import {defaultMapPreferences,readMapPreferences,normalizeMapPreferences,mapPreferenceKey,mapIsDark,mapFeatures,type MapPreferences} from './map-preferences';
import './scene-map.css';
import {validLocation,locationLabel} from './geographic-location';
import {MapSettings} from './map-settings';

const glyphs:Record<ScenePhase,string>={published:'<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm-8 4.5 8 4.5 8-4.5M12 12v9"/>',building:'<path d="M20 12a8 8 0 1 1-3-6.25M20 4v5h-5"/>',review:'<path d="M12 5v9m0 4h.01"/>',unavailable:'<path d="m7 7 10 10M17 7 7 17"/>',paused:'<path d="M8 5v14M16 5v14"/>',archived:'<path d="M5 9v11h14V9M4 4h16v5H4zM9 13h6"/>'};
function pinSvg(phase:ScenePhase){return `<svg class="scene-map-pin" viewBox="0 0 36 44" aria-hidden="true"><path class="scene-pin-fill" d="M18 1C8.6 1 1 8.6 1 18c0 10 11 20 17 25 6-5 17-15 17-25C35 8.6 27.4 1 18 1Z"/><svg x="6" y="6" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${glyphs[phase]}</svg></svg>`;}


export function AmapSceneMap({spaces,loading,error,onBack,onRefresh,onViewChange}:{onViewChange:(value:'2D'|'3D')=>void;spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void}){
 const {theme}=useTheme();const [preferences,setPreferences]=useState(readMapPreferences),[preferenceError,setPreferenceError]=useState(''),[administrativeError,setAdministrativeError]=useState(''),[layerError,setLayerError]=useState('');
 const dark=mapIsDark(preferences,theme),collapsed=!preferences.directoryExpanded;
 function updatePreference<K extends keyof MapPreferences>(key:K,value:MapPreferences[K]){setPreferences(previous=>({...previous,[key]:value}));}
 useEffect(()=>{try{localStorage.setItem(mapPreferenceKey,JSON.stringify(preferences));setPreferenceError('');}catch{setPreferenceError('浏览器禁止保存偏好，本次设置仅在当前页面生效。');}},[preferences]);
 useEffect(()=>{const sync=(event:StorageEvent)=>{if(event.storageArea===localStorage&&(event.key===mapPreferenceKey||event.key===null)){try{setPreferences(normalizeMapPreferences(JSON.parse(event.newValue||'null')));}catch{setPreferences({...defaultMapPreferences});}}};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync);},[]);
 const [phase,setPhase]=useState('all'),[query,setQuery]=useState(''),[selected,setSelected]=useState(''),[group,setGroup]=useState<string[]>([]),[revision,setRevision]=useState(0),[ready,setReady]=useState<AmapMap|null>(null),[status,setStatus]=useState('正在加载高德地图…');
 const [camera,setCamera]=useState({rotation:0,pitch:0});
 const viewpoint=useRef<{center:Point;zoom:number;rotation:number}>({center:[104,35],zoom:4,rotation:0});
 const fittedScenes=useRef<SceneSpace[]|null>(null);
 const host=useRef<HTMLDivElement>(null),map=useRef<AmapMap|null>(null),markers=useRef<AmapMarker[]>([]),positions=useRef(new Map<string,Point>()),choice=useRef<(id:string)=>void>(()=>{});
 const visible=useMemo(()=>filterScenes(spaces,query,phase,'phase'),[spaces,query,phase]);
 const scene=visible.find(s=>s.id===selected),located=visible.filter(s=>validLocation(s.location)).length;
 function choose(id:string){setSelected(id);setGroup([]);const point=positions.current.get(id);if(point)map.current?.setZoomAndCenter(15,point);}
 choice.current=choose;
 useEffect(()=>{let alive=true;const timeout=setTimeout(()=>{if(alive)setStatus('地图加载超时，请检查网络后重试。');},25000);setReady(null);setStatus('正在加载高德地图…');
  loadAmap().then(sdk=>{if(!alive||!host.current)return;const created=new sdk.Map(host.current,{center:viewpoint.current.center,zoom:viewpoint.current.zoom,rotation:viewpoint.current.rotation,viewMode:'2D',pitch:0,mapStyle:dark?'amap://styles/dark':'amap://styles/normal',features:mapFeatures(preferences),scrollWheel:preferences.scrollZoom});map.current=created;
   const syncCamera=()=>{if(alive)setCamera({rotation:created.getRotation(),pitch:created.getPitch()});};created.on('rotatechange',syncCamera);created.on('pitchchange',syncCamera);
   created.on('complete',()=>{if(alive){clearTimeout(timeout);syncCamera();setReady(created);setStatus('');}});created.on('click',()=>{setSelected('');setGroup([]);});
  }).catch(e=>{if(alive){clearTimeout(timeout);setStatus(e.message);}});
  return()=>{alive=false;clearTimeout(timeout);markers.current=[];positions.current.clear();if(map.current){const center=map.current.getCenter();viewpoint.current={center:[center.getLng(),center.getLat()],zoom:map.current.getZoom(),rotation:map.current.getRotation()};map.current.destroy();}map.current=null;};
 },[revision,preferences.viewMode]);
 useEffect(()=>{let layers:AmapDistrictLayer[]=[];let alive=true;setLayerError('');
  if(!ready||preferences.basemap!=='satellite')return;
  loadAmap().then(sdk=>{if(!alive)return;layers=createSatelliteLayers(sdk,preferences.roads);layers.forEach(layer=>layer.setMap(map.current));}).catch(error=>{if(alive)setLayerError(error.message);});
  return()=>{alive=false;layers.forEach(layer=>layer.setMap(null));};
 },[ready,preferences.basemap,preferences.roads]);
 useEffect(()=>{map.current?.setMapStyle(dark?'amap://styles/dark':'amap://styles/normal');},[dark,ready]);
 useEffect(()=>{map.current?.setFeatures(mapFeatures(preferences));map.current?.setStatus({scrollWheel:preferences.scrollZoom});},[preferences.roads,preferences.buildings,preferences.points,preferences.scrollZoom,ready]);
 useEffect(()=>{if(ready&&preferences.autoFit&&markers.current.length)map.current?.setFitView(markers.current,false,(host.current?.clientWidth||0)>600?[100,100,360,80]:[100,100,30,30],16);},[preferences.autoFit]);
 useEffect(()=>{let alive=true;let layer:AmapDistrictLayer|undefined;setAdministrativeError('');
  if(!ready||!preferences.administrative)return;
  loadAmap().then(createAdministrativeLayer).then(created=>{layer=created;if(!alive)return;const colors=getComputedStyle(host.current!);created.setStyles({fill:'rgba(0,0,0,0)','nation-stroke':dark?'#454545':colors.getPropertyValue('--foreground').trim(),'province-stroke':dark?'#383838':colors.getPropertyValue('--primary-muted-foreground').trim(),'city-stroke':'rgba(0,0,0,0)'});created.setMap(map.current);}).catch(()=>{if(alive)setAdministrativeError('行政区划增强暂不可用，请关闭后重试。');});
  return()=>{alive=false;layer?.setMap(null);};
 },[ready,preferences.administrative,dark]);
 const autoFit=useRef(preferences.autoFit);autoFit.current=preferences.autoFit;
 useEffect(()=>{let alive=true;const created:AmapMarker[]=[];markers.current.forEach(marker=>marker.setMap(null));markers.current=[];positions.current.clear();setSelected('');setGroup([]);if(!ready||!map.current)return;
  const locatedScenes=visible.filter(s=>validLocation(s.location));
  loadAmap().then(async sdk=>{const points=await displayPoints(sdk,locatedScenes.map(s=>s.location!));if(!alive||!map.current)return;
   setStatus('');const groups=new Map<string,{point:Point;scenes:SceneSpace[]}>();points.forEach((point,i)=>{const item=locatedScenes[i];positions.current.set(item.id,point);const key=point.join(',');const group=groups.get(key)||{point,scenes:[]};group.scenes.push(item);groups.set(key,group);});
   groups.forEach(({point,scenes})=>{const first=scenes[0],state=scenePhase(first);const button=document.createElement('button');button.type='button';button.className='scene-map-marker';button.dataset.tone=scenePhases[state].tone;button.dataset.sceneIds=scenes.map(s=>s.id).join(',');button.setAttribute('aria-pressed','false');button.setAttribute('aria-label',scenes.length>1?`${scenes.length} 个同址场景`:first.name+' · '+scenePhases[state].label);button.innerHTML=pinSvg(state);
    if(scenes.length>1){const count=document.createElement('span');count.className='scene-map-marker-count';count.textContent=String(scenes.length);button.append(count);}
    button.onclick=event=>{event.stopPropagation();if(scenes.length>1){setSelected('');setGroup(scenes.map(s=>s.id));}else choice.current(first.id);};
    const marker=new sdk.Marker({position:point,content:button,anchor:'bottom-center',map:map.current});created.push(marker);
   });markers.current=created;if(created.length&&autoFit.current&&fittedScenes.current!==visible)map.current.setFitView(created,false,(host.current?.clientWidth||0)>600?[100,100,360,80]:[100,100,30,30],16);fittedScenes.current=visible;
  }).catch(e=>{if(alive)setStatus(e.message);});
  return()=>{alive=false;created.forEach(marker=>marker.setMap(null));};
 },[visible,ready]);
 useEffect(()=>{host.current?.querySelectorAll<HTMLButtonElement>('.scene-map-marker').forEach(button=>button.setAttribute('aria-pressed',String(!!selected&&!!button.dataset.sceneIds?.split(',').includes(selected))));},[selected]);
 return <main className="scene-map-workspace" data-basemap={preferences.basemap} data-map-theme={dark?'dark':'light'} data-ui-theme={theme} aria-label="高德场景地图">
  <div ref={host} className="scene-map-canvas" role="region" aria-label="场景分布地图"/>
  <div className="scene-map-heading"><ListBullets size={16} aria-hidden="true"/><h1>场景目录</h1><span className="scene-map-total" aria-label="场景总数">{spaces.length}</span><Button size="icon-xl" variant="ghost" aria-label={collapsed?'展开场景清单':'收起场景清单'} aria-expanded={!collapsed} aria-controls="scene-map-directory" onClick={()=>updatePreference('directoryExpanded',collapsed)}>{collapsed?<CaretDown size={16}/>:<CaretUp size={16}/>}</Button></div>
  <Tabs className="scene-map-phases" value={phase} onValueChange={setPhase}><TabsList aria-label="地图场景状态"><TabsTrigger value="all">全部</TabsTrigger>{Object.entries(scenePhases).map(([value,state])=><TabsTrigger key={value} value={value}>{state.label}</TabsTrigger>)}</TabsList></Tabs>
  <Button className="scene-map-back" size="xl" variant="secondary" onClick={onBack}><SquaresFour size={16}/>清单模式</Button>
  {!collapsed&&<aside id="scene-map-directory" className="scene-map-directory" aria-label="场景清单"><div className="scene-map-search"><MagnifyingGlass size={16}/><Input value={query} aria-label="搜索地图场景" placeholder="搜索场景、项目或位置" onChange={e=>setQuery(e.target.value)}/></div><div className="scene-map-items">
   {loading&&<p role="status">正在读取场景…</p>}{error&&<div role="alert"><p>{error}</p><Button size="xl" variant="secondary" onClick={onRefresh}>重新读取</Button></div>}
   {visible.map(item=><button key={item.id} className="scene-map-item" aria-pressed={selected===item.id} data-tone={scenePhases[scenePhase(item)].tone} onClick={()=>choose(item.id)}><span className="scene-map-item-icon"><Cube size={18} aria-hidden="true"/></span><span className="scene-map-item-copy"><span className="scene-map-item-title"><strong title={item.name}>{item.name}</strong><span className="scene-map-tag">{scenePhases[scenePhase(item)].label}</span></span><small>{item.project_name}</small><small>{item.address||locationLabel(item.location)}</small></span></button>)}
   {!loading&&!error&&!visible.length&&<p>没有匹配的场景</p>}</div><footer>{located} 个场景已定位 · {visible.length-located} 个位置待补充</footer></aside>}
  {status&&<div className="scene-map-status" role="status"><p>{status}</p>{!status.startsWith('正在')&&<Button size="xl" variant="secondary" onClick={()=>setRevision(v=>v+1)}>重新加载</Button>}</div>}
  {!!group.length&&<section className="scene-map-detail" aria-label="同址场景"><header><h2>同址场景 · {group.length}</h2><Button size="icon-xl" variant="ghost" aria-label="关闭同址场景" onClick={()=>setGroup([])}><X size={16}/></Button></header>{visible.filter(s=>group.includes(s.id)).map(s=><Button key={s.id} size="xl" variant="secondary" onClick={()=>choose(s.id)}>{s.name}</Button>)}</section>}
  <SceneDetail mapOverlay scene={scene} onClose={()=>setSelected('')}/>
  <div className="scene-map-tools" role="group" aria-label="地图操作">
   <Tooltip><TooltipTrigger asChild><Button size="icon-xl" variant="ghost" disabled={!ready} aria-label="恢复正北" onClick={()=>ready?.setRotation(0)}><PaperPlaneIcon size={16} aria-hidden="true" style={{transform:`rotate(${camera.rotation}deg)`}}/></Button></TooltipTrigger><TooltipContent side="left">正北</TooltipContent></Tooltip>

   <Tooltip><TooltipTrigger asChild><Button size="icon-xl" variant="ghost" disabled={!ready} aria-label="复位地图视图" onClick={()=>{if(ready)resetMapView(ready,markers.current,'2D',(host.current?.clientWidth||0)>600);setSelected('');setGroup([]);}}><Crosshair size={16}/></Button></TooltipTrigger><TooltipContent side="left">复位视图</TooltipContent></Tooltip>
   <Tooltip><TooltipTrigger asChild><Button className="scene-map-tool-divider" size="icon-xl" variant="ghost" disabled={!ready} aria-label="放大地图" onClick={()=>ready?.zoomIn()}><Plus size={16}/></Button></TooltipTrigger><TooltipContent side="left">放大</TooltipContent></Tooltip>
   <Tooltip><TooltipTrigger asChild><Button size="icon-xl" variant="ghost" disabled={!ready} aria-label="缩小地图" onClick={()=>ready?.zoomOut()}><Minus size={16}/></Button></TooltipTrigger><TooltipContent side="left">缩小</TooltipContent></Tooltip>
   <MapSettings preferences={preferences} updatePreference={updatePreference} viewMode="2D" onViewChange={onViewChange} onReset={()=>setPreferences({...defaultMapPreferences})} layerError={layerError} administrativeError={administrativeError} preferenceError={preferenceError}/></div>
  {preferences.legend&&<div className="scene-map-legend" aria-label="场景状态图例">{Object.entries(scenePhases).map(([key,value])=><span key={key} data-tone={value.tone}><i dangerouslySetInnerHTML={{__html:pinSvg(key as ScenePhase)}}/>{value.label}</span>)}</div>}
 </main>;
}
