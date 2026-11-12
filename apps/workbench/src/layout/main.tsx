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
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
 Collapsible,CollapsibleTrigger,CollapsibleContent,Button,Icon,Input,StatusBadge,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter,Popover,PopoverTrigger,ShellPanelContent,ShellPanelSection,ShellPanelRow,ShellIconGroup,ShellIconButton,ShellUserMenu,ShellThemeToggle,Card,CardHeader,CardTitle,CardDescription,CardContent,Tabs,TabsList,TabsTrigger,Switch,Separator,ThemeProvider,Tooltip,TooltipTrigger,TooltipContent,TooltipProvider,useTheme,
} from '@vxture/design-system';
import {CoSpaceBrand} from './product-brand';
import {ProductLauncher} from './product-launcher';
import { spaces } from './spaces';
import spaceSvg from './space.svg?raw';
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
const defaults = {workspace:'内部工程空间',scene:'设备间与相连走廊'};
type Config = typeof defaults;
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
 const [route,setRoute]=useState<Route>(currentRoute);
 const [preview,setPreview]=useState(()=>Boolean(platform)||sessionStorage.getItem('cospace.ui.ds.preview')==='1' || (new URLSearchParams(location.search).get('screen')==='space' && new URLSearchParams(location.search).get('preview')==='1'));
 const config=defaults;
 const [launcher,setLauncher]=useState(false);
 const [modal,setModal]=useState<{title:string;body:string}|null>(null);
 const [notice,setNotice]=useState('');
 const [buildAssistantOpen,setBuildAssistantOpen]=useState(false);
 useEffect(()=>{const sync=(event:Event)=>setBuildAssistantOpen(Boolean((event as CustomEvent).detail));window.addEventListener('cospace-build-assistant-state',sync);window.addEventListener('cospace-publication-assistant-state',sync);window.addEventListener('cospace-association-assistant-state',sync);return()=>{window.removeEventListener('cospace-build-assistant-state',sync);window.removeEventListener('cospace-publication-assistant-state',sync);window.removeEventListener('cospace-association-assistant-state',sync);};},[]);
 const {theme,setTheme}=useTheme();
 useEffect(()=>{const fn=()=>{setRoute(currentRoute());setLauncher(false);};return subscribeAppLocation(fn);},[]);
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
    if(new URLSearchParams(location.search).has('publication')||!spaces.some(s=>s.id===new URLSearchParams(location.search).get('space')))return <React.Suspense fallback={<output className="dark flex flex-1 items-center justify-center bg-background text-foreground text-body-small">正在打开空间…</output>}><RealSpace full={full} workspace={config.workspace}/></React.Suspense>;
    return <Space config={config} full={full}/>;
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
function RailHandle({side,open,toggle}:{side:'left'|'right';open:boolean;toggle:()=>void}){return <Button variant="ghost" className={`rail-handle rail-handle-${side}`} data-open={open} aria-label={side==='left'?'展开或收起左侧信息栏':'空间概览'} aria-expanded={open} title={open?'收起信息栏':'展开信息栏'} onClick={toggle}><img src="/assets/fold-bracket.png" alt="" aria-hidden="true" className="rail-handle-art"/></Button>;}
function Space({config,full}:{config:Config;full:()=>void}){
 const [spaceId,setSpaceId]=useState(()=>new URLSearchParams(location.search).get('space')||'equipment');
 const scene=spaces.find(s=>s.id===spaceId)||spaces[0];
 const [objects,setObjects]=useState(false),[properties,setProperties]=useState(false);
 const [selected,setSelected]=useState(0),[search,setSearch]=useState(''),[view,setView]=useState('human'),[tab,setTab]=useState('attributes');
 const [deviceBlock,setDeviceBlock]=useState(true);
 const [overview,setOverview]=useState(false);
 const [anchor,setAnchor]=useState({left:0,top:0});
 const detail=useRef<HTMLDivElement>(null);
 const [switcher,setSwitcher]=useState(false),[isFull,setIsFull]=useState(Boolean(document.fullscreenElement));
 const initialLayers={geometry:true,labels:true,unknown:true,grid:false};
 const [layers,setLayers]=useState<Record<string,boolean>>(initialLayers);
 const holder=useRef<HTMLDivElement>(null);
 function switchSpace(id:string){setSpaceId(id);setSelected(0);setSearch('');setProperties(false);setOverview(false);setLayers(initialLayers);setView('human');setTab('attributes');setSwitcher(false);const url=new URL(location.href);url.searchParams.set('space',id);history.replaceState(null,'',url);}
 useEffect(()=>{document.title=`${scene.name} · 空间态势`;if(!holder.current)return;const svg=holder.current;svg.querySelectorAll('[data-object]').forEach(el=>{const i=Number(el.getAttribute('data-object'));el.classList.toggle('selected',i===selected);el.setAttribute('tabindex','0');el.setAttribute('role','button');el.setAttribute('aria-label',scene.objects[i]);el.setAttribute('transform',scene.variant===1?`translate(${i===1?25:-15} ${i===2?-25:8})`:scene.variant===2?`translate(${i*10} -15)`:'');});svg.querySelectorAll('#labels text').forEach((el,i)=>{if(i<3){el.textContent=scene.objects[i];el.setAttribute('visibility',properties&&i===selected?'hidden':'visible');}});Object.entries(layers).forEach(([key,on])=>{const el=svg.querySelector<SVGElement>(`#${key}`);if(el)el.style.display=on?'':'none';});const overlay=svg.querySelector<SVGElement>('#agent-overlay');if(overlay)overlay.style.display=view==='agent'?'':'none';},[selected,layers,view,scene,properties]);
 useEffect(()=>{const sync=()=>setIsFull(Boolean(document.fullscreenElement));document.addEventListener('fullscreenchange',sync);return()=>{document.removeEventListener('fullscreenchange',sync);};},[]);
 useEffect(()=>{const node=holder.current;if(!node)return;const sync=()=>{const bounds=node.getBoundingClientRect();const scale=Math.min(bounds.width/645,bounds.height/465);const size=parseFloat(getComputedStyle(node).fontSize)/scale;node.querySelectorAll<SVGTextElement>('text').forEach(el=>{el.style.fontSize=`${size}px`;});};const observer=new ResizeObserver(sync);observer.observe(node);sync();return()=>observer.disconnect();},[]);
 useEffect(()=>{if(!properties||!holder.current||!detail.current)return;const place=()=>{const node=holder.current;const panel=detail.current;if(!node||!panel)return;const item=node.querySelector(`[data-object="${selected}"]`);if(!item)return;const r=item.getBoundingClientRect(),base=node.getBoundingClientRect(),pr=panel.getBoundingClientRect();const gap=parseFloat(getComputedStyle(panel).paddingTop)||16;let left=r.right-base.left+gap;if(left+pr.width>base.width-gap)left=r.left-base.left-pr.width-gap;left=Math.max(gap,Math.min(left,base.width-pr.width-gap));const top=Math.max(gap,Math.min(r.top-base.top,base.height-pr.height-gap));setAnchor(old=>old.left===left&&old.top===top?old:{left,top});};const observer=new ResizeObserver(place);observer.observe(holder.current);observer.observe(detail.current);place();return()=>observer.disconnect();},[properties,selected,scene,tab]);
 const select=(target:EventTarget)=>{if(target instanceof Element){const item=target.closest('[data-object]');if(item){setSelected(Number(item.getAttribute('data-object')));setProperties(true);}}};
 return <section id="spatial" className="dark relative isolate min-h-0 flex-1 overflow-hidden bg-background text-foreground" aria-label="空间态势大屏">
  <div className="absolute inset-0 spatial-canvas text-label-small font-normal" ref={holder} onClick={e=>select(e.target)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(e.target);}}} dangerouslySetInnerHTML={{__html:spaceSvg}}/>
  <>
   <div className="space-picker absolute left-lg top-lg z-30 flex max-w-full flex-col gap-xs">
    <Popover open={switcher} onOpenChange={setSwitcher}><PopoverTrigger asChild><Button size="sm" variant="secondary" className="space-title-control max-w-full gap-sm font-normal" aria-label="切换空间"><Icon name="cube" size="sm"/><span className="truncate">{scene.id==='equipment'?config.scene:scene.name}</span><Icon name="chevron-down" size="xs"/></Button></PopoverTrigger><ShellPanelContent align="start" className="dark"><ShellPanelSection title="空间预览 · 设计示例">{spaces.map(s=><ShellPanelRow key={s.id} icon="cube" label={s.name} description={`${s.level} · ${s.version}`} active={s.id===scene.id} onClick={()=>switchSpace(s.id)}/>)}</ShellPanelSection></ShellPanelContent></Popover>
   </div>
   <div className="space-tools absolute right-lg top-lg z-30 flex items-center gap-md" role="toolbar" aria-label="空间显示工具">
    <div className="space-action-group flex items-center gap-2xs" role="group" aria-label="空间操作"><Button variant="ghost" size="sm" className="space-icon-control" aria-label={isFull?'退出全屏':'全屏'} title={isFull?'退出全屏':'全屏'} onClick={full}><Icon name={isFull?'corners-in':'corners-out'} size="sm"/></Button>
    <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="sm" className="space-icon-control" aria-label={view==='human'?'当前人视图，切换到机视图':'当前机视图，切换到人视图'} onClick={()=>setView(view==='human'?'agent':'human')}><Icon name={view==='human'?'cube':'cpu'} size="sm"/></Button></TooltipTrigger><TooltipContent className="dark" side="bottom">{view==='human'?'人视图 · 点击切换机视图':'机视图 · 点击切换人视图'}</TooltipContent></Tooltip></div>
    <ShellUserMenu triggerClassName="space-avatar-control" openLabel="用户账户" online={false} contentClassName="dark" user={{displayName:'交付工程师',avatarFallback:'工',uniqueLine:'设计预览身份 · 非真实登录',meta:config.workspace}} actions={[{key:'spaces',label:'我的场景',icon:'cube',onClick:()=>{window.open('/space','_blank','noopener,noreferrer');}},{key:'account',label:'账户与登录',icon:'user',onClick:()=>{window.open('/account','_blank','noopener,noreferrer');}}]}/>
   </div>
   <div className="space-rail space-rail-left flex flex-col gap-lg overflow-auto" data-open={objects} inert={!objects}>
    <Collapsible open={deviceBlock} onOpenChange={setDeviceBlock} asChild><section className="space-block shrink-0 overflow-hidden rounded-lg border border-border bg-card text-card-foreground" aria-label="设备对象板块">
     <h2><CollapsibleTrigger asChild><Button variant="ghost" className="space-block-title w-full justify-between rounded-none px-lg font-medium" aria-label="设备对象"><span className="flex items-center gap-sm"><Icon name="cube" size="sm"/>设备对象</span><Icon name={deviceBlock?'chevron-up':'chevron-down'} size="xs" className="text-muted-foreground"/></Button></CollapsibleTrigger></h2>
     <CollapsibleContent><div className="space-block-content flex flex-col gap-md px-lg pb-lg"><p className="text-label-small font-normal text-muted-foreground">{scene.name}<br/>{scene.level} · {scene.version} · 示例空间</p><Input className="space-block-search" aria-label="搜索空间对象" placeholder="搜索空间对象" value={search} onChange={e=>setSearch(e.target.value)}/><div className="flex flex-col gap-xs">{scene.objects.map((name,i)=>name.includes(search)&&<Button key={name} size="sm" variant={i===selected?'secondary':'ghost'} className="space-object-row justify-start gap-sm px-sm font-normal" onClick={()=>{setSelected(i);setProperties(true);}}><Icon name="cube" size="sm" className="text-muted-foreground"/>{name}</Button>)}</div></div></CollapsibleContent>
    </section></Collapsible>
   </div>
   <div className="space-rail space-rail-right" data-open={overview} inert={!overview}><Card className="h-full overflow-auto"><CardHeader className="p-lg"><CardTitle className="text-label-small font-medium">空间概览</CardTitle></CardHeader><CardContent className="flex flex-col gap-lg px-lg pb-lg text-body-small"><p>{scene.name}</p><Separator/><div className="flex justify-between"><span className="text-muted-foreground">对象</span><span>{scene.objects.length}</span></div><div className="flex justify-between"><span className="text-muted-foreground">视图</span><span>{view==='human'?'人视图':'机视图'}</span></div><div className="flex justify-between"><span className="text-muted-foreground">质量</span><span>未验证</span></div><p className="text-muted-foreground">合成示例，未接入现场数据。</p></CardContent></Card></div>
   <RailHandle side="left" open={objects} toggle={()=>setObjects(!objects)}/><RailHandle side="right" open={overview} toggle={()=>setOverview(!overview)}/>
   {properties&&<Card ref={detail} style={{left:anchor.left,top:anchor.top}} className="device-detail gap-md py-md absolute z-20 w-overlay-lg max-w-full overflow-auto bg-popover" aria-label="对象属性"><CardHeader className="p-lg"><div className="flex justify-between gap-sm"><CardTitle className="text-label-small font-medium">{scene.objects[selected]}</CardTitle><Button size="sm" variant="ghost" onClick={()=>setProperties(false)} aria-label="关闭属性面板"><Icon name="x" size="xs"/></Button></div><CardDescription className="text-label-small">{scene.id.toUpperCase()} · {String(selected+1).padStart(2,'0')}</CardDescription></CardHeader><CardContent className="flex flex-col gap-lg px-lg pb-lg"><Tabs value={tab} onValueChange={setTab}><TabsList><TabsTrigger className="font-normal" value="attributes">属性</TabsTrigger><TabsTrigger className="font-normal" value="evidence">来源与证据</TabsTrigger></TabsList></Tabs>{tab==='attributes'?<><div className="flex flex-col gap-sm text-body-small"><p className="text-muted-foreground">对象类型</p><p>{scene.types}</p><p className="text-muted-foreground">所属空间</p><p>{scene.name} · {scene.level}</p></div><StatusBadge size="sm" tone="warning">现场质量未验证</StatusBadge><p className="text-body-small text-muted-foreground">示例对象，不用于量测、定位或导航。</p></>:<p className="text-body-small text-muted-foreground">界面设计示意，原始资料与质量证据待接入。</p>}</CardContent></Card>}
   <div className="pointer-events-none absolute bottom-md right-lg left-lg z-30 flex flex-wrap items-end justify-between gap-md">
    <div role="group" aria-label="显示图层" className="space-layer-controls pointer-events-auto flex flex-wrap gap-x-md gap-y-sm">{Object.entries({geometry:'空间几何',labels:'对象标注',unknown:'未知区域',grid:'坐标网格'}).map(([key,label])=><label htmlFor={`layer-${key}`} key={key} className="flex cursor-pointer items-center gap-xs text-body-small font-normal"><span>{{geometry:'几何',labels:'标注',unknown:'未知',grid:'网格'}[key]}</span><Switch aria-label={label} className="space-layer-switch" id={`layer-${key}`} checked={layers[key]} onCheckedChange={on=>setLayers({...layers,[key]:on})}/></label>)}</div>
    <div className="ml-auto flex flex-wrap justify-end gap-x-md gap-y-xs text-label-small font-normal text-muted-foreground"><span>CoSpace</span><span>{view==='human'?'人视图':'机视图 · 裁剪示意'}</span><span className="hidden sm:inline">合成示意 · 非实测成果</span></div>
   </div>
  </>

 </section>;
}
function RoutedApplication(){return <ThemeProvider defaultMode="light"><TooltipProvider><AuthBoundary><SceneSelection><App/></SceneSelection></AuthBoundary><NavigationGuard/></TooltipProvider></ThemeProvider>;}
// A persistent parent route owns authentication and product context. Child route
// changes must never remount the session boundary or re-bootstrap authentication.
const router=createBrowserRouter([{element:<RoutedApplication/>,children:['/',...Object.keys(names).map(name=>'/'+name)].map(path=>({path,element:null}))}]);
bindAppRouter(router);
createRoot(document.getElementById('root')!).render(<ToastProvider><RouterProvider router={router}/></ToastProvider>);
