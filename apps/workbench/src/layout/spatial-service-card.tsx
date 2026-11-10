import React from 'react';
import {Button,StatusBadge,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuLabel,DropdownMenuRadioGroup,DropdownMenuRadioItem} from '@vxture/design-system';
import {Cube,DotsThreeVertical,DownloadSimple,Code,ArrowSquareOut,Info,CaretDown} from '@phosphor-icons/react';
import {type ServiceSpace,type ServiceVersion,type ServiceSection,type SpatialService,serviceResourcePath} from './spatial-service-contract';
import {realScreenHref} from './real-space-data';
import {SceneCover} from './scene-cover';
import {businessEndpoint} from './business-endpoint';

const states={active:'可用',paused:'已暂停',retired:'已退役',unknown:'待核对'};
export function ServiceCard({group,version,section,onVersion,onDetails}:{group:ServiceSpace;version:ServiceVersion;section:ServiceSection;onVersion:(publication:string)=>void;onDetails:(item:SpatialService)=>void}){
 const {scene}=group;
 const offline=version.services.find(item=>item.kind==='offline');
 const query=version.services.find(item=>item.kind==='query');
 const preview=version.services.find(item=>item.kind==='preview');
 const primary=section==='offline'?offline:section==='online'?query:offline||query||preview;
 const title=section==='offline'?'离线交付':section==='online'?'在线服务':'空间态势';
 return <article className="spatial-service-card" aria-label={`${scene.name} · ${title}`}>
  <header className="spatial-service-heading"><span className="spatial-service-symbol"><Cube size={18}/></span><div className="spatial-service-title"><h2 title={scene.name}><button onClick={()=>primary&&onDetails(primary)}>{scene.name}</button></h2><p title={scene.project_name}>{scene.project_name||'未指定项目'}</p></div><StatusBadge tone={version.available?'success':'neutral'}>{states[version.state]}</StatusBadge></header>
  <button className="spatial-service-cover" onClick={()=>primary&&onDetails(primary)} aria-label={`查看${scene.name}服务详情`}>
   <SceneCover overviewUrl={scene.overview_url} name={scene.name}/>
  </button>
  <div className="spatial-service-body"><p className="spatial-service-description">{scene.description||'面向具身智能体提供固定版本的空间态势成果。'}</p><div className="spatial-service-capabilities" aria-label="已授权能力">{offline&&<span>离线交付</span>}{query&&<span>在线查询</span>}{preview&&<span>态势预览</span>}</div></div>
  <footer className="spatial-service-footer"><DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="spatial-service-version" aria-label={`${scene.name}成果版本`} title={version.release.id}>ver: {version.release.id.slice(-8)}<CaretDown size={12}/></Button></DropdownMenuTrigger><DropdownMenuContent align="start" className="scene-action-menu"><DropdownMenuLabel>{group.versions.length} 个成果版本</DropdownMenuLabel><DropdownMenuRadioGroup value={version.release.id} onValueChange={onVersion}>{group.versions.map(value=><DropdownMenuRadioItem key={value.release.id} value={value.release.id}><span title={value.release.id}>ver: {value.release.id.slice(-8)} · {states[value.state]}<small className="block text-label-small text-muted-foreground">{value.release.created_at.slice(0,10)}</small></span></DropdownMenuRadioItem>)}</DropdownMenuRadioGroup></DropdownMenuContent></DropdownMenu><div className="spatial-service-actions">
   <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-xl" variant="secondary" aria-label={`${scene.name}更多操作`}><DotsThreeVertical size={16}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="scene-action-menu">
    <DropdownMenuItem onSelect={()=>primary&&onDetails(primary)}><Info size={16}/>服务详情</DropdownMenuItem>
    <DropdownMenuItem disabled={!offline||!version.available} onSelect={()=>offline&&onDetails(offline)}><DownloadSimple size={16}/>离线交付</DropdownMenuItem>
    <DropdownMenuItem disabled={!query||!version.available} onSelect={()=>query&&onDetails(query)}><Code size={16}/>在线查询</DropdownMenuItem>
    {preview&&version.available?<DropdownMenuItem asChild><a href={realScreenHref(scene.id,version.release.id)} target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={16}/>态势预览</a></DropdownMenuItem>:<DropdownMenuItem disabled><ArrowSquareOut size={16}/>态势预览</DropdownMenuItem>}
   </DropdownMenuContent></DropdownMenu>
   {section==='offline'&&offline?(version.available?<Button size="xl" asChild><a href={businessEndpoint+serviceResourcePath(offline)} target="_blank" rel="noopener noreferrer">获取成果<DownloadSimple size={14}/></a></Button>:<Button size="xl" disabled>获取成果</Button>):<Button size="xl" onClick={()=>primary&&onDetails(primary)}>{section==='online'?'服务接入':'查看服务'}</Button>}
  </div></footer>
 </article>;
}
