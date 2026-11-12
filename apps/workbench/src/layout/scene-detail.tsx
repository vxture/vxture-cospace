import React,{useEffect,useState} from 'react';
import {businessEndpoint} from './business-endpoint';
import {altitudeLabel} from './geographic-location';
import {Button,Drawer,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {ArrowRight,ArrowSquareOut,Cube,Database,FlowArrow,Package,Gear,DotsThreeVertical} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {SceneCover} from './scene-cover';
import {scenePhases,scenePhase,sceneEntryHref,sceneDestinations,currentRelease,publicationAvailable,publicationLabel} from './scene-catalog-contract';
import {realScreenHref} from './real-space-data';

const destinationIcons={data:Database,build:FlowArrow,delivery:Package,settings:Gear};
export function SceneMoreMenu({scene,onDetails}:{scene:SceneSpace;onDetails:()=>void}){
 const release=currentRelease(scene);
 return <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-xl" variant="secondary" aria-label={scene.name+'更多操作'}><DotsThreeVertical size={16}/></Button></DropdownMenuTrigger>
  <DropdownMenuContent align="end" className="scene-action-menu">
   <DropdownMenuItem onSelect={onDetails}><Cube size={16}/>场景详情</DropdownMenuItem>
   <DropdownMenuItem asChild><a href={sceneEntryHref(scene)} {...(release?{target:'_blank',rel:'noopener noreferrer'}:{})}><ArrowRight size={16}/>进入场景</a></DropdownMenuItem>
   <DropdownMenuSeparator/>
   {sceneDestinations(scene).map(item=>{const Icon=destinationIcons[item.key as keyof typeof destinationIcons];return item.enabled?<DropdownMenuItem key={item.key} asChild><a href={item.href}><Icon size={16}/>{item.label}</a></DropdownMenuItem>:<DropdownMenuItem key={item.key} disabled title="当前账号无此操作权限"><Icon size={16}/>{item.label}</DropdownMenuItem>;})}
  </DropdownMenuContent>
 </DropdownMenu>;
}
export function SceneDetail({scene,onClose,mapOverlay=false}:{scene?:SceneSpace;onClose:()=>void;mapOverlay?:boolean}){
 const release=scene&&currentRelease(scene),state=scene&&scenePhases[scenePhase(scene)];
 return <Drawer open={!!scene} onClose={onClose} side="right" width="md" title="场景详情" description={scene?.name} closeLabel="关闭场景详情" className={'scene-detail-panel'+(mapOverlay?' scene-map-detail-panel':'')}
  footer={scene&&<><Button size="xl" variant="secondary" onClick={onClose}>关闭</Button>{release?<Button asChild size="xl"><a href={sceneEntryHref(scene)} target="_blank" rel="noopener noreferrer">进入场景<ArrowRight size={16}/></a></Button>:<Button size="xl" disabled>暂无可用发布</Button>}</>}>
  {scene&&<div className="scene-detail-content" data-tone={state?.tone}>
   <div className="scene-detail-cover"><SceneCover name={scene.name} overviewUrl={scene.overview_url}/></div>
   <section aria-label="空间概览"><div className="scene-detail-section-heading"><h3>空间概览</h3><span className="catalog-card-status">{state?.label}</span></div><h2>{scene.name}</h2><p className="scene-detail-project">{scene.project_name||'未指定项目'}</p><p>{scene.description||'暂无场景描述'}</p></section>
   <ScenePublications key={scene.id} scene={scene}/>
   <section aria-label="空间位置"><h3>空间位置</h3><dl><dt>地址</dt><dd>{scene.address||'位置未登记'}</dd><dt>地图坐标</dt><dd>{scene.location?`${scene.location.longitude}, ${scene.location.latitude} · ${scene.location.crs}`:'暂无定位坐标'}</dd><dt>高度</dt><dd>{altitudeLabel(scene.location)}</dd><dt>坐标来源</dt><dd>{scene.location?.source||'未登记'}</dd></dl></section>
   <section aria-label="场景工作"><h3>场景工作</h3><div className="scene-detail-links">{sceneDestinations(scene).map(item=>{const Icon=destinationIcons[item.key as keyof typeof destinationIcons];return item.enabled?<Button asChild size="xl" variant="secondary" key={item.key}><a href={item.href}><Icon size={16}/>{item.label}<ArrowRight size={14}/></a></Button>:<Button key={item.key} size="xl" variant="secondary" disabled title="当前账号无此操作权限"><Icon size={16}/>{item.label}</Button>;})}</div></section>
  </div>}
 </Drawer>;
}

function ScenePublications({scene}:{scene:SceneSpace}){
 const [mapping,setMapping]=useState<{space:string;ids:string[]}|null>(null),[failed,setFailed]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setMapping(null);setFailed(false);
  fetch(`${businessEndpoint}/api/workflow?${new URLSearchParams({space_id:scene.id})}`,{cache:'no-store',signal:controller.signal})
   .then(async response=>{
    if(!response.ok)throw Error('workflow unavailable');
    const report=await response.json();
    if(report.space_id!==scene.id||!Array.isArray(report.summary?.publications))throw Error('workflow mismatch');
    if(!controller.signal.aborted)setMapping({space:scene.id,ids:report.summary.publications.filter((p:{publication_id?:string;matches_current?:boolean})=>p.matches_current===true&&typeof p.publication_id==='string').map((p:{publication_id:string})=>p.publication_id)});
   }).catch(()=>{if(!controller.signal.aborted)setFailed(true);});
  return()=>controller.abort();
 },[scene.id,revision]);
 const releases=[...(scene.publications||[])].sort((a,b)=>(Date.parse(b.created_at)||0)-(Date.parse(a.created_at)||0));
 return <section aria-label="发布版本"><div className="scene-detail-section-heading"><h3>发布版本</h3><span>{releases.length} 个版本</span></div>
  {!releases.length?<p>尚无固定发布，可在服务发布中创建。</p>:<>
   {failed&&<div className="scene-publication-note" role="status">候选对应关系暂不可用<Button size="sm" variant="ghost" onClick={()=>setRevision(v=>v+1)}>重试</Button></div>}
   <div className="scene-publications">{releases.map(release=>{
    const available=publicationAvailable(release),label=available?'已发布':release.lifecycle_state==='paused'?'已暂停':release.lifecycle_state==='retired'?'已退役':'不可用';
    return <article className="scene-publication-card" key={release.id} aria-label={publicationLabel(release)}>
     <div className="scene-publication-cover"><SceneCover name={scene.name} overviewUrl={scene.overview_url}/></div>
     <div className="scene-publication-copy"><div className="scene-detail-section-heading"><h4 title={release.id}>{publicationLabel(release)}</h4><span className="catalog-card-status">{label}</span></div>
      <p>{release.id===scene.publication_id?'当前指定发布 · ':''}{mapping?.space===scene.id&&mapping.ids.includes(release.id)?'对应当前工作候选':'固定发布版本'}</p>
      <div className="scene-publication-footer"><time dateTime={release.created_at}>{new Date(release.created_at).toLocaleString('zh-CN',{hour12:false})}</time>{available?<Button asChild size="sm" variant="secondary"><a href={realScreenHref(scene.id,release.id)} target="_blank" rel="noopener noreferrer">打开场景<ArrowSquareOut size={16}/></a></Button>:<Button disabled size="sm" variant="secondary">打开场景</Button>}</div>
     </div>
    </article>;
   })}</div>
  </>}
 </section>;
}
