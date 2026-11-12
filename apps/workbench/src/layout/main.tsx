import {ManagementFrame} from './management-frame';
import {ManagementWorkspace} from './management-workspace';
import {managementHref} from './management-contract';
import {Gear} from '@phosphor-icons/react';
import {ToastProvider} from '@vxture/design-system';
import {ProductUserMenu} from './user-menu';
import {HeaderContext} from './header-context';
import {SceneSelection} from './scene-selection';
import {SceneCatalog} from './scene-catalog';
import {SpatialServices} from './spatial-services';
import {createBrowserRouter,RouterProvider} from 'react-router-dom';
import {bindAppRouter,subscribeAppLocation} from './app-router';
import {appRoute} from './app-router';
import {SignInContent} from './signin-content';

import {HeaderSupportControls} from './header-support-controls';
import {PlatformHeader as ShellHeader} from './platform-header';
import {NavigationGuard} from './navigation-guard';
/// <reference types="vite/client" />
import {Sparkle} from '@phosphor-icons/react';
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
 Button,Icon,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter,Popover,PopoverTrigger,ShellPanelContent,ShellIconGroup,ShellIconButton,ShellThemeToggle,ThemeProvider,TooltipProvider,useTheme,
} from '@vxture/design-system';
import {CoSpaceBrand} from './product-brand';
import {ProductLauncher} from './product-launcher';
import {recordLink,moduleLink,useRecordNavigation} from './record-navigation';
import {ConstructionFlow} from './construction-flow';
import {InputDirectory} from './input-directory';
import {SharedDataCatalog} from './shared-data-catalog';
import {SharedOntology} from './shared-ontology';
import {ModuleWorkspace} from './module-workspace';
import {OntologyWorkbench} from './ontology-workbench';
import {SpatialAssociations} from './spatial-associations';
import {moduleNames} from './product-navigation';
import {HomeLayout} from './home-layout';
import {AuthBoundary,usePlatformSession,platformLogout} from './platform-auth';
import { PreviewPublications } from './preview-publications';
import './globals.css';
import './home-panorama.css';
import './public-entry.css';

const BuildScan=React.lazy(()=>import('./build-scan').then(module=>({default:module.BuildScan})));
const RealSpace=React.lazy(()=>import('./real-space').then(module=>({default:module.RealSpace})));
const GlobeEmbed=React.lazy(()=>import('./globe-embed').then(module=>({default:module.GlobeEmbed})));

const names = {...moduleNames,services:'空间服务',settings:'工作区与授权',members:'工作区与授权',identity:'账户与登录',account:'账户与登录'};
type Route = keyof typeof names;
const adminRoutes:Route[] = ['settings','members','identity','account'];
const defaults = {workspace:'内部工程空间'};
function currentRoute():Route {const key=appRoute();return Object.hasOwn(names,key)?key as Route:'space';}
function LoginPage({identity,tools,login,enter}:{identity:React.ReactNode;tools:React.ReactNode;login:()=>void;enter:()=>void}){
 return <HomeLayout tools={tools} footerTools={<Button variant="link" id="enter-preview" onClick={enter}>预览界面<Icon name="arrow-right"/></Button>}>
  <SignInContent onLogin={login}/>
 </HomeLayout>;
}

function App(){
 const platform=usePlatformSession();
 // Header links must refresh even when only the scene changes on the same route.
 const navigation=useRecordNavigation();
 const route=currentRoute();
 const [preview,setPreview]=useState(()=>Boolean(platform)||sessionStorage.getItem('cospace.ui.ds.preview')==='1' || (new URLSearchParams(location.search).get('screen')==='space' && new URLSearchParams(location.search).get('preview')==='1'));
 const config=defaults;
 const [launcher,setLauncher]=useState(false);
 const [modal,setModal]=useState<{title:string;body:string}|null>(null);
 const [notice,setNotice]=useState('');
 const [buildAssistantOpen,setBuildAssistantOpen]=useState(false);
 useEffect(()=>{const sync=(event:Event)=>setBuildAssistantOpen(Boolean((event as CustomEvent).detail));window.addEventListener('cospace-build-assistant-state',sync);window.addEventListener('cospace-publication-assistant-state',sync);window.addEventListener('cospace-association-assistant-state',sync);return()=>{window.removeEventListener('cospace-build-assistant-state',sync);window.removeEventListener('cospace-publication-assistant-state',sync);window.removeEventListener('cospace-association-assistant-state',sync);};},[]);
 const {theme,setTheme}=useTheme();
 useEffect(()=>{const fn=()=>{setLauncher(false);};return subscribeAppLocation(fn);},[]);
 useEffect(()=>{let title='登录';if(preview)title=route==='space'&&new URLSearchParams(location.search).get('screen')!=='space'?'我的场景':names[route];document.title=`CoSpace · ${title}`;},[route,preview,navigation.space]);
 useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),3500);return()=>clearTimeout(t);},[notice]);
 const enter=()=>{sessionStorage.setItem('cospace.ui.ds.preview','1');setPreview(true);};
 const exit=()=>{if(platform?.csrf){return platformLogout(platform.csrf);}sessionStorage.removeItem('cospace.ui.ds.preview');setPreview(false);};
 const full=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{setNotice('当前浏览器未允许全屏。');}};
 const identity=<CoSpaceBrand href="/space"/>;
 const launcherControl=<Popover open={launcher} onOpenChange={v=>{setLauncher(v);}}><PopoverTrigger asChild><ShellIconButton className="launcher-control" icon="app-grid" label="功能 Launcher" active={launcher}/></PopoverTrigger><ShellPanelContent align="start" sideOffset={12} className="product-launcher-panel"><ProductLauncher route={route} hasScene={!!new URLSearchParams(location.search).get('space')} hrefForRoute={target=>moduleLink(target,navigation.space)} onNavigate={()=>setLauncher(false)}/></ShellPanelContent></Popover>;
 const header=<ShellHeader height="md" leading={<>{launcherControl}{identity}<HeaderContext/></>} trailing={<div className="platform-header-actions"><ShellIconGroup label="全局工具">{(route==='build'||route==='delivery'||route==='association')&&<Button variant={buildAssistantOpen?'secondary':'ghost'} size="icon-sm" aria-label={route==='delivery'?'发布智能助手':route==='association'?'关联助手':'构建智能助手'} title={route==='delivery'?'发布智能助手':route==='association'?'关联助手':'构建智能助手'} disabled={!navigation.space} aria-expanded={buildAssistantOpen} onClick={()=>window.dispatchEvent(new Event(route==='delivery'?'cospace-publication-assistant-toggle':route==='association'?'cospace-association-assistant-toggle':'cospace-build-assistant-toggle'))}><Sparkle size={16}/></Button>}<ShellThemeToggle currentTheme={theme} onThemeChange={setTheme} buttonLabel="切换主题"/><HeaderSupportControls/><a href={managementHref('settings',navigation.space)} target="_blank" rel="noopener noreferrer" aria-label="配置与管理" title="配置与管理（新标签页）"><Gear size={16}/></a></ShellIconGroup><ShellIconGroup label="账户"><ProductUserMenu onLogout={exit}/></ShellIconGroup></div>}/>;
 if(preview&&route==='build'&&new URLSearchParams(location.search).get('screen')==='build')return <React.Suspense fallback={<main className="dark h-dvh bg-background text-foreground" role="status">正在打开构建画布…</main>}><BuildScan/></React.Suspense>;
 if(preview&&route==='space'&&new URLSearchParams(location.search).get('embed')==='globe')return <React.Suspense fallback={<main role="status">正在打开三维地球…</main>}><GlobeEmbed/></React.Suspense>;
 const showLoginInfo=()=>setModal({title:'平台登录 · 独立接入验证',body:'已按 yucer 接通 OIDC + PKCE、中央会话与全局登出的独立验证入口。当前工程服务保持 UI 预览，尚未配置 CoSpace 平台客户端和业务空间授权。'});
 const renderWorkspace=()=>{
  if(route==='space'){
   if(new URLSearchParams(location.search).get('screen')==='space'){
    return <React.Suspense fallback={<output className="dark flex flex-1 items-center justify-center bg-background text-foreground text-body-small">正在打开空间…</output>}><RealSpace full={full} workspace={config.workspace}/></React.Suspense>;
   }
   return <SceneCatalog/>;
  }
  if(route==='services')return <SpatialServices/>;
  if(route==='data'){
   const catalog=navigation.tab==='info'||!navigation.space||new URLSearchParams(location.search).get('scope')==='all'||![navigation.tab,navigation.input,navigation.artifact,navigation.batch,navigation.job,navigation.publication].some(Boolean);
   return <main className="data-route-shell min-h-0 flex-1 overflow-hidden">{catalog?<SharedDataCatalog/>:<InputDirectory/>}</main>;
  }
  if(route==='ontology')return <SharedOntology/>;
  if(adminRoutes.includes(route))return <ManagementFrame route={route as 'settings'|'members'|'identity'|'account'}><ManagementWorkspace route={route} onLogout={exit}/></ManagementFrame>;
  return <ModuleWorkspace route={route as keyof typeof moduleNames}><Business route={route as 'data'|'ontology'|'build'|'delivery'|'association'}/></ModuleWorkspace>;
 };
 return <>
 {!preview?<LoginPage identity={identity} tools={<ShellThemeToggle currentTheme={theme} onThemeChange={setTheme} buttonLabel="切换主题"/>} login={showLoginInfo} enter={enter}/> :
 <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground" id="workbench-shell">{route==='space'&&new URLSearchParams(location.search).get('screen')==='space'?null:header}{renderWorkspace()}</div>}
 <Dialog open={Boolean(modal)} onOpenChange={v=>{if(!v)setModal(null);}}><DialogContent><DialogHeader><DialogTitle>{modal?.title}</DialogTitle><DialogDescription>{modal?.body}</DialogDescription></DialogHeader><DialogFooter><Button onClick={()=>setModal(null)}>知道了</Button></DialogFooter></DialogContent></Dialog>

 {notice&&<div role="status" className="fixed bottom-lg left-lg z-notification rounded-md border border-border bg-popover px-lg py-md text-body-small text-popover-foreground shadow-notification">{notice}</div>}
 </>;
}

function Business({route}:Readonly<{route:'data'|'ontology'|'build'|'delivery'|'association'}>){
 const context=useRecordNavigation();
 if(route==='data')return <InputDirectory key={context.space}/>;
 if(route==='ontology')return <OntologyWorkbench/>;
 if(route==='association')return <SpatialAssociations key={context.space}/>;
 if(route==='delivery')return <PreviewPublications key={`publications-${context.space}`}/>;
 return <BuildWorkspaceViews key={context.space}/>;
}
function BuildWorkspaceViews(){return <ConstructionFlow/>;}
function RoutedApplication(){return <ThemeProvider defaultMode="light"><TooltipProvider><AuthBoundary><SceneSelection><App/></SceneSelection></AuthBoundary><NavigationGuard/></TooltipProvider></ThemeProvider>;}
// A persistent parent route owns authentication and product context. Child route
// changes must never remount the session boundary or re-bootstrap authentication.
const router=createBrowserRouter([{element:<RoutedApplication/>,children:['/',...Object.keys(names).map(name=>'/'+name)].map(path=>({path,element:null}))}]);
bindAppRouter(router);
createRoot(document.getElementById('root')!).render(<ToastProvider><RouterProvider router={router}/></ToastProvider>);
