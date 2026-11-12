import React,{useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Button,Input,NativeSelect,ShellSidebarFrame,Drawer,useMediaQuery} from '@vxture/design-system';
import {Cube,UploadSimple,MagnifyingGlass,ArrowsClockwise,SidebarSimple,Cloud,DownloadSimple,Users} from '@phosphor-icons/react';
import {WorkspaceHeading} from './workspace-frame';
import {useSceneDirectory} from './use-scene-directory';
import {spatialServices,serviceSpaces,selectedServiceVersion,sectionServices,serviceSections,type ServiceSection} from './spatial-service-contract';
import {ServiceNavigation} from './service-navigation';
import {ServiceListEntry} from './spatial-service-list';
import {SceneServicePage,UnavailableServiceSection} from './scene-service-page';
import {appNavigate} from './app-router';
import {sceneServiceTabs,entryServiceTab,servicePageHref,type SceneServiceTab} from './service-workspace-contract';
import './scene-catalog.css';
import './spatial-services.css';

const descriptions:Record<ServiceSection,string>={
 directory:'浏览已授权的场景服务，查看能力、发布版本与使用情况。',
 offline:'浏览各场景的离线成果，进入服务页获取固定版本的交付包。',
 online:'浏览各场景的在线服务，进入服务页查看接入与运行情况。',
 feedback:'汇总各场景的态势反馈与处理情况。',
 recipients:'查看服务对象使用的场景、服务方式与关联版本。'
};
export function SpatialServices(){
 const [params,setParams]=useSearchParams();
 const space=params.get('space')||'',publication=params.get('publication');
 const requested=params.get('section')||'directory';
 const section:ServiceSection=Object.hasOwn(serviceSections,requested)?requested as ServiceSection:'directory';
 const requestedTab=params.get('tab')||'';
 const tab:SceneServiceTab=Object.hasOwn(sceneServiceTabs,requestedTab)?requestedTab as SceneServiceTab:entryServiceTab(section);
 const query=params.get('q')||'',state=['available','unavailable'].includes(params.get('status')||'')?params.get('status')!:'all';
 const filter={query,state};
 const [revision,setRevision]=useState(0),[collapsed,setCollapsed]=useState(false),[navigationOpen,setNavigationOpen]=useState(false);
 const narrow=useMediaQuery('(max-width:639px)');
 const content=useRef<HTMLDivElement>(null),listScroll=useRef<Record<string,number>>({});
 useLayoutEffect(()=>{if(content.current)content.current.scrollTop=space?0:listScroll.current[section]||0;},[space,section]);
 useEffect(()=>setNavigationOpen(false),[section,space]);
 const [versions,setVersions]=useState<Record<string,string>>({});
 const {spaces,loading,error}=useSceneDirectory(revision);
 const groups=useMemo(()=>serviceSpaces(spatialServices(spaces)),[spaces]);
 // Refresh never changes an existing pin. Direct detail links also pin the URL.
 useEffect(()=>{setVersions(current=>{
  const next={...current};let changed=false;
  for(const group of groups)if(!Object.hasOwn(current,group.scene.id)){
   const version=selectedServiceVersion(group);
   if(version){next[group.scene.id]=version.release.id;changed=true;}
  }
  return changed?next:current;
 });},[groups]);
 const group=groups.find(value=>value.scene.id===space);
 const version=group?selectedServiceVersion(group,publication??versions[space]):undefined;
 // Legacy scene-only links become explicit fixed-version detail links once loaded.
 useEffect(()=>{if(space&&version&&publication===null)appNavigate(servicePageHref(section,space,version.release.id,tab,filter),true);},[space,version?.release.id,publication,section,tab,query,state]);
 const missingVersion=groups.some(value=>versions[value.scene.id]!==undefined&&!selectedServiceVersion(value,versions[value.scene.id]));
 const visible=groups.filter(value=>{
  const selected=selectedServiceVersion(value,versions[value.scene.id]);
  return selected&&sectionServices(selected,section).length>0&&(state==='all'||(state==='available'?selected.available:!selected.available))&&`${value.scene.name} ${value.scene.project_name||''} ${selected.release.id} ${selected.release.display_code||''} ${selected.release.version_code||''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
 });
 function updateFilter(key:string,value:string){setParams(current=>{const next=new URLSearchParams(current);if(!value||value==='all')next.delete(key);else next.set(key,value);return next;},{replace:true});}
 function changeVersion(id:string){setVersions(current=>({...current,[space]:id}));appNavigate(servicePageHref(section,space,id,tab,filter));}
 return <main className="scene-catalog spatial-services" aria-label="空间服务">
  {!narrow&&<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}><ServiceNavigation section={section} collapsed={collapsed} onToggle={()=>setCollapsed(value=>!value)}/></ShellSidebarFrame>}
  <div ref={content} className="spatial-service-content" onScroll={()=>{if(!space&&content.current)listScroll.current[section]=content.current.scrollTop;}}><div className="service-workspace-shell">
   {narrow&&<Button className="service-mobile-navigation" variant="ghost" size="sm" onClick={()=>setNavigationOpen(true)}><SidebarSimple size={16}/>功能导航</Button>}
   {space?<>
    {loading?<p role="status" className="service-list-empty">正在读取场景服务…</p>:error?<div role="alert" className="service-list-empty"><p>{error}</p><Button variant="secondary" onClick={()=>setRevision(value=>value+1)}>重新加载</Button></div>:group?<SceneServicePage group={group} version={version} tab={tab} revision={revision} onTab={value=>appNavigate(servicePageHref(section,space,publication||version?.release.id||'',value,filter))} onVersion={changeVersion} onRefresh={()=>setRevision(value=>value+1)}/>:<div className="service-list-empty" role="alert"><h2>此场景服务不可访问</h2><p>场景已不可访问，或暂无已授权的发布服务。</p><Button variant="secondary" onClick={()=>appNavigate('/services?section='+section)}>返回服务清单</Button></div>}
   </>:<>
    <WorkspaceHeading icon={({directory:Cube,online:Cloud,offline:DownloadSimple,feedback:UploadSimple,recipients:Users})[section]} title={serviceSections[section]} description={descriptions[section]} actions={<Button size="icon-sm" variant="ghost" aria-label="刷新服务清单" onClick={()=>setRevision(value=>value+1)}><ArrowsClockwise size={16}/></Button>}/>
    {section==='feedback'||section==='recipients'?<UnavailableServiceSection section={section}/>:<section aria-label={`${serviceSections[section]}清单`}>
     <div className="service-list-toolbar"><span className="service-list-count" aria-live="polite">{loading?'读取中…':error?'暂不可读':`${visible.length} 项场景服务`}</span><div className="service-list-filters"><div className="service-list-search"><MagnifyingGlass size={16}/><Input aria-label="搜索服务清单" placeholder="搜索场景、项目或版本" value={query} onChange={event=>updateFilter('q',event.target.value)}/></div><NativeSelect wrapperClassName="service-list-state-select" aria-label="发布状态" value={state} onChange={event=>updateFilter('status',event.target.value)}><option value="all">全部发布状态</option><option value="available">已发布</option><option value="unavailable">暂停 / 退役 / 待核对</option></NativeSelect></div></div>
     {missingVersion&&<p role="alert" className="spatial-service-section-note">部分已选版本不再可见，相关操作已停止。<Button variant="link" size="sm" onClick={()=>setVersions(current=>Object.fromEntries(Object.entries(current).filter(([id,pin])=>{const value=groups.find(item=>item.scene.id===id);return !value||!!selectedServiceVersion(value,pin);}))) }>重新确认版本</Button></p>}
     {loading?<p role="status" className="service-list-empty">正在读取服务清单…</p>:error?<div role="alert" className="service-list-empty"><p>{error}</p><Button variant="secondary" onClick={()=>setRevision(value=>value+1)}>重新加载</Button></div>:<div className="service-directory-list">{visible.map(value=><ServiceListEntry key={value.scene.id} group={value} version={selectedServiceVersion(value,versions[value.scene.id])!} section={section} filter={filter}/>)}{!visible.length&&<div className="service-list-empty"><h2>{groups.length?'没有匹配的服务':'暂无已授权的场景服务'}</h2><p>{groups.length?'调整关键词或发布状态后重试。':'场景发布成果并授权后，服务会显示在这里。'}</p>{(query||state!=='all')&&<Button variant="secondary" onClick={()=>setParams({section},{replace:true})}>清除筛选</Button>}</div>}</div>}
    </section>}
   </>}
  </div></div>
  <Drawer open={narrow&&navigationOpen} onClose={()=>setNavigationOpen(false)} side="left" width="sm" title="功能导航" closeLabel="关闭功能导航"><ServiceNavigation section={section} collapsed={false} onToggle={()=>setNavigationOpen(false)}/></Drawer>
 </main>;
}
