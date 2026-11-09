import {HeaderSupportControls} from '../layout/header-support-controls';
import {PlatformHeader as ShellHeader} from '../layout/platform-header';
/// <reference types="vite/client" />
import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ShellHeaderMark,ShellProductTitle,ShellHeaderDivider,ShellIconGroup,ShellIconButton,ShellThemeToggle,ShellUserMenu,Popover,PopoverTrigger,ShellPanelContent,ShellPanelSection,ShellPanelRow,useTheme,ThemeProvider,Button,Input,NativeSelect,ViewHeader,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem} from '@vxture/design-system';
import {CoSpaceBrand,LauncherPlatformBrand} from '../layout/product-brand';
import {MapTrifold,SquaresFour,Cube,MapPin,Buildings,Plus,Minus,Crosshair,SlidersHorizontal,X,List,DotsThreeVertical,ArrowRight,Clock,CheckCircle,FileDashed,MagnifyingGlass,CaretUp,CaretDown} from '@phosphor-icons/react';
import {SceneCover} from '../layout/scene-cover';
import {moduleGroups,moduleNames} from '../layout/product-navigation';
import * as maplibregl from 'maplibre-gl';
import type {Map as GeoMap,StyleSpecification} from 'maplibre-gl';
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';
import '../layout/globals.css';
import './map-lab.css';

maplibregl.setWorkerUrl(mapWorkerUrl);

const sceneStates={
 published:{label:'已发布',tone:'brand',icon:CheckCircle},
 building:{label:'构建中',tone:'info',icon:Clock},
 review:{label:'待验证',tone:'warning',icon:Clock},
 unavailable:{label:'不可用',tone:'danger',icon:X},
 paused:{label:'已暂停',tone:'neutral',icon:FileDashed},
 archived:{label:'已归档',tone:'neutral',icon:FileDashed},
} as const;
// Fixed SVG geometry shared by map pins and legend; no user-supplied markup.
const pinPaths={
 published:'<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm-8 4.5 8 4.5 8-4.5M12 12v9m-4-16 8 4.5"/>',
 building:'<path d="M20 12a8 8 0 1 1-3-6.25M20 4v5h-5"/>',
 review:'<path d="M12 5v9m0 4h.01"/>',
 unavailable:'<path d="m7 7 10 10M17 7 7 17"/>',
 paused:'<path d="M8 5v14M16 5v14"/>',
 archived:'<path d="M5 9v11h14V9M4 4h16v5H4zM9 13h6"/>',
};
function pinIcon(state:keyof typeof sceneStates){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${pinPaths[state]}</svg>`;}
type Scene={id:string;name:string;project:string;unit_short_name:string;address:string;description?:string;point?:[number,number];overview_url?:string;release_version?:string;published_at?:string;state:keyof typeof sceneStates};
// Design fixtures only. No customer data, scene writes or real business handoffs.
const fixtures:Scene[]=[
 {id:'sample-beijing-a',state:'published',release_version:'v1.4.0',published_at:'2026-11-08',name:'园区设备间',project:'北方园区 · 合成示例',unit_short_name:'北方园区',address:'北京 · 示例锚点',description:'设备与空间关系的统一视图，用于资料核对和空间服务。',point:[116.391,39.907]},
 {id:'sample-beijing-b',state:'review',name:'园区二层走廊',project:'北方园区 · 合成示例',unit_short_name:'北方园区',address:'北京 · 同址示例',description:'连接设备间与公共区域，核对走廊空间及关联资料。',point:[116.391,39.907]},
 {id:'sample-shanghai',state:'unavailable',name:'生产车间',project:'华东园区 · 合成示例',unit_short_name:'华东园区',address:'上海 · 示例锚点',description:'汇集生产设备、工位与空间资料，支撑车间协同。',point:[121.474,31.230]},
 {id:'sample-singapore',state:'paused',name:'海外仓储区',project:'海外项目 · 合成示例',unit_short_name:'海外项目',address:'新加坡 · 示例锚点',description:'集中查看仓储区域与空间资料，衔接海外项目协作。',point:[103.820,1.352]},
 {id:'sample-unlocated',state:'building',name:'待登记实验室',project:'研发项目 · 合成示例',unit_short_name:'研发项目',address:'尚未登记地理位置',description:'资料准备与空间构建进行中，持续完善场景内容。'},
 {id:'sample-archived',state:'archived',name:'历史展厅',project:'华南园区 · 合成示例',unit_short_name:'华南园区',address:'广州 · 示例锚点',point:[113.264,23.129],description:'历史空间资料已归档，保留用于后续查阅。'},
];

function configuredStyle():StyleSpecification{
 const template=import.meta.env.VITE_MAP_LAB_RASTER_URL?.trim();
 const attribution=import.meta.env.VITE_MAP_LAB_ATTRIBUTION?.trim();
 const labels=import.meta.env.VITE_MAP_LAB_LABEL_URL?.trim();
 const base:StyleSpecification={version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#edf1f3'}}]};
 if(!template)return base;
 const validTemplate=(value:string)=>value.startsWith('https://')&&['{z}','{x}','{y}'].every(part=>value.includes(part));
 if(!validTemplate(template)||labels&&!validTemplate(labels)||!attribution||import.meta.env.VITE_MAP_LAB_CRS!=='WGS84'){
  throw new Error('底图配置未通过校验，请核对 HTTPS XYZ 模板、署名和 WGS84 坐标声明。');
 }
 // Attribution accepts plain text only; MapLibre renders attribution as HTML.
 const safeAttribution=attribution.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
 return {...base,sources:{basemap:{type:'raster',tiles:[template],tileSize:256,attribution:safeAttribution},...(labels?{labels:{type:'raster' as const,tiles:[labels],tileSize:256}}:{})},layers:[...base.layers,{id:'basemap',type:'raster',source:'basemap'},...(labels?[{id:'labels',type:'raster' as const,source:'labels'}]:[])]};
}

function SceneMap({scenes,onChoose,onGroup,selected,onStatus,onMap}:{scenes:Scene[];onChoose:(id:string)=>void;onGroup:(ids:string[])=>void;selected?:Scene;onStatus:(status:string)=>void;onMap:(map:GeoMap|null)=>void}){
 const host=useRef<HTMLDivElement>(null),map=useRef<GeoMap|null>(null);
 const callbacks=useRef({onChoose,onGroup,onStatus,selected});callbacks.current={onChoose,onGroup,onStatus,selected};
 const [ready,setReady]=useState(false);
 useEffect(()=>{
  if(!host.current)return;
  let instance:GeoMap;
  try{
   instance=new maplibregl.Map({container:host.current,style:configuredStyle(),center:[112,25],zoom:2.5,pitch:0,bearing:0,attributionControl:{compact:false},renderWorldCopies:false});
   map.current=instance;instance.dragRotate.disable();instance.touchZoomRotate.disableRotation();
   onMap(instance);
   const clusterLabels=new Map<number,maplibregl.Marker>();
   const pointMarkers=new Map<string,maplibregl.Marker>();
   instance.on('render',()=>{
    if(!instance.getLayer('clusters'))return;
    const visible=new Set<number>();
    for(const feature of instance.queryRenderedFeatures({layers:['clusters']})){
     const id=feature.properties?.cluster_id;if(typeof id!=='number'||feature.geometry.type!=='Point')continue;
     visible.add(id);
     if(!clusterLabels.has(id)){
      const label=document.createElement('span');label.className='entry-cluster-count';label.textContent=String(feature.properties?.point_count);label.setAttribute('aria-hidden','true');
      clusterLabels.set(id,new maplibregl.Marker({element:label}).setLngLat(feature.geometry.coordinates.slice(0,2) as [number,number]).addTo(instance));
     }
     const label=clusterLabels.get(id);if(label){label.getElement().textContent=String(feature.properties?.point_count);label.setLngLat(feature.geometry.coordinates.slice(0,2) as [number,number]);}
    }
    for(const [id,label] of clusterLabels){if(!visible.has(id)){label.remove();clusterLabels.delete(id);}}
    const visiblePoints=new Set<string>();
    for(const feature of instance.queryRenderedFeatures({layers:['points']})){
     const id=feature.properties?.id,state=feature.properties?.state as Scene['state'];
     if(typeof id!=='string'||feature.geometry.type!=='Point'||!sceneStates[state])continue;
     visiblePoints.add(id);
     if(!pointMarkers.has(id)){
      const button=document.createElement('button');button.className='entry-point';button.dataset.state=state;
      button.setAttribute('aria-label',`${feature.properties?.name} · ${sceneStates[state].label}`);button.title=button.getAttribute('aria-label')!;
      const symbol=document.createElement('span');symbol.className='entry-map-symbol';symbol.dataset.state=state;const badge=document.createElement('span');badge.className='entry-pin-badge';badge.innerHTML=pinIcon(state);symbol.append(badge);button.append(symbol);
      button.addEventListener('click',event=>{event.stopPropagation();callbacks.current.onChoose(id);});
      pointMarkers.set(id,new maplibregl.Marker({element:button,anchor:'bottom'}).setLngLat(feature.geometry.coordinates.slice(0,2) as [number,number]).addTo(instance));
     }
     const marker=pointMarkers.get(id)!;marker.getElement().setAttribute('aria-pressed',String(callbacks.current.selected?.id===id));
     marker.setLngLat(feature.geometry.coordinates.slice(0,2) as [number,number]);
    }
    for(const [id,marker] of pointMarkers){if(!visiblePoints.has(id)){marker.remove();pointMarkers.delete(id);}}
   });
   instance.once('style.load',()=>{
    instance.addSource('scenes',{type:'geojson',data:{type:'FeatureCollection',features:[]},cluster:true,clusterRadius:45,clusterMaxZoom:17});
    instance.addLayer({id:'clusters',type:'circle',source:'scenes',filter:['has','point_count'],paint:{'circle-color':'#273e68','circle-radius':22,'circle-stroke-color':'#fff','circle-stroke-width':3}});
    // No font/glyph service is needed for scene markers or cluster counts.
    instance.addLayer({id:'points',type:'circle',source:'scenes',filter:['!',['has','point_count']],paint:{'circle-radius':12,'circle-opacity':0,'circle-stroke-opacity':0}});
    instance.on('click','points',event=>{const id=event.features?.[0]?.properties?.id;if(typeof id==='string')callbacks.current.onChoose(id);});
    instance.on('click','clusters',async event=>{
     const feature=event.features?.[0],clusterId=feature?.properties?.cluster_id;
     if(typeof clusterId!=='number'||feature?.geometry.type!=='Point')return;
     try{
      const source=instance.getSource('scenes') as maplibregl.GeoJSONSource;
      const leaves=await source.getClusterLeaves(clusterId,100,0);
      if(map.current!==instance)return;
      const coordinates=leaves.map(leaf=>leaf.geometry.type==='Point'?leaf.geometry.coordinates:null);
      const samePlace=coordinates.every(point=>point&&point[0]===coordinates[0]?.[0]&&point[1]===coordinates[0]?.[1]);
      if(samePlace)callbacks.current.onGroup(leaves.map(leaf=>String(leaf.properties?.id)));
      else instance.easeTo({center:feature.geometry.coordinates.slice(0,2) as [number,number],zoom:await source.getClusterExpansionZoom(clusterId)});
     }catch{if(map.current===instance)callbacks.current.onStatus('聚合读取失败，请从列表选择场景。');}
    });
    setReady(true);callbacks.current.onStatus(import.meta.env.VITE_MAP_LAB_RASTER_URL?'底图已配置，等待人工核对覆盖与坐标。':'地图引擎已就绪；未配置地理底图，当前仅显示合成点位。');
   });
   instance.on('error',()=>callbacks.current.onStatus('地图资源加载失败，请从列表选择场景，或检查底图配置后重试。'));
  }catch(error){callbacks.current.onStatus(error instanceof Error?error.message:'地图初始化失败，请使用列表。');return;}
  const resize=new ResizeObserver(()=>{instance.resize();instance.jumpTo({center:callbacks.current.selected?.point||instance.getCenter()});});resize.observe(host.current);
  return()=>{resize.disconnect();map.current=null;onMap(null);instance.remove();};
 },[]);
 useEffect(()=>{
  if(!ready||!map.current)return;
  const source=map.current.getSource('scenes') as maplibregl.GeoJSONSource;
  source.setData({type:'FeatureCollection',features:scenes.filter(scene=>scene.point).map(scene=>({type:'Feature',geometry:{type:'Point',coordinates:scene.point!},properties:{id:scene.id,state:scene.state,name:scene.name}}))});
  const located=scenes.flatMap(scene=>scene.point?[scene.point]:[]);
  if(located.length){const bounds=new maplibregl.LngLatBounds();located.forEach(point=>bounds.extend(point));map.current.fitBounds(bounds,{padding:85,maxZoom:9,duration:0});}
 },[scenes,ready]);
 useEffect(()=>{
  if(!ready||!selected?.point||!map.current)return;
  map.current.easeTo({center:selected.point,zoom:Math.max(map.current.getZoom(),9),duration:400});
 },[ready,selected]);
 return <div ref={host} className="entry-map-canvas" role="img" aria-label="场景分布地图，合成点位，可通过列表完成选择"/>;
}

function EntryHeader(){
 const {theme,setTheme}=useTheme();
 return <ShellHeader height="md" className="entry-header" leading={<><Popover><PopoverTrigger asChild><ShellIconButton icon="app-grid" label="功能 Launcher"/></PopoverTrigger><ShellPanelContent align="start"><LauncherPlatformBrand/>{moduleGroups.map(group=><ShellPanelSection key={group.title} title={group.title}>{group.items.map(item=><ShellPanelRow key={item.route} label={moduleNames[item.route]} icon={item.icon} href={'/workbench/layout.html#'+item.route}/>)}</ShellPanelSection>)}</ShellPanelContent></Popover><CoSpaceBrand href="/workbench/map-lab.html"/></>} trailing={<div className="platform-header-actions"><span className="entry-sample-label">设计预览</span><ShellIconGroup label="全局工具"><ShellThemeToggle currentTheme={theme} onThemeChange={setTheme} buttonLabel="切换主题"/><HeaderSupportControls/><Popover><PopoverTrigger asChild><ShellIconButton icon="settings" label="配置与管理"/></PopoverTrigger><ShellPanelContent><ShellPanelSection title="配置与管理"><ShellPanelRow label="业务配置" href="/workbench/layout.html#settings"/></ShellPanelSection></ShellPanelContent></Popover></ShellIconGroup><ShellIconGroup label="账户"><ShellUserMenu openLabel="账户菜单" user={{displayName:'设计预览',avatarFallback:'预',uniqueLine:'合成场景',meta:'本机设计验证'}} links={[{key:'account',label:'个人账户',href:'/workbench/layout.html#account',icon:'user'}]} actions={[]}/></ShellIconGroup></div>}/>;
}
function MapLab(){
 const [query,setQuery]=useState(''),[selectedId,setSelectedId]=useState(''),[status,setStatus]=useState('正在启动地图…'),[view,setView]=useState('cards'),[group,setGroup]=useState<string[]>([]),[entered,setEntered]=useState(''),[config,setConfig]=useState(false),[phase,setPhase]=useState('all'),[sort,setSort]=useState('phase'),[catalogLayout,setCatalogLayout]=useState('cards'),[mapRevision,setMapRevision]=useState(0),[directoryOpen,setDirectoryOpen]=useState(true);
 const map=useRef<GeoMap|null>(null);
 const scenes=React.useMemo(()=>fixtures.filter(scene=>`${scene.name} ${scene.project} ${scene.id} ${scene.address}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())),[query]);
 const stateFor=(scene:Scene)=>sceneStates[scene.state].label;
 const visibleScenes=React.useMemo(()=>scenes.filter(scene=>phase==='all'||sceneStates[scene.state].label===phase).sort((a,b)=>sort==='name'?a.name.localeCompare(b.name,'zh-CN'):['published','building','review','unavailable','paused','archived'].indexOf(a.state)-['published','building','review','unavailable','paused','archived'].indexOf(b.state)),[scenes,phase,sort]);
 const selected=visibleScenes.find(scene=>scene.id===selectedId);
 useEffect(()=>{setGroup([]);setEntered('');setSelectedId('');},[query,phase]);
 useEffect(()=>{
  if(!selectedId)return;
  const dismiss=(event:PointerEvent)=>{
   const target=event.target;
   if(!(target instanceof Element)||target.closest('.entry-selection,.entry-scene,.entry-card,.entry-point,.entry-group,[role=menu],[data-radix-popper-content-wrapper]'))return;
   setSelectedId('');setEntered('');
  };
  document.addEventListener('pointerdown',dismiss);return()=>document.removeEventListener('pointerdown',dismiss);
 },[selectedId]);
 function changeView(next:string){setView(next);setSelectedId('');setEntered('');setGroup([]);setConfig(false);} 

 useEffect(()=>{
  const close=(event:KeyboardEvent)=>{if(event.key!=='Escape')return;if(config)setConfig(false);else if(group.length)setGroup([]);else{setSelectedId('');setEntered('');}};
  window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close);
 },[config,group.length]);
 function enter(scene:Scene){choose(scene.id);setEntered(`已选择「${scene.name}」，当前为设计预览。`);}
 function choose(id:string){setSelectedId(id);setEntered('');setGroup([]);}
 const sceneItems=visibleScenes.map(scene=>view==='cards'?<article key={scene.id} className="entry-card" aria-label={scene.name} data-selected={selectedId===scene.id} data-tone={sceneStates[scene.state].tone}>
  <div className="entry-card-visual"><header className="entry-card-heading"><div className="entry-card-title"><h2 title={scene.unit_short_name+' · '+scene.name}><button onClick={()=>choose(scene.id)}><span className="entry-card-unit">{scene.unit_short_name} · </span>{scene.name}</button></h2><span className="entry-status">{React.createElement(sceneStates[scene.state].icon,{size:12})} {stateFor(scene)}</span></div></header>
  <button className="entry-card-cover" aria-label={'查看'+scene.name+'详情'} onClick={()=>choose(scene.id)}><SceneCover name={scene.name} overviewUrl={scene.overview_url}/></button></div>
  <div className="entry-card-body"><p className="entry-card-description">{scene.description||'暂无场景描述'}</p><div className="entry-card-footer"><p className="entry-card-meta" title={scene.point?scene.address:'位置未登记'}><MapPin size={13}/><span>{scene.point?scene.address:'位置未登记'}</span></p>{scene.state==='published'&&<div className="entry-release-info"><span className="entry-release-version" aria-label="发布版本">{scene.release_version||'版本未登记'}</span><time dateTime={scene.published_at} aria-label="发布日期">{scene.published_at||'日期未登记'}</time></div>}<div><Button variant={sceneStates[scene.state].tone==='neutral'?'secondary':'default'} size="sm" onClick={()=>enter(scene)}>进入场景<ArrowRight size={14}/></Button><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="sm" aria-label={scene.name+'更多操作'}><DotsThreeVertical size={18}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem className="gap-xs" onSelect={()=>choose(scene.id)}><Cube size={16}/>查看详情</DropdownMenuItem><DropdownMenuItem className="gap-xs" disabled={!scene.point} title={!scene.point?'位置未登记':undefined} onSelect={()=>{choose(scene.id);setView('map');}}><MapPin size={16}/>地图定位</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div></div></div>
 </article>:<button key={scene.id} aria-pressed={selected?.id===scene.id} className="entry-scene" data-tone={sceneStates[scene.state].tone} onClick={()=>choose(scene.id)}><span className="entry-scene-art"><Cube size={23} weight="duotone"/></span><span className="entry-scene-copy"><span className="entry-scene-title"><strong>{scene.name}</strong><span className="entry-scene-state" data-tone={sceneStates[scene.state].tone}>{stateFor(scene)}</span></span><span>{scene.unit_short_name}</span><small><MapPin size={12}/>{scene.point?scene.address:'位置未登记'}</small></span></button>);
 return <main className="entry-lab"><EntryHeader/><div className={'entry-stage entry-mode-'+view}>
  <section className="entry-map" aria-label="场景地图工作区">{view==='map'&&<SceneMap key={mapRevision} scenes={visibleScenes} selected={selected} onChoose={choose} onGroup={setGroup} onStatus={setStatus} onMap={value=>{map.current=value;}}/>}{(!import.meta.env.VITE_MAP_LAB_RASTER_URL||status.includes('失败'))&&<div className="entry-map-note" role="status"><span>{status}</span>{status.includes('失败')&&<Button variant="secondary" size="sm" onClick={()=>{setStatus('正在重新加载地图…');setMapRevision(value=>value+1);}}>重新加载</Button>}</div>}{group.length>0&&<div className="entry-group"><header><strong>同址场景 · {group.length}</strong><Button variant="ghost" size="sm" aria-label="关闭同址场景" onClick={()=>setGroup([])}><X size={16}/></Button></header>{visibleScenes.filter(scene=>group.includes(scene.id)).map(scene=><Button key={scene.id} variant="outline" onClick={()=>choose(scene.id)}>{scene.name}</Button>)}</div>}</section>
  {view==='map'&&<><div className="entry-phase-switch" role="group" aria-label="地图场景状态"><span className="entry-phase-track" aria-hidden="true" style={{'--phase-index':['all',...Object.values(sceneStates).map(state=>state.label)].indexOf(phase)} as React.CSSProperties}/>{['all',...Object.values(sceneStates).map(state=>state.label)].map(value=><button key={value} aria-pressed={phase===value} onClick={()=>setPhase(value)}>{value==='all'?'全部':value}</button>)}</div><div className="entry-map-legend" aria-label="场景状态图例">{Object.entries(sceneStates).map(([key,state])=><span key={key}><i className="entry-map-symbol" data-state={key}><span className="entry-pin-badge" dangerouslySetInnerHTML={{__html:pinIcon(key as keyof typeof sceneStates)}}/></i>{state.label}</span>)}<span><i className="entry-legend-cluster">2</i>聚合</span></div></>}
  <div className="entry-content-shell">{view==='cards'&&<ViewHeader className="entry-page-heading" title="我的场景" secondary={<span className="entry-page-count" aria-label="场景数量">{fixtures.length}</span>} description="从场景开始，连接资料、模型与空间服务。" action={<Button variant="secondary" onClick={()=>changeView(view==='cards'?'map':'cards')}>{view==='cards'?<MapTrifold size={17}/>:<SquaresFour size={17}/>} {view==='cards'?'地图模式':'清单模式'}</Button>}/>}{view==='map'&&<div className="entry-map-heading"><Buildings size={18}/><h1>场景目录</h1><span>{fixtures.length}</span><button className="entry-directory-toggle" aria-label={directoryOpen?'收起场景清单':'展开场景清单'} aria-expanded={directoryOpen} aria-controls="entry-scene-directory" onClick={()=>setDirectoryOpen(value=>!value)}>{directoryOpen?<CaretUp size={16}/>:<CaretDown size={16}/>}</button></div>}{view==='map'&&<div className="entry-topbar"><Button variant="secondary" onClick={()=>changeView('cards')}><SquaresFour size={17}/>清单模式</Button></div>}

  <aside id="entry-scene-directory" className="entry-list" aria-label="场景列表" hidden={view==='map'&&!directoryOpen}>{view==='map'&&<div className="entry-map-directory-controls"><div className="entry-map-search"><MagnifyingGlass size={16}/><Input aria-label="搜索地图场景" placeholder="搜索场景、单位或地址" value={query} onChange={event=>{setQuery(event.target.value);setGroup([]);setEntered('');}}/></div></div>}
 <div className="entry-catalog-operations" aria-label="清单操作区">{view==='cards'&&<div className="entry-layout-switch" role="group" aria-label="清单布局"><Button variant={catalogLayout==='cards'?'secondary':'ghost'} aria-label="卡片布局" aria-pressed={catalogLayout==='cards'} onClick={()=>setCatalogLayout('cards')}><SquaresFour size={17}/></Button><Button variant={catalogLayout==='list'?'secondary':'ghost'} aria-label="列表布局" aria-pressed={catalogLayout==='list'} onClick={()=>setCatalogLayout('list')}><List size={17}/></Button></div>}{view==='cards'&&<span className="entry-filter-count" aria-live="polite" aria-label="筛选结果数量">显示 <strong>{visibleScenes.length}</strong> 项</span>}<div className="entry-catalog-filters">{view==='cards'&&<Input aria-label="搜索清单场景" placeholder="搜索场景、项目或位置" value={query} onChange={event=>{setQuery(event.target.value);setEntered('');}}/>}{view==='cards'&&<><NativeSelect aria-label="场景状态" value={phase} onChange={event=>setPhase(event.target.value)}><option value="all">全部状态</option>{Object.values(sceneStates).map(state=><option key={state.label}>{state.label}</option>)}</NativeSelect><NativeSelect aria-label="场景排序" value={sort} onChange={event=>setSort(event.target.value)}><option value="phase">按进展阶段</option><option value="name">按名称排序</option></NativeSelect></>}</div></div>
 <div className={'entry-scene-items entry-layout-'+catalogLayout}>{sceneItems}{!visibleScenes.length&&<div className="entry-empty" role="status"><MagnifyingGlass size={24}/><strong>没有匹配的场景</strong><span>调整搜索关键词或状态后重试</span><Button variant="secondary" size="sm" onClick={()=>{setQuery('');setPhase('all');}}>清除筛选</Button></div>}</div>{view==='map'&&<div className="entry-map-summary" aria-live="polite"><span>{visibleScenes.filter(scene=>scene.point).length} 个场景已定位</span><span>{visibleScenes.filter(scene=>!scene.point).length} 个位置待补充</span></div>}</aside></div>

  {selected&&<section className="entry-selection" aria-label="选中场景"><header className="entry-selection-head"><h2>{selected.name}</h2><Button variant="ghost" size="sm" aria-label="关闭场景详情" onClick={()=>setSelectedId('')}><X size={16}/></Button></header><div className="entry-detail-cover"><SceneCover name={selected.name} overviewUrl={selected.overview_url}/></div><div className="entry-detail-subtitle"><small>{selected.unit_short_name}</small><span className="entry-scene-state" data-tone={sceneStates[selected.state].tone}>{stateFor(selected)}</span></div><p>{selected.description||'暂无场景描述'}</p><p><Buildings size={16}/>{selected.project}</p><p><MapPin size={16}/>{selected.address}</p><div className="entry-detail-meta"><span>位置状态</span><strong>{selected.point?'已登记':'待补充'}</strong><span>当前状态</span><strong>{stateFor(selected)}</strong>{selected.state==='published'&&<><span>发布版本</span><strong>{selected.release_version||'版本未登记'}</strong><span>发布日期</span><strong>{selected.published_at||'日期未登记'}</strong></>}</div><Button className="entry-detail-enter" size="sm" onClick={()=>setEntered(`已选择「${selected.name}」，当前为设计预览。`)}>进入场景</Button>{entered&&<p role="status">{entered}</p>}</section>}
  {view==='map'&&<><div className="entry-map-tools" aria-label="地图操作"><button aria-label="复位全国地图" title="复位全国地图" onClick={()=>map.current?.fitBounds([[73,18],[135,54]],{padding:40,duration:500})}><Crosshair size={16}/></button><button aria-label="放大" title="放大" onClick={()=>map.current?.zoomIn()}><Plus size={16}/></button><button aria-label="缩小" title="缩小" onClick={()=>map.current?.zoomOut()}><Minus size={16}/></button><button aria-label="地图配置" title="地图配置" aria-expanded={config} onClick={()=>setConfig(value=>!value)}><SlidersHorizontal size={16}/></button></div>{config&&<section className="entry-map-config" aria-label="地图配置面板"><header><strong>地图配置</strong><button aria-label="关闭地图配置" onClick={()=>setConfig(false)}><X size={17}/></button></header><span>显示维度</span><div><Button variant="secondary" aria-pressed>二维</Button><Button variant="outline" disabled>三维</Button></div><span>底图类型</span><div><Button variant="secondary" aria-pressed><MapTrifold size={18}/>数字地图</Button><Button variant="outline" disabled>卫星影像</Button></div></section>}</>}
 </div></main>;
}

createRoot(document.getElementById('root')!).render(<ThemeProvider defaultMode="light"><MapLab/></ThemeProvider>);

