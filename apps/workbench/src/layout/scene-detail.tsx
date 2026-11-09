import React from 'react';
import {Button,Drawer,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {ArrowRight,ArrowSquareOut,Cube,Database,FlowArrow,Package,Gear,DotsThreeVertical} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {SceneCover} from './scene-cover';
import {scenePhases,scenePhase,sceneWorkspaceHref,sceneDestinations} from './scene-catalog-contract';
import {realScreenHref} from './real-space-data';

const destinationIcons={data:Database,build:FlowArrow,delivery:Package,settings:Gear};
export const currentRelease=(scene:SceneSpace)=>scene.publications?.find(p=>p.id===scene.publication_id);
export function SceneMoreMenu({scene,onDetails}:{scene:SceneSpace;onDetails:()=>void}){
 const release=currentRelease(scene);
 return <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-xl" variant="secondary" aria-label={scene.name+'更多操作'}><DotsThreeVertical size={16}/></Button></DropdownMenuTrigger>
  <DropdownMenuContent align="end" className="scene-action-menu">
   <DropdownMenuItem onSelect={onDetails}><Cube size={16}/>场景详情</DropdownMenuItem>
   <DropdownMenuItem asChild><a href={sceneWorkspaceHref(scene.id)}><ArrowRight size={16}/>进入场景</a></DropdownMenuItem>
   <DropdownMenuSeparator/>
   {sceneDestinations(scene).map(item=>{const Icon=destinationIcons[item.key as keyof typeof destinationIcons];return item.enabled?<DropdownMenuItem key={item.key} asChild><a href={item.href}><Icon size={16}/>{item.label}</a></DropdownMenuItem>:<DropdownMenuItem key={item.key} disabled title="当前账号无此操作权限"><Icon size={16}/>{item.label}</DropdownMenuItem>;})}
   <DropdownMenuSeparator/>
   {release?<DropdownMenuItem asChild><a href={realScreenHref(scene.id,release.id)} target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={16}/>打开发布版本</a></DropdownMenuItem>:<DropdownMenuItem disabled title="暂无可用的发布版本"><ArrowSquareOut size={16}/>打开发布版本</DropdownMenuItem>}
  </DropdownMenuContent>
 </DropdownMenu>;
}
export function SceneDetail({scene,onClose}:{scene?:SceneSpace;onClose:()=>void}){
 const release=scene&&currentRelease(scene),state=scene&&scenePhases[scenePhase(scene)];
 return <Drawer open={!!scene} onClose={onClose} side="right" width="md" title="场景详情" description={scene?.name} closeLabel="关闭场景详情" className="scene-detail-panel"
  footer={scene&&<><Button size="xl" variant="secondary" onClick={onClose}>关闭</Button><Button asChild size="xl"><a href={sceneWorkspaceHref(scene.id)}>进入场景<ArrowRight size={16}/></a></Button></>}>
  {scene&&<div className="scene-detail-content" data-tone={state?.tone}>
   <div className="scene-detail-cover"><SceneCover name={scene.name} overviewUrl={scene.overview_url}/></div>
   <section aria-label="空间概览"><div className="scene-detail-section-heading"><h3>空间概览</h3><span className="catalog-card-status">{state?.label}</span></div><h2>{scene.name}</h2><p className="scene-detail-project">{scene.project_name||'未指定项目'}</p><p>{scene.description||'暂无场景描述'}</p></section>
   <section aria-label="发布信息"><h3>发布信息</h3><dl><dt>当前版本</dt><dd title={release?.id}>{release?'ver: '+release.id.slice(-8):'暂无可用版本'}</dd><dt>发布日期</dt><dd>{release?<time dateTime={release.created_at}>{new Date(release.created_at).toLocaleString('zh-CN',{hour12:false})}</time>:'—'}</dd><dt>历史发布</dt><dd>{scene.publications?.length||0} 个版本</dd></dl></section>
   <section aria-label="空间位置"><h3>空间位置</h3><dl><dt>地址</dt><dd>{scene.address||'位置未登记'}</dd><dt>地图坐标</dt><dd>{scene.location?`${scene.location.longitude}, ${scene.location.latitude} · ${scene.location.crs}`:'暂无定位坐标'}</dd></dl></section>
   <section aria-label="场景工作"><h3>场景工作</h3><div className="scene-detail-links">{sceneDestinations(scene).map(item=>{const Icon=destinationIcons[item.key as keyof typeof destinationIcons];return item.enabled?<Button asChild size="xl" variant="secondary" key={item.key}><a href={item.href}><Icon size={16}/>{item.label}<ArrowRight size={14}/></a></Button>:<Button key={item.key} size="xl" variant="secondary" disabled title="当前账号无此操作权限"><Icon size={16}/>{item.label}</Button>;})}</div></section>
  </div>}
 </Drawer>;
}
