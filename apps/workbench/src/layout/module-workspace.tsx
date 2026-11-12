import {canOpenSceneWorkspace,sceneInformationHref} from './management-contract';
import {appNavigate,appLocation} from './app-router';
import {runGuarded} from './unsaved-navigation';
import {sceneLinkFromUrl} from './navigation-contract';
import {useSceneDirectory} from './use-scene-directory';
import {CapabilityNavigation,SceneScope} from './capability-navigation';
import React,{createContext,useContext,useEffect,useMemo,useState} from 'react';
import {Button} from '@vxture/design-system';
import {SidebarSimple,CaretRight,ArrowClockwise,Cube} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {moduleNames,moduleGroups} from './product-navigation';
import {useRecordNavigation,RecordNavigationProvider} from './record-navigation';
import {SceneCapabilities} from './scene-capabilities';
import {SceneProgress} from './scene-progress';
import './data-workspace.css';
import './module-workspace.css';

type ModuleRoute=keyof typeof moduleNames;
const EmbeddedScene=createContext(false);
export function useEmbeddedScene(){return useContext(EmbeddedScene);}
const descriptions:Record<ModuleRoute,string>={space:'查看场景信息与固定发布版本。',delivery:'管理当前场景的发布版本、在线服务与离线交付。',data:'按场景空间管理资料、历史版本与发布成果。',build:'从当前场景的资料生成模型候选，核对后选择版本。',ontology:'管理共用的类型、属性与关系规则；场景实例在空间关联中维护。',association:'将固定本体版本应用到当前场景，维护对象、几何与业务关联。'};

export function ModuleWorkspace({route,children}:{route:ModuleRoute;children:React.ReactNode}){
 const platform=usePlatformSession(),target=useRecordNavigation();
 const [revision,setRevision]=useState(0);
 const {spaces,loading,error}=useSceneDirectory(revision);
 const [sidebar,setSidebar]=useState(()=>innerWidth>620);
 useEffect(()=>{const media=matchMedia('(max-width:620px)');const update=()=>{if(media.matches)setSidebar(false);};media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
 const scene=spaces.find(s=>s.id===target.space),group=moduleGroups.find(g=>g.items.some(i=>i.route===route));
 const allowed=!!scene&&(!platform||canOpenSceneWorkspace(route,target.tab,scene.capabilities||[]));
 const common=route==='ontology';
 const capabilities=useMemo(()=>scene?.capabilities||[],[scene?.capabilities]);
 const renderContent=()=>{
  if(common)return <RecordNavigationProvider value={target}><EmbeddedScene.Provider value>{children}</EmbeddedScene.Provider></RecordNavigationProvider>;
  if(loading)return <output className="data-subtle">正在读取场景空间…</output>;
  if(error&&!scene)return <div role="alert" className="data-empty"><p>{error}</p><Button variant="outline" onClick={()=>setRevision(v=>v+1)}>重试</Button></div>;
  if(!scene)return <div className="data-empty"><Cube size={36}/><h2>选择场景空间</h2><p>{target.space?'所选场景无权访问或不存在，请重新选择。':'从上方选择操作场景，继续处理资料、模型与发布。'}</p></div>;
  if(!allowed)return <div className="data-empty" role="alert"><h2>当前场景无此操作权限</h2><p>可切换有权限的场景空间，或返回我的场景。</p></div>;
  return <RecordNavigationProvider value={target}><EmbeddedScene.Provider value><SceneCapabilities.Provider value={capabilities}>{route!=='build'&&route!=='delivery'&&route!=='association'&&<SceneProgress key={[scene.id,target.job,target.publication,target.input].join(':')} space={scene.id} name={scene.name} input={target.input} revision={revision}/>} {children}</SceneCapabilities.Provider></EmbeddedScene.Provider></RecordNavigationProvider>;
 };
 let moduleClass='';
 if(route==='build')moduleClass='build-module';
 else if(route==='delivery')moduleClass='publication-module';
 else if(route==='association')moduleClass='association-module';
 return <main className="data-route-shell min-h-0 flex-1 overflow-hidden"><div className={`data-workspace module-workspace ${moduleClass} ${sidebar?'':'data-sidebar-hidden'}`}>
  {route!=='build'&&route!=='delivery'&&route!=='association'&&<CapabilityNavigation route={route}/> }
  <section className="data-main" aria-label={`${moduleNames[route]}工作区`}>
   <SceneScope spaces={spaces} current={target.space} onChoose={id=>{appNavigate(sceneLinkFromUrl(route,id,appLocation()));}} loading={loading} error={error} onRefresh={()=>setRevision(v=>v+1)}/>
   <header className="data-heading"><div className="data-heading-copy"><div className="data-breadcrumb"><Button variant="outline" size="sm" className="data-icon-button data-sidebar-toggle" aria-label={sidebar?'收起能力导航':'展开能力导航'} aria-expanded={sidebar} aria-controls="data-scene-sidebar" onClick={()=>setSidebar(v=>!v)}><SidebarSimple size={16}/></Button><span>{group?.title}</span><CaretRight size={12}/><span>{moduleNames[route]}</span><CaretRight size={12}/><span className="data-breadcrumb-scene">{common?'共用规则库':scene?.name||'选择场景空间'}</span></div><h1>{moduleNames[route]}</h1><p>{descriptions[route]}</p></div><div className="data-heading-actions"><Button variant="outline" size="sm" className="data-icon-button" aria-label="刷新场景空间目录" onClick={()=>{void runGuarded(()=>setRevision(v=>v+1));}} disabled={loading}><ArrowClockwise size={16}/></Button><Button asChild size="sm" variant="outline"><a href={sceneInformationHref(target.space)}>基本信息</a></Button></div></header>

   <div className="module-body">
    {common&&<p className="module-scope-note">规则库为共用定义，不属于某个模型版本。{scene?`当前关联上下文：${scene.name}。`:''}应用到场景时固定本体版本与摘要。</p>}
    {renderContent()}
   </div>
  </section>
 </div></main>;
}
