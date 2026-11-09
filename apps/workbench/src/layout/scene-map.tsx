import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Input,SegmentedControl,Popover,PopoverTrigger,PopoverContent,Switch,Tabs,TabsList,TabsTrigger,useTheme} from '@vxture/design-system';
import {SquaresFour,MagnifyingGlass,CaretUp,CaretDown,Crosshair,Plus,Minus,SlidersHorizontal,Cube,ListBullets,ArrowCounterClockwise,X} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {scenePhases,scenePhase,filterScenes,type ScenePhase} from './scene-catalog-contract';
import {SceneDetail} from './scene-detail';
import {loadAmap,displayPoints,createAdministrativeLayer,type AmapDistrictLayer,type AmapMap,type AmapMarker,type Point} from './amap-sdk';
import {defaultMapPreferences,readMapPreferences,normalizeMapPreferences,mapPreferenceKey,mapIsDark,mapFeatures,type MapPreferences} from './map-preferences';
import './scene-map.css';

const glyphs:Record<ScenePhase,string>={published:'<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm-8 4.5 8 4.5 8-4.5M12 12v9"/>',building:'<path d="M20 12a8 8 0 1 1-3-6.25M20 4v5h-5"/>',review:'<path d="M12 5v9m0 4h.01"/>',unavailable:'<path d="m7 7 10 10M17 7 7 17"/>',paused:'<path d="M8 5v14M16 5v14"/>',archived:'<path d="M5 9v11h14V9M4 4h16v5H4zM9 13h6"/>'};
function pinSvg(phase:ScenePhase){return `<svg class="scene-map-pin" viewBox="0 0 36 44" aria-hidden="true"><path class="scene-pin-fill" d="M18 1C8.6 1 1 8.6 1 18c0 10 11 20 17 25 6-5 17-15 17-25C35 8.6 27.4 1 18 1Z"/><svg x="6" y="6" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${glyphs[phase]}</svg></svg>`;}

export function SceneMap({spaces,loading,error,onBack,onRefresh}:{spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void}){
 const {theme}=useTheme();const [preferences,setPreferences]=useState(readMapPreferences),[settingsOpen,setSettingsOpen]=useState(false),[preferenceError,setPreferenceError]=useState(''),[administrativeError,setAdministrativeError]=useState('');
 const dark=mapIsDark(preferences,theme),collapsed=!preferences.directoryExpanded;
 function updatePreference<K extends keyof MapPreferences>(key:K,value:MapPreferences[K]){setPreferences(previous=>({...previous,[key]:value}));}
 useEffect(()=>{try{localStorage.setItem(mapPreferenceKey,JSON.stringify(preferences));setPreferenceError('');}catch{setPreferenceError('浏览器禁止保存偏好，本次设置仅在当前页面生效。');}},[preferences]);
 useEffect(()=>{const sync=(event:StorageEvent)=>{if(event.storageArea===localStorage&&(event.key===mapPreferenceKey||event.key===null)){try{setPreferences(normalizeMapPreferences(JSON.parse(event.newValue||'null')));}catch{setPreferences({...defaultMapPreferences});}}};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync);},[]);
 const [phase,setPhase]=useState('all'),[query,setQuery]=useState(''),[selected,setSelected]=useState(''),[group,setGroup]=useState<string[]>([]),[revision,setRevision]=useState(0),[ready,setReady]=useState(false),[status,setStatus]=useState('正在加载高德地图…');
 const host=useRef<HTMLDivElement>(null),map=useRef<AmapMap|null>(null),markers=useRef<AmapMarker[]>([]),positions=useRef(new Map<string,Point>()),choice=useRef<(id:string)=>void>(()=>{});
 const visible=useMemo(()=>filterScenes(spaces,query,phase,'phase'),[spaces,query,phase]);
 const scene=visible.find(s=>s.id===selected),located=visible.filter(s=>s.location).length;
 function choose(id:string){setSelected(id);setGroup([]);const point=positions.current.get(id);if(point)map.current?.setZoomAndCenter(15,point);}
 choice.current=choose;
 useEffect(()=>{let alive=true;const timeout=setTimeout(()=>{if(alive)setStatus('地图加载超时，请检查网络后重试。');},25000);setReady(false);setStatus('正在加载高德地图…');
  loadAmap().then(sdk=>{if(!alive||!host.current)return;const created=new sdk.Map(host.current,{center:[104,35],zoom:4,viewMode:'2D',mapStyle:dark?'amap://styles/dark':'amap://styles/normal',features:mapFeatures(preferences),scrollWheel:preferences.scrollZoom});map.current=created;
   created.on('complete',()=>{if(alive){clearTimeout(timeout);setReady(true);setStatus('');}});created.on('click',()=>{setSelected('');setGroup([]);});
  }).catch(e=>{if(alive)setStatus(e.message);});
  return()=>{alive=false;clearTimeout(timeout);markers.current=[];positions.current.clear();map.current?.destroy();map.current=null;};
 },[revision]);
 useEffect(()=>{map.current?.setMapStyle(dark?'amap://styles/dark':'amap://styles/normal');},[dark,ready]);
 useEffect(()=>{map.current?.setFeatures(mapFeatures(preferences));map.current?.setStatus({scrollWheel:preferences.scrollZoom});},[preferences.roads,preferences.buildings,preferences.points,preferences.scrollZoom,ready]);
 useEffect(()=>{if(ready&&preferences.autoFit&&markers.current.length)map.current?.setFitView(markers.current,false,(host.current?.clientWidth||0)>600?[100,100,360,80]:[100,100,30,30],16);},[preferences.autoFit,ready]);
 useEffect(()=>{let alive=true;let layer:AmapDistrictLayer|undefined;setAdministrativeError('');
  if(!ready||!preferences.administrative)return;
  loadAmap().then(createAdministrativeLayer).then(created=>{layer=created;if(!alive)return;const colors=getComputedStyle(host.current!);created.setStyles({fill:'rgba(0,0,0,0)','nation-stroke':dark?'#454545':colors.getPropertyValue('--foreground').trim(),'province-stroke':dark?'#383838':colors.getPropertyValue('--primary-muted-foreground').trim(),'city-stroke':'rgba(0,0,0,0)'});created.setMap(map.current);}).catch(()=>{if(alive)setAdministrativeError('行政区划增强暂不可用，请关闭后重试。');});
  return()=>{alive=false;layer?.setMap(null);};
 },[ready,preferences.administrative,dark]);
 const autoFit=useRef(preferences.autoFit);autoFit.current=preferences.autoFit;
 useEffect(()=>{let alive=true;const created:AmapMarker[]=[];markers.current.forEach(marker=>marker.setMap(null));markers.current=[];positions.current.clear();setSelected('');setGroup([]);if(!ready||!map.current)return;
  const locatedScenes=visible.filter(s=>s.location);
  loadAmap().then(async sdk=>{const points=await displayPoints(sdk,locatedScenes.map(s=>s.location!));if(!alive||!map.current)return;
   setStatus('');const groups=new Map<string,{point:Point;scenes:SceneSpace[]}>();points.forEach((point,i)=>{const item=locatedScenes[i];positions.current.set(item.id,point);const key=point.join(',');const group=groups.get(key)||{point,scenes:[]};group.scenes.push(item);groups.set(key,group);});
   groups.forEach(({point,scenes})=>{const first=scenes[0],state=scenePhase(first);const button=document.createElement('button');button.type='button';button.className='scene-map-marker';button.dataset.tone=scenePhases[state].tone;button.dataset.sceneIds=scenes.map(s=>s.id).join(',');button.setAttribute('aria-pressed','false');button.setAttribute('aria-label',scenes.length>1?`${scenes.length} 个同址场景`:first.name+' · '+scenePhases[state].label);button.innerHTML=pinSvg(state);
    if(scenes.length>1){const count=document.createElement('span');count.className='scene-map-marker-count';count.textContent=String(scenes.length);button.append(count);}
    button.onclick=event=>{event.stopPropagation();if(scenes.length>1){setSelected('');setGroup(scenes.map(s=>s.id));}else choice.current(first.id);};
    const marker=new sdk.Marker({position:point,content:button,anchor:'bottom-center',map:map.current});created.push(marker);
   });markers.current=created;if(created.length&&autoFit.current)map.current.setFitView(created,false,(host.current?.clientWidth||0)>600?[100,100,360,80]:[100,100,30,30],16);
  }).catch(e=>{if(alive)setStatus(e.message);});
  return()=>{alive=false;created.forEach(marker=>marker.setMap(null));};
 },[visible,ready]);
 useEffect(()=>{host.current?.querySelectorAll<HTMLButtonElement>('.scene-map-marker').forEach(button=>button.setAttribute('aria-pressed',String(!!selected&&!!button.dataset.sceneIds?.split(',').includes(selected))));},[selected]);
 return <main className="scene-map-workspace" data-map-theme={dark?'dark':'light'} data-ui-theme={theme} aria-label="高德场景地图">
  <div ref={host} className="scene-map-canvas" role="region" aria-label="场景分布地图"/>
  <div className="scene-map-heading"><ListBullets size={16} aria-hidden="true"/><h1>场景目录</h1><span className="scene-map-total" aria-label="场景总数">{spaces.length}</span><Button size="icon-xl" variant="ghost" aria-label={collapsed?'展开场景清单':'收起场景清单'} aria-expanded={!collapsed} aria-controls="scene-map-directory" onClick={()=>updatePreference('directoryExpanded',collapsed)}>{collapsed?<CaretDown size={16}/>:<CaretUp size={16}/>}</Button></div>
  <Tabs className="scene-map-phases" value={phase} onValueChange={setPhase}><TabsList aria-label="地图场景状态"><TabsTrigger value="all">全部</TabsTrigger>{Object.entries(scenePhases).map(([value,state])=><TabsTrigger key={value} value={value}>{state.label}</TabsTrigger>)}</TabsList></Tabs>
  <Button className="scene-map-back" size="xl" variant="secondary" onClick={onBack}><SquaresFour size={16}/>清单模式</Button>
  {!collapsed&&<aside id="scene-map-directory" className="scene-map-directory" aria-label="场景清单"><div className="scene-map-search"><MagnifyingGlass size={16}/><Input value={query} aria-label="搜索地图场景" placeholder="搜索场景、项目或位置" onChange={e=>setQuery(e.target.value)}/></div><div className="scene-map-items">
   {loading&&<p role="status">正在读取场景…</p>}{error&&<div role="alert"><p>{error}</p><Button size="xl" variant="secondary" onClick={onRefresh}>重新读取</Button></div>}
   {visible.map(item=><button key={item.id} className="scene-map-item" aria-pressed={selected===item.id} data-tone={scenePhases[scenePhase(item)].tone} onClick={()=>choose(item.id)}><span className="scene-map-item-icon"><Cube size={18} aria-hidden="true"/></span><span className="scene-map-item-copy"><span className="scene-map-item-title"><strong title={item.name}>{item.name}</strong><span className="scene-map-tag">{scenePhases[scenePhase(item)].label}</span></span><small>{item.project_name}</small><small>{item.address||'位置未登记'}</small></span></button>)}
   {!loading&&!error&&!visible.length&&<p>没有匹配的场景</p>}</div><footer>{located} 个场景已定位 · {visible.length-located} 个位置待补充</footer></aside>}
  {status&&<div className="scene-map-status" role="status"><p>{status}</p>{!status.startsWith('正在')&&<Button size="xl" variant="secondary" onClick={()=>setRevision(v=>v+1)}>重新加载</Button>}</div>}
  {!!group.length&&<section className="scene-map-detail" aria-label="同址场景"><header><h2>同址场景 · {group.length}</h2><Button size="icon-xl" variant="ghost" aria-label="关闭同址场景" onClick={()=>setGroup([])}><X size={16}/></Button></header>{visible.filter(s=>group.includes(s.id)).map(s=><Button key={s.id} size="xl" variant="secondary" onClick={()=>choose(s.id)}>{s.name}</Button>)}</section>}
  <SceneDetail mapOverlay scene={scene} onClose={()=>setSelected('')}/>
  <div className="scene-map-tools" role="group" aria-label="地图操作"><Button size="icon-xl" variant="ghost" aria-label="复位全国地图" onClick={()=>map.current?.setZoomAndCenter(4,[104,35])}><Crosshair size={14}/></Button><Button size="icon-xl" variant="ghost" aria-label="放大地图" onClick={()=>map.current?.zoomIn()}><Plus size={14}/></Button><Button size="icon-xl" variant="ghost" aria-label="缩小地图" onClick={()=>map.current?.zoomOut()}><Minus size={14}/></Button><Popover open={settingsOpen} onOpenChange={setSettingsOpen}><PopoverTrigger asChild><Button size="icon-xl" variant="ghost" aria-label="地图设置" aria-pressed={settingsOpen}><SlidersHorizontal size={14}/></Button></PopoverTrigger><PopoverContent side="left" align="end" sideOffset={10} className="scene-map-settings" data-ui-theme={theme} aria-label="地图设置"><header><h2><SlidersHorizontal size={16}/>地图设置</h2><Button size="icon-xl" variant="ghost" aria-label="关闭地图设置" onClick={()=>setSettingsOpen(false)}><X size={14}/></Button></header><section aria-label="底图外观"><h3>底图外观</h3><SegmentedControl size="sm" fill ariaLabel="底图明暗" value={preferences.appearance} onChange={value=>updatePreference('appearance',value as MapPreferences['appearance'])} items={[{value:'follow',label:'跟随全局'},{value:'light',label:'亮色'},{value:'dark',label:'暗色'}]}/><p>跟随全局时，底图随平台主题自动切换。</p></section><section aria-label="地图要素"><h3>地图要素</h3>{([['roads','道路路网'],['buildings','建筑轮廓'],['points','兴趣点']] as const).map(([key,label])=><label className="scene-map-setting-row" key={key} htmlFor={'map-setting-'+key}><span>{label}</span><Switch id={'map-setting-'+key} checked={preferences[key]} onCheckedChange={value=>updatePreference(key,value)}/></label>)}</section><section aria-label="行政区划"><label className="scene-map-setting-row" htmlFor="map-setting-administrative"><span>行政区划</span><Switch id="map-setting-administrative" checked={preferences.administrative} onCheckedChange={value=>updatePreference('administrative',value)}/></label><p>增强省级行政边界；关闭后保留底图基础边界。</p>{administrativeError&&<p role="alert">{administrativeError}</p>}</section><section aria-label="交互与显示"><h3>交互与显示</h3>{([['scrollZoom','滚轮缩放'],['autoFit','筛选后自动取景'],['legend','场景状态图例']] as const).map(([key,label])=><label className="scene-map-setting-row" key={key} htmlFor={'map-setting-'+key}><span>{label}</span><Switch id={'map-setting-'+key} checked={preferences[key]} onCheckedChange={value=>updatePreference(key,value)}/></label>)}</section><footer><span>{preferenceError||'偏好自动保存在当前浏览器'}</span><Button size="sm" variant="ghost" onClick={()=>setPreferences({...defaultMapPreferences})}><ArrowCounterClockwise size={12}/>恢复默认</Button></footer></PopoverContent></Popover></div>
  {preferences.legend&&<div className="scene-map-legend" aria-label="场景状态图例">{Object.entries(scenePhases).map(([key,value])=><span key={key} data-tone={value.tone}><i dangerouslySetInnerHTML={{__html:pinSvg(key as ScenePhase)}}/>{value.label}</span>)}</div>}
 </main>;
}
