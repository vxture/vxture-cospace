import React,{createContext,useContext,useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {SidebarSimple,CaretRight,ArrowClockwise,ArrowUpRight,Cube} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {businessEndpoint as endpoint} from './business-endpoint';
import {moduleNames,moduleGroups} from './product-navigation';
import {recordLink,useRecordNavigation,RecordNavigationProvider} from './record-navigation';
import {SceneDirectory,SceneSpace} from './scene-directory';
import {realScreenHref} from './real-space-data';
import {SceneCapabilities} from './scene-capabilities';
import {SceneProgress} from './scene-progress';
import spaceArt from './space.svg?raw';
import './data-workspace.css';
import './module-workspace.css';

type ModuleRoute=keyof typeof moduleNames;
const EmbeddedScene=createContext(false);
export function useEmbeddedScene(){return useContext(EmbeddedScene);}
const descriptions:Record<ModuleRoute,string>={space:'浏览当前场景空间的固定发布，打开完整三维场景。',delivery:'管理当前场景的发布版本、在线服务与离线交付。',data:'按场景空间管理资料、历史版本与发布成果。',build:'从当前场景的资料生成模型候选，核对后选择版本。',ontology:'管理共用的类型、属性与关系规则；场景实例在空间关联中维护。',association:'将固定本体版本应用到当前场景，维护对象、几何与业务关联。'};
const required:Partial<Record<ModuleRoute,string>>={data:'data.manage',build:'build.run',association:'association.edit'};

export function ModuleWorkspace({route,children}:{route:ModuleRoute;children:React.ReactNode}){
 const platform=usePlatformSession(),target=useRecordNavigation();
 const [spaces,setSpaces]=useState<SceneSpace[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [matched,setMatched]=useState<{space:string;ids:string[]}>({space:'',ids:[]});
 const [search,setSearch]=useState(''),[sidebar,setSidebar]=useState(()=>innerWidth>620);
 useEffect(()=>{const controller=new AbortController();setSpaces([]);setLoading(true);setError('');
  fetch(`${endpoint}/api/spaces`,{cache:'no-store',signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('场景空间目录暂不可用，请重试。');const value=await r.json();if(!Array.isArray(value.spaces))throw Error('场景空间目录格式无效。');if(!controller.signal.aborted)setSpaces(value.spaces);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[platform?.user?.workspace_id,revision]);
 useEffect(()=>{if(!target.space&&spaces.length&&route!=='ontology')location.replace(recordLink(route,{space:spaces[0].id}));},[target.space,spaces,route]);
 useEffect(()=>{const media=matchMedia('(max-width:620px)');const update=()=>{if(media.matches)setSidebar(false);};media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
 const scene=spaces.find(s=>s.id===target.space),group=moduleGroups.find(g=>g.items.some(i=>i.route===route));
 const cap=required[route],allowed=!!scene&&(!platform||!cap||!!scene.capabilities?.includes(cap));
 const common=route==='ontology';
 return <main className="data-route-shell min-h-0 flex-1 overflow-hidden"><div className={`data-workspace module-workspace ${sidebar?'':'data-sidebar-hidden'}`}>
  <SceneDirectory spaces={spaces} current={target.space} workspace={platform?.user?.workspace_id||'本机工程预览'} search={search} onSearch={setSearch} onChoose={id=>{location.hash=recordLink(route,{space:id});if(innerWidth<=620)setSidebar(false);}} loading={loading} error={error} library={common}/>
  <section className="data-main" aria-label={`${moduleNames[route]}工作区`}>
   <header className="data-heading"><div className="data-heading-copy"><div className="data-breadcrumb"><Button variant="outline" size="sm" className="data-icon-button data-sidebar-toggle" aria-label={sidebar?'收起场景目录':'展开场景目录'} aria-expanded={sidebar} aria-controls="data-scene-sidebar" onClick={()=>setSidebar(v=>!v)}><SidebarSimple size={16}/></Button><span>{group?.title}</span><CaretRight size={12}/><span>{moduleNames[route]}</span><CaretRight size={12}/><span className="data-breadcrumb-scene">{common?'共用规则库':scene?.name||'选择场景空间'}</span></div><h1>{moduleNames[route]}</h1><p>{descriptions[route]}</p></div><div className="data-heading-actions"><Button variant="outline" size="sm" className="data-icon-button" aria-label="刷新场景空间目录" onClick={()=>setRevision(v=>v+1)} disabled={loading}><ArrowClockwise size={16}/></Button><Button asChild size="sm" variant="outline"><a href={recordLink('settings',{})}>场景配置</a></Button></div></header>
   <SceneModuleNavigation route={route} scene={scene}/>
   <div className="module-body">
    {common&&<p className="module-scope-note">规则库为共用定义，不属于某个模型版本。{scene?`当前关联上下文：${scene.name}。`:''}应用到场景时固定本体版本与摘要。</p>}
    {common?<RecordNavigationProvider value={target}><EmbeddedScene.Provider value>{children}</EmbeddedScene.Provider></RecordNavigationProvider>:loading?<p role="status" className="data-subtle">正在读取场景空间…</p>:error?<div role="alert" className="data-empty"><p>{error}</p><Button variant="outline" onClick={()=>setRevision(v=>v+1)}>重试</Button></div>:!scene?<div className="data-empty"><Cube size={36}/><h2>选择场景空间</h2><p>{target.space?'所选场景无权访问或不存在，请重新选择。':'从左侧选择一个场景，查看它的资料、版本和服务。'}</p></div>:!allowed?<div className="data-empty" role="alert"><h2>当前场景无此操作权限</h2><p>可切换有权限的场景空间，或返回空间预览。</p></div>:<RecordNavigationProvider value={target}><EmbeddedScene.Provider value><SceneCapabilities.Provider value={scene.capabilities||[]}><SceneProgress key={[scene.id,target.job,target.publication,target.input].join(':')} space={scene.id} name={scene.name} input={target.input} revision={revision} onRead={report=>setMatched(report?{space:report.space_id,ids:report.summary.publications.filter(p=>p.matches_current).map(p=>p.publication_id)}:{space:'',ids:[]})}/>{route==='space'?<ScenePreview scene={scene} matching={matched.space===scene.id?matched.ids:[]}/>:children}</SceneCapabilities.Provider></EmbeddedScene.Provider></RecordNavigationProvider>}
   </div>
  </section>
 </div></main>;
}

export function SceneModuleNavigation({route,scene}:{route:ModuleRoute;scene?:SceneSpace}){
 const platform=usePlatformSession(),target=useRecordNavigation();
 const context={...(target.input?{input:target.input}:{}),...(target.batch?{batch:target.batch}:{}),...(target.job?{job:target.job}:{}),...(target.publication?{publication:target.publication}:{})};
 return <nav className="module-context-bar" aria-label="当前场景的六模块导航"><span className="module-context-name">{route==='ontology'?'共用规则库':scene?.name||'场景空间'}</span>{(Object.keys(moduleNames) as ModuleRoute[]).map(key=>{const cap=required[key],denied=!!platform&&!!scene&&!!cap&&!scene.capabilities?.includes(cap);return denied?<span key={key} className="module-context-disabled" title="当前场景无此操作权限">{moduleNames[key]}</span>:<a key={key} href={recordLink(key,context)} aria-current={route===key?'page':undefined}>{moduleNames[key]}</a>;})}</nav>;
}

function ScenePreview({scene,matching}:{scene:SceneSpace;matching:string[]}){
 const releases=[...(scene.publications||[])].sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at));
 return <section aria-label="当前场景发布预览" className="module-preview"><div className="module-section-heading"><h2>{scene.name}</h2><span>{releases.length} 个固定发布</span></div>{scene.description&&<p className="module-scope-note">{scene.description}</p>}{!releases.length?<div className="data-empty"><Cube size={40}/><h2>此场景尚无固定发布</h2><p>资料构建并核对后，在态势服务中发布，随后可在这里打开。</p><Button asChild variant="outline"><a href={recordLink('data',{})}>查看场景资料</a></Button></div>:<div className="module-preview-grid">{releases.map(release=>{const active=release.lifecycle_state!=='paused';return <article key={release.id} className="module-preview-card"><div className="module-preview-art"><div className="module-preview-illustration" aria-hidden="true" dangerouslySetInnerHTML={{__html:spaceArt.replace(/id="([^"]+)"/g,`id="${release.id}-$1"`).replace(/url\(#([^)]+)\)/g,`url(#${release.id}-$1)`)}}/><span className="module-preview-caption">空间示意</span></div><div className="module-preview-copy"><div className="module-section-heading"><h3>{scene.name}</h3><span className={active?'module-release-active':''}>{active?'已发布':'已暂停'}</span></div><p className="module-version-id">版本：{release.id}</p><p className="module-scope-note">{matching.includes(release.id)?'对应当前工作候选':'固定发布版本'}</p><div className="module-preview-footer"><time dateTime={release.created_at}>{new Date(release.created_at).toLocaleString('zh-CN',{hour12:false})}</time>{active?<Button asChild size="sm"><a href={realScreenHref(scene.id,release.id)} target="_blank" rel="noopener noreferrer">打开空间<ArrowUpRight size={14}/></a></Button>:<Button disabled size="sm">打开空间</Button>}</div></div></article>;})}</div>}</section>;
}
