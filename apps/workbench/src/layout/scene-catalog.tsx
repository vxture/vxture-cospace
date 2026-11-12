import {preloadGlobe} from './globe-loader';
import {readMapPreferences} from './map-preferences';
import {locationLabel} from './geographic-location';
import React,{useEffect,useMemo,useState} from 'react';
import {Button,Input,NativeSelect,ViewHeader,SegmentedControl} from '@vxture/design-system';
import {MapTrifold,MagnifyingGlass,MapPin,ArrowRight,Cube,ArrowsClockwise,List,SquaresFour} from '@phosphor-icons/react';
import {useSceneDirectory} from './use-scene-directory';
import {SceneCover} from './scene-cover';
import {CreateSceneButton} from './create-scene';
import {scenePhases,scenePhase,filterScenes,sceneWorkspaceHref,sceneEntryHref,currentRelease,publicationLabel} from './scene-catalog-contract';
import {SceneDetail,SceneMoreMenu} from './scene-detail';
import {useLocation} from 'react-router-dom';
import {appNavigate} from './app-router';
import './scene-catalog.css';
const SceneMap=React.lazy(()=>import('./scene-map-view').then(m=>({default:m.SceneMap})));

export function SceneCatalog(){
 const [revision,setRevision]=useState(0),[query,setQuery]=useState(''),[phase,setPhase]=useState('all'),[sort,setSort]=useState('phase'),[layout,setLayout]=useState<'cards'|'list'>('cards'),[selected,setSelected]=useState(''),[mode,setMode]=useState<'catalog'|'map'>('catalog');
 const location=useLocation();
 useEffect(()=>{setSelected(new URLSearchParams(location.search).get('space')||'');},[location.search]);
 const showDetails=(id:string)=>appNavigate(id?sceneWorkspaceHref(id):'/space');
 const {spaces,loading,error}=useSceneDirectory(revision);
 const visible=useMemo(()=>filterScenes(spaces,query,phase,sort),[spaces,query,phase,sort]);
 const detail=spaces.find(s=>s.id===selected);
 const reset=()=>{setQuery('');setPhase('all');};
 if(mode==='map')return <React.Suspense fallback={<div role="status">正在打开地图…</div>}><SceneMap spaces={spaces} loading={loading} error={error} onBack={()=>setMode('catalog')} onRefresh={()=>setRevision(v=>v+1)}/></React.Suspense>;
 return <main className="scene-catalog" aria-label="场景选择"><div className="scene-catalog-shell">
  <ViewHeader title="我的场景" secondary={<span className="scene-total" aria-label="场景总数">{spaces.length}</span>} description="从场景开始，连接资料、模型与空间服务。" action={<div className="scene-catalog-heading-actions"><CreateSceneButton size="xl" onCreated={id=>appNavigate('/data?'+new URLSearchParams({space:id,tab:'inputs'}))}/><Button size="xl" variant="default" onPointerEnter={()=>{if(readMapPreferences().viewMode==='3D')preloadGlobe();}} onFocus={()=>{if(readMapPreferences().viewMode==='3D')preloadGlobe();}} onClick={()=>{showDetails('');setSelected('');setMode('map');}}><MapTrifold size={16}/>地图模式</Button></div>}/>
  <div className="scene-catalog-toolbar" aria-label="场景清单操作区">
   <SegmentedControl value={layout} onChange={setLayout} size="md" className="h-control-xl p-2xs" ariaLabel="清单布局" items={[{value:"list",label:<List size={20}/>,ariaLabel:"列表布局"},{value:"cards",label:<SquaresFour size={20}/>,ariaLabel:"卡片布局"}]}/>
   <span className="scene-result-count" aria-live="polite">筛选 <strong>{visible.length}</strong> 项</span>
   <div className="scene-catalog-filters"><div className="scene-catalog-search"><MagnifyingGlass size={16}/><Input aria-label="搜索场景" placeholder="搜索场景、项目或位置" value={query} onChange={e=>setQuery(e.target.value)}/></div><NativeSelect wrapperClassName="scene-catalog-select" aria-label="场景状态" value={phase} onChange={e=>setPhase(e.target.value)}><option value="all">全部状态</option>{Object.entries(scenePhases).map(([key,value])=><option key={key} value={key}>{value.label}</option>)}</NativeSelect><NativeSelect wrapperClassName="scene-catalog-select" aria-label="场景排序" value={sort} onChange={e=>setSort(e.target.value)}><option value="phase">按进展阶段</option><option value="name">按名称排序</option><option value="time">按时间排序</option></NativeSelect><Button size="icon-xl" variant="outline" aria-label="刷新场景目录" onClick={()=>setRevision(v=>v+1)}><ArrowsClockwise size={16}/></Button></div>
  </div>
  {!loading&&!error&&selected&&!detail&&<div className="scene-catalog-empty" role="alert"><p>所选场景无权访问或不存在，请重新选择。</p><Button variant="secondary" onClick={()=>showDetails('')}>返回场景目录</Button></div>}
  {loading?<div className="scene-catalog-empty" role="status">正在读取场景…</div>:error?<div className="scene-catalog-empty" role="alert"><Cube size={28}/><p>{error}</p><Button size="sm" variant="secondary" onClick={()=>setRevision(v=>v+1)}>重新加载</Button></div>:<div className={'scene-catalog-items scene-catalog-'+layout}>
   {visible.map(scene=>{const state=scenePhases[scenePhase(scene)],release=currentRelease(scene);return <article className="catalog-card" key={scene.id} data-tone={state.tone} aria-label={scene.name}>
    <div className="catalog-card-visual"><header className="catalog-card-heading"><h2><a href={sceneWorkspaceHref(scene.id)}>{scene.name}{scene.project_name&&<span> · {scene.project_name}</span>}</a></h2><span className="catalog-card-status">{state.label}</span></header><button className="catalog-card-cover" aria-label={'查看'+scene.name+'详情'} onClick={()=>showDetails(scene.id)}><SceneCover name={scene.name} overviewUrl={scene.overview_url}/></button></div>
    <div className="catalog-card-body"><p className="catalog-card-description">{scene.description||'暂无场景描述'}</p><div className="catalog-card-footer"><p className="catalog-card-address" title={scene.address||locationLabel(scene.location)}><MapPin size={14}/><span>{scene.address||locationLabel(scene.location)}</span></p>{release&&<div className="catalog-card-release" title={'发布版本 '+release.id}><span>{publicationLabel(release)}</span><time dateTime={release.created_at}>{release.created_at.slice(0,10)}</time></div>}<div className="catalog-card-actions"><SceneMoreMenu scene={scene} onDetails={()=>showDetails(scene.id)}/><Button asChild size="xl" variant={state.tone==='neutral'?'secondary':'default'}><a href={sceneEntryHref(scene)} {...(release?{target:'_blank',rel:'noopener noreferrer'}:{})}>进入场景<ArrowRight size={14}/></a></Button></div></div></div>
   </article>;})}
   {!visible.length&&<div className="scene-catalog-empty" role="status"><MagnifyingGlass size={28}/><h2>{spaces.length?'没有匹配的场景':'暂无可访问的场景'}</h2><p>{spaces.length?'调整搜索关键词或状态后重试。':'可创建新场景，或联系管理员分配场景权限。'}</p>{spaces.length>0&&<Button size="sm" variant="secondary" onClick={reset}>清除筛选</Button>}</div>}
  </div>}
 </div><SceneDetail scene={detail} onClose={()=>showDetails('')}/></main>;
}
