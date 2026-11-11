import {WorkspaceHeading} from './workspace-frame';
import React,{useEffect,useMemo,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Button,Input,NativeSelect,ViewHeader,SegmentedControl,ShellSidebarFrame,Drawer,useMediaQuery,StatusBadge,Icon} from '@vxture/design-system';
import {Cube,Robot,UploadSimple,MagnifyingGlass,ArrowsClockwise,List,SquaresFour,SidebarSimple,Cloud,DownloadSimple,Users} from '@phosphor-icons/react';
import {useSceneDirectory} from './use-scene-directory';
import {spatialServices,serviceSpaces,selectedServiceVersion,sectionServices,serviceSections,type ServiceSection,type SpatialService} from './spatial-service-contract';
import {ServiceNavigation,serviceSectionIcons} from './service-navigation';
import {ServiceCard} from './spatial-service-card';
import {ServiceDetail} from './spatial-service-detail';
import {OnlineServiceMonitor} from './online-service-monitor';
import {useRecordNavigation} from './record-navigation';
import './scene-catalog.css';
import './spatial-services.css';

const descriptions:Record<ServiceSection,string>={
 directory:'一套空间态势，为多类具身智能体提供共享服务。',
 offline:'获取指定版本的空间态势成果，导入具身智能体后独立使用。',
 online:'监测空间态势服务调用，核对接入与版本状态，保障共享服务。',
 feedback:'独立接入空间观测与变化证据反馈，无需先使用在线服务。',
 recipients:'查看空间态势服务了哪些具身智能体，关联交付、接入与成果版本。'
};
function UnavailableSection({section}:{section:'feedback'|'recipients'}){
 const feedback=section==='feedback';
 const SectionIcon=feedback?UploadSimple:Robot;
 return <section className="spatial-service-unavailable" aria-label={serviceSections[section]}><SectionIcon size={32}/><h2>{feedback?'态势反馈接入尚未开放':'服务对象登记尚未开放'}</h2><p>{feedback?'态势反馈将提供接入配置、数据约定、接口接入与接收诊断。反馈处理和空间更新由其他板块承接。':'支持登记离线交付对象，识别在线接入对象，并查看各对象关联的空间与使用版本。'}</p><StatusBadge tone="neutral">尚未开放</StatusBadge></section>;
}
export function SpatialServices(){
 const {space}=useRecordNavigation();
 const [params]=useSearchParams();
 const tab=params.get('section')||'directory';
 const section:ServiceSection=Object.hasOwn(serviceSections,tab)?tab as ServiceSection:'directory';
 const [revision,setRevision]=useState(0),[query,setQuery]=useState(''),[state,setState]=useState('available'),[selected,setSelected]=useState(''),[layout,setLayout]=useState('cards');
 const [collapsed,setCollapsed]=useState(false),[navigationOpen,setNavigationOpen]=useState(false);
 const narrow=useMediaQuery('(max-width:639px)');
 useEffect(()=>{setSelected('');setQuery('');setState('available');setNavigationOpen(false);},[section,space]);
 const [versions,setVersions]=useState<Record<string,string>>({});
 const {spaces,loading,error}=useSceneDirectory(revision);
 const items=useMemo(()=>spatialServices(spaces),[spaces]);
 const groups=useMemo(()=>serviceSpaces(items),[items]);
 // Pin the first visible version; refresh must not switch consumers to a new release.
 useEffect(()=>{setVersions(current=>{
  const next={...current};let changed=false;
  for(const group of groups)if(!Object.hasOwn(current,group.scene.id)){
   const version=selectedServiceVersion(group);
   if(version){next[group.scene.id]=version.release.id;changed=true;}
  }
  return changed?next:current;
 });},[groups]);
 const missingVersion=groups.some(group=>versions[group.scene.id]!==undefined&&!selectedServiceVersion(group,versions[group.scene.id]));
 const visible=groups.filter(group=>{
  const version=selectedServiceVersion(group,versions[group.scene.id]);
  const match=query.trim().toLocaleLowerCase();
  return version&&(section!=='online'||group.scene.id===space)&&sectionServices(version,section).length>0&&(state==='all'||(state==='available'?version.available:!version.available))&&`${group.scene.name} ${group.scene.project_name||''} ${group.scene.description||''} ${version.release.id}`.toLocaleLowerCase().includes(match);
 });
 const detail=!error?items.find(item=>item.id===selected):undefined;
 const detailItems=detail?items.filter(item=>item.scene.id===detail.scene.id&&item.release.id===detail.release.id):[];
 function chooseVersion(space:string,publication:string){setVersions(current=>({...current,[space]:publication}));setState('all');setSelected('');}
 const catalog=section!=='feedback'&&section!=='recipients';
 return <main className="scene-catalog spatial-services" aria-label="空间服务">
  {!narrow&&<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}><ServiceNavigation section={section} collapsed={collapsed} onToggle={()=>setCollapsed(value=>!value)}/></ShellSidebarFrame>}
  <div className="spatial-service-content"><div className="scene-catalog-shell">
  {narrow&&<Button variant="ghost" size="sm" onClick={()=>setNavigationOpen(true)}><SidebarSimple size={16}/>功能导航</Button>}
  <WorkspaceHeading icon={({directory:Cube,online:Cloud,offline:DownloadSimple,feedback:UploadSimple,recipients:Users})[section]} title={serviceSections[section]} secondary={catalog&&section!=='online'?<span className="scene-total" aria-label="空间总数">{groups.length}</span>:undefined} description={descriptions[section]}/>

   {section==='online'&&<OnlineServiceMonitor key={space} space={space} scene={!error?spaces.find(scene=>scene.id===space):undefined} revision={revision}/>}
   {catalog&&(section!=='online'||!!space)?<section aria-label={serviceSections[section]}>
    {missingVersion&&<p role="alert" className="spatial-service-section-note">已选版本不再可见，相关空间的操作已停止。请重新确认版本。<Button variant="link" size="sm" onClick={()=>setVersions(current=>Object.fromEntries(Object.entries(current).filter(([id,publication])=>{const group=groups.find(value=>value.scene.id===id);return !group||!!selectedServiceVersion(group,publication);}))) }>重新选择版本</Button></p>}
    <div className="scene-catalog-toolbar" aria-label="空间服务筛选"><SegmentedControl value={layout} onChange={setLayout} size="md" className="h-control-xl p-2xs" ariaLabel="服务布局" items={[{value:'list',label:<List size={20}/>,ariaLabel:'列表布局'},{value:'cards',label:<SquaresFour size={20}/>,ariaLabel:'卡片布局'}]}/><span className="scene-result-count" aria-live="polite">筛选 <strong>{visible.length}</strong> 个空间</span><div className="scene-catalog-filters"><div className="scene-catalog-search"><MagnifyingGlass size={16}/><Input aria-label="搜索空间服务" placeholder="搜索空间、项目或当前版本" value={query} onChange={event=>setQuery(event.target.value)}/></div><NativeSelect wrapperClassName="scene-catalog-select" aria-label="版本状态" value={state} onChange={event=>setState(event.target.value)}><option value="available">可用版本</option><option value="all">全部状态</option><option value="unavailable">不可用版本</option></NativeSelect><Button size="icon-xl" variant="outline" aria-label="刷新空间服务" onClick={()=>setRevision(value=>value+1)}><ArrowsClockwise size={16}/></Button></div></div>
    {loading?<p role="status" className="scene-catalog-empty">正在读取空间服务…</p>:error?<div role="alert" className="scene-catalog-empty"><p>{error}</p><Button size="xl" variant="secondary" onClick={()=>setRevision(value=>value+1)}>重新加载</Button></div>:<div className={'scene-catalog-items spatial-service-grid'+(layout==='list'?' spatial-service-list scene-catalog-list':'')}>{visible.map(group=><ServiceCard key={group.scene.id} group={group} version={selectedServiceVersion(group,versions[group.scene.id])!} section={section} onVersion={publication=>chooseVersion(group.scene.id,publication)} onDetails={(item:SpatialService)=>setSelected(item.id)}/>)}{!visible.length&&<div className="scene-catalog-empty"><Cube size={28}/><h2>{groups.length?'没有匹配的空间态势服务':'暂无已授权的空间态势成果'}</h2><p>{groups.length?'调整关键词或版本状态后重试。':'请联系空间提供方发布成果并分配使用权限。'}</p>{groups.length>0&&<Button size="xl" variant="secondary" onClick={()=>{setQuery('');setState('all');}}>清除筛选</Button>}</div>}</div>}
   </section>:!catalog&&<UnavailableSection section={section as 'feedback'|'recipients'}/>}
 </div></div>
 <Drawer open={narrow&&navigationOpen} onClose={()=>setNavigationOpen(false)} side="left" width="sm" title="功能导航" closeLabel="关闭功能导航"><ServiceNavigation section={section} collapsed={false} onToggle={()=>setNavigationOpen(false)}/></Drawer>
 <ServiceDetail key={detail?`${detail.scene.id}:${detail.release.id}`:'closed'} item={detail} items={detailItems} onChoose={item=>setSelected(item.id)} onClose={()=>setSelected('')}/></main>;
}
