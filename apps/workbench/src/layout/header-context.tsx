import {useSceneControls} from './scene-selection';
import React,{useState} from 'react';
import {Button,Input,Popover,PopoverTrigger,ShellPanelContent,ShellPanelRow} from '@vxture/design-system';
import {Buildings,Cube,CaretDown,CheckCircle,MagnifyingGlass,WarningCircle} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {useRecordNavigation} from './record-navigation';
import {useSceneDirectory} from './use-scene-directory';
import {appLocation,appNavigate} from './app-router';
import {headerSceneLinkFromUrl} from './navigation-contract';

export function HeaderContext(){
 const {selectScene,mapActive}=useSceneControls();
 const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[revision,setRevision]=useState(0);
 const session=usePlatformSession(),navigation=useRecordNavigation(),{spaces,loading,error}=useSceneDirectory(revision);
 const user=session?.user,organization=user?.org_name||(user?.org_type==='personal'?'个人空间':'组织信息待补全');
 const selected=spaces.find(scene=>scene.id===navigation.space);
 let sceneName='未选择场景';
 if(navigation.space)sceneName=selected?.name||(loading?'读取场景中…':'场景不可用');
 if(error&&navigation.space)sceneName='场景暂不可读';
 const term=query.trim().toLocaleLowerCase(),visible=spaces.filter(scene=>[scene.name,scene.project_name||''].some(value=>value.toLocaleLowerCase().includes(term)));
 return <div className="header-context" aria-label="组织与场景"><span className="header-context-organization" title={organization}><Buildings size={14}/><span>{organization}</span></span><span className="header-context-divider" aria-hidden="true"/>
  {mapActive?<span className="header-context-scene" title={sceneName}><Cube size={14}/><span>{sceneName}</span></span>:<Popover open={open} onOpenChange={value=>{setOpen(value);if(value)setQuery('');}}><PopoverTrigger asChild><Button variant="ghost" size="sm" className="header-scene-trigger" data-warning={!selected||undefined} title={sceneName}><span className="header-context-scene">{selected?<Cube size={14}/>:<WarningCircle size={14}/>}<span>{sceneName}</span></span><CaretDown size={12}/></Button></PopoverTrigger>
   <ShellPanelContent align="start" sideOffset={8} className="header-scene-panel" aria-label="选择场景空间">
    <div className="relative"><MagnifyingGlass size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"/><Input autoFocus aria-label="搜索空间" placeholder="搜索空间或归属名称" className="pl-9 text-body-small" value={query} onChange={event=>setQuery(event.target.value)}/></div>
    <div className="header-scene-options" aria-label="空间清单">
     {loading&&<p role="status" className="p-sm text-body-small text-muted-foreground">正在读取空间…</p>}
     {error&&<div role="alert" className="p-sm text-body-small text-muted-foreground"><p>{error}</p><Button size="sm" variant="ghost" onClick={()=>setRevision(value=>value+1)}>重试</Button></div>}
     {visible.map(scene=><ShellPanelRow key={scene.id} icon="cube" label={scene.name} description={scene.project_name||'未指定项目'} active={scene.id===navigation.space} chevron={false} value={scene.id===navigation.space?<CheckCircle size={18} weight="fill" className="text-primary" aria-label="当前选中"/>:undefined} onClick={()=>{setOpen(false);if(scene.id!==navigation.space){selectScene(scene.id);const href=headerSceneLinkFromUrl(scene.id,appLocation());if(href!==appLocation())appNavigate(href);}}}/>)}
     {!loading&&!error&&!visible.length&&<p role="status" className="p-sm text-body-small text-muted-foreground">{spaces.length?'没有匹配的空间':'暂无可访问的空间'}</p>}
    </div>
   </ShellPanelContent>
  </Popover>}
 </div>;
}
