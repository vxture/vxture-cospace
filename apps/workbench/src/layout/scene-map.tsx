import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Input,SegmentedControl,useTheme} from '@vxture/design-system';
import {SquaresFour,MagnifyingGlass,CaretUp,CaretDown,Crosshair,Plus,Minus,Moon,Sun,X,ArrowRight} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {scenePhases,scenePhase,filterScenes,sceneWorkspaceHref,type ScenePhase} from './scene-catalog-contract';
import {SceneCover} from './scene-cover';
import {loadAmap,displayPoints,type AmapMap,type AmapMarker,type Point} from './amap-sdk';
import './scene-map.css';

const glyphs:Record<ScenePhase,string>={published:'<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm-8 4.5 8 4.5 8-4.5M12 12v9"/>',building:'<path d="M20 12a8 8 0 1 1-3-6.25M20 4v5h-5"/>',review:'<path d="M12 5v9m0 4h.01"/>',unavailable:'<path d="m7 7 10 10M17 7 7 17"/>',paused:'<path d="M8 5v14M16 5v14"/>',archived:'<path d="M5 9v11h14V9M4 4h16v5H4zM9 13h6"/>'};
function pinSvg(phase:ScenePhase){return `<svg class="scene-map-pin" viewBox="0 0 36 44" aria-hidden="true"><path class="scene-pin-fill" d="M18 1C8.6 1 1 8.6 1 18c0 10 11 20 17 25 6-5 17-15 17-25C35 8.6 27.4 1 18 1Z"/><svg x="6" y="6" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${glyphs[phase]}</svg></svg>`;}

export function SceneMap({spaces,loading,error,onBack,onRefresh}:{spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void}){
 const {theme}=useTheme();const [dark,setDark]=useState(theme==='dark'),[collapsed,setCollapsed]=useState(false),[phase,setPhase]=useState('all'),[query,setQuery]=useState(''),[selected,setSelected]=useState(''),[group,setGroup]=useState<string[]>([]),[revision,setRevision]=useState(0),[ready,setReady]=useState(false),[status,setStatus]=useState('正在加载高德地图…');
 const host=useRef<HTMLDivElement>(null),map=useRef<AmapMap|null>(null),markers=useRef<AmapMarker[]>([]),positions=useRef(new Map<string,Point>()),choice=useRef<(id:string)=>void>(()=>{});
 const visible=useMemo(()=>filterScenes(spaces,query,phase,'phase'),[spaces,query,phase]);
 const scene=visible.find(s=>s.id===selected),located=visible.filter(s=>s.location).length;
 function choose(id:string){setSelected(id);setGroup([]);const point=positions.current.get(id);if(point)map.current?.setZoomAndCenter(15,point);}
 choice.current=choose;
 useEffect(()=>{let alive=true;const timeout=setTimeout(()=>{if(alive)setStatus('地图加载超时，请检查网络后重试。');},25000);setReady(false);setStatus('正在加载高德地图…');
  loadAmap().then(sdk=>{if(!alive||!host.current)return;const created=new sdk.Map(host.current,{center:[104,35],zoom:4,viewMode:'2D',mapStyle:dark?'amap://styles/darkblue':'amap://styles/normal'});map.current=created;
   created.on('complete',()=>{if(alive){clearTimeout(timeout);setReady(true);setStatus('');}});created.on('click',()=>{setSelected('');setGroup([]);});
  }).catch(e=>{if(alive)setStatus(e.message);});
  return()=>{alive=false;clearTimeout(timeout);markers.current=[];positions.current.clear();map.current?.destroy();map.current=null;};
 },[revision]);
 useEffect(()=>{map.current?.setMapStyle(dark?'amap://styles/darkblue':'amap://styles/normal');},[dark,ready]);
 useEffect(()=>{let alive=true;const created:AmapMarker[]=[];markers.current.forEach(marker=>marker.setMap(null));markers.current=[];positions.current.clear();setSelected('');setGroup([]);if(!ready||!map.current)return;
  const locatedScenes=visible.filter(s=>s.location);
  loadAmap().then(async sdk=>{const points=await displayPoints(sdk,locatedScenes.map(s=>s.location!));if(!alive||!map.current)return;
   setStatus('');const groups=new Map<string,{point:Point;scenes:SceneSpace[]}>();points.forEach((point,i)=>{const item=locatedScenes[i];positions.current.set(item.id,point);const key=point.join(',');const group=groups.get(key)||{point,scenes:[]};group.scenes.push(item);groups.set(key,group);});
   groups.forEach(({point,scenes})=>{const first=scenes[0],state=scenePhase(first);const button=document.createElement('button');button.type='button';button.className='scene-map-marker';button.dataset.tone=scenePhases[state].tone;button.dataset.sceneIds=scenes.map(s=>s.id).join(',');button.setAttribute('aria-pressed','false');button.setAttribute('aria-label',scenes.length>1?`${scenes.length} 个同址场景`:first.name+' · '+scenePhases[state].label);button.innerHTML=pinSvg(state);
    if(scenes.length>1){const count=document.createElement('span');count.className='scene-map-marker-count';count.textContent=String(scenes.length);button.append(count);}
    button.onclick=event=>{event.stopPropagation();if(scenes.length>1){setSelected('');setGroup(scenes.map(s=>s.id));}else choice.current(first.id);};
    const marker=new sdk.Marker({position:point,content:button,anchor:'bottom-center',map:map.current});created.push(marker);
   });markers.current=created;if(created.length)map.current.setFitView(created,false,(host.current?.clientWidth||0)>600?[100,100,360,80]:[100,100,30,30],16);
  }).catch(e=>{if(alive)setStatus(e.message);});
  return()=>{alive=false;created.forEach(marker=>marker.setMap(null));};
 },[visible,ready]);
 useEffect(()=>{host.current?.querySelectorAll<HTMLButtonElement>('.scene-map-marker').forEach(button=>button.setAttribute('aria-pressed',String(!!selected&&!!button.dataset.sceneIds?.split(',').includes(selected))));},[selected]);
 return <main className="scene-map-workspace" aria-label="高德场景地图">
  <div ref={host} className="scene-map-canvas" role="region" aria-label="场景分布地图"/>
  <div className="scene-map-heading"><h1>场景目录 <span>{spaces.length}</span></h1><Button size="icon-xl" variant="ghost" aria-label={collapsed?'展开场景清单':'收起场景清单'} aria-expanded={!collapsed} onClick={()=>setCollapsed(!collapsed)}>{collapsed?<CaretDown size={16}/>:<CaretUp size={16}/>}</Button></div>
  <div className="scene-map-phases"><SegmentedControl ariaLabel="地图场景状态" value={phase} onChange={setPhase} items={[{value:'all',label:'全部'},...Object.entries(scenePhases).map(([value,state])=>({value,label:state.label}))]}/></div>
  <Button className="scene-map-back" size="xl" variant="secondary" onClick={onBack}><SquaresFour size={16}/>清单模式</Button>
  {!collapsed&&<aside className="scene-map-directory" aria-label="场景清单"><div className="scene-map-search"><MagnifyingGlass size={16}/><Input value={query} aria-label="搜索地图场景" placeholder="搜索场景、项目或位置" onChange={e=>setQuery(e.target.value)}/></div><div className="scene-map-items">
   {loading&&<p role="status">正在读取场景…</p>}{error&&<div role="alert"><p>{error}</p><Button size="xl" variant="secondary" onClick={onRefresh}>重新读取</Button></div>}
   {visible.map(item=><button key={item.id} className="scene-map-item" aria-pressed={selected===item.id} data-tone={scenePhases[scenePhase(item)].tone} onClick={()=>choose(item.id)}><span className="scene-map-item-title"><strong>{item.name}</strong><span className="catalog-card-status">{scenePhases[scenePhase(item)].label}</span></span><small>{item.project_name}</small><small>{item.address||'位置未登记'}</small></button>)}
   {!loading&&!error&&!visible.length&&<p>没有匹配的场景</p>}</div><footer>{located} 个场景已定位 · {visible.length-located} 个位置待补充</footer></aside>}
  {status&&<div className="scene-map-status" role="status"><p>{status}</p>{!status.startsWith('正在')&&<Button size="xl" variant="secondary" onClick={()=>setRevision(v=>v+1)}>重新加载</Button>}</div>}
  {!!group.length&&<section className="scene-map-detail" aria-label="同址场景"><header><h2>同址场景 · {group.length}</h2><Button size="icon-xl" variant="ghost" aria-label="关闭同址场景" onClick={()=>setGroup([])}><X size={16}/></Button></header>{visible.filter(s=>group.includes(s.id)).map(s=><Button key={s.id} size="xl" variant="secondary" onClick={()=>choose(s.id)}>{s.name}</Button>)}</section>}
  {scene&&<section className="scene-map-detail" aria-label="选中场景"><header><h2>{scene.name}</h2><Button size="icon-xl" variant="ghost" aria-label="关闭场景详情" onClick={()=>setSelected('')}><X size={16}/></Button></header><SceneCover name={scene.name} overviewUrl={scene.overview_url}/><div className="scene-map-detail-copy"><span className="catalog-card-status" data-tone={scenePhases[scenePhase(scene)].tone}>{scenePhases[scenePhase(scene)].label}</span><p>{scene.description||'暂无场景描述'}</p><small>{scene.address||'位置未登记'}</small></div><Button size="xl" asChild><a href={sceneWorkspaceHref(scene.id)}>进入场景<ArrowRight size={16}/></a></Button></section>}
  <div className="scene-map-tools" aria-label="地图操作"><Button size="icon-xl" variant="outline" aria-label="复位全国地图" onClick={()=>map.current?.setZoomAndCenter(4,[104,35])}><Crosshair size={16}/></Button><Button size="icon-xl" variant="outline" aria-label="放大地图" onClick={()=>map.current?.zoomIn()}><Plus size={16}/></Button><Button size="icon-xl" variant="outline" aria-label="缩小地图" onClick={()=>map.current?.zoomOut()}><Minus size={16}/></Button><Button size="icon-xl" variant="outline" aria-label={dark?'切换亮色底图':'切换暗色底图'} aria-pressed={dark} onClick={()=>setDark(!dark)}>{dark?<Sun size={16}/>:<Moon size={16}/>}</Button></div>
  <div className="scene-map-legend" aria-label="场景状态图例">{Object.entries(scenePhases).map(([key,value])=><span key={key} data-tone={value.tone}><i dangerouslySetInnerHTML={{__html:pinSvg(key as ScenePhase)}}/>{value.label}</span>)}</div>
 </main>;
}
