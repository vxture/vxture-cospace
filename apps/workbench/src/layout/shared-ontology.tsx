import {Button} from '@vxture/design-system';
import {WorkspaceHeading} from './workspace-frame';
import {Graph} from '@phosphor-icons/react';
import React,{useState,useRef,useLayoutEffect} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {OntologyNavigation,ontologySelectionHref} from './ontology-navigation';
import {OntologyWorkbench} from './ontology-workbench';
import {OntologyAuthoring} from './ontology-authoring';
import type {LibrarySelection} from '@vxture/ontology-ui';
import {OntologyDirectory} from '@vxture/ontology-ui/directory';
import {useUnsavedNavigation} from './unsaved-navigation';
import {ontologyDirectoryClient,ontologyAuthoringClient} from './ontology-library-client';
import {DefinitionWorkspace} from '@vxture/ontology-ui/authoring';
import {businessEndpoint} from './business-endpoint';
import {usePlatformSession} from './platform-auth';

export function SharedOntology(){
 const platform=usePlatformSession();
 return <OntologyWorkspace key={[platform?.user?.subject,platform?.user?.org_id,platform?.user?.workspace_id].join('/')}/>;
}
function OntologyWorkspace(){
 const location=useLocation(),navigate=useNavigate(),params=new URLSearchParams(location.search),tab=params.get('tab');
 const view=tab==='rules'||!tab&&params.has('ontology_id')?'rules':tab==='authoring'?'authoring':tab==='release'?'release':'library';
 const category=['core','domain'].includes(params.get('category')||'')?params.get('category')!:'all';
 const categoryTitle=category==='core'?'通用核心':category==='domain'?'领域本体':'全部本体';
 const kind=params.get('kind'),selection:LibrarySelection={moduleId:params.get('module')||'',...(kind==='concept'||kind==='relation'?{kind,term:params.get('term')||''}:{})};
 const [refresh,setRefresh]=useState(0),[dirty,setDirty]=useState(false);
 useUnsavedNavigation(dirty,'本体编制或归组');
 const content=useRef<HTMLElement>(null);
 useLayoutEffect(()=>{if(content.current)content.current.scrollTop=0;},[category,selection.moduleId,selection.kind,selection.term]);
 return <div className="shared-support-layout ontology-workspace" data-layout="management"><OntologyNavigation view={view} category={category}/><main ref={content} className="shared-data-catalog" aria-label="共用语义本体"><div className="ontology-content-shell">{!(view==='library'&&selection.moduleId)&&<WorkspaceHeading icon={Graph} title={view==='library'?categoryTitle:'语义本体'} description={view==='library'?'通用核心与领域定义，可供产品和场景引用':view==='authoring'?'编辑 · 工作区规则草稿':view==='release'?'发布 · 版本与封存':'查看 · 固定规则版本与校验'} actions={view==='library'&&<Button variant="outline" disabled={dirty} onClick={()=>setRefresh(v=>v+1)}>刷新目录</Button>}/>}
 {view==='library'?<><OntologyDirectory key={category} client={ontologyDirectoryClient} renderDetail={library=><DefinitionWorkspace key={selection.moduleId} client={ontologyAuthoringClient} library={library} selection={selection} onSelect={s=>navigate(ontologySelectionHref(s,category))} onBack={()=>navigate(ontologySelectionHref({moduleId:selection.kind?selection.moduleId:''},category))} onDirtyChange={setDirty}/>} category={category} selection={selection} refresh={refresh} onBack={()=>navigate(ontologySelectionHref({moduleId:selection.kind?selection.moduleId:''},category))} onDirtyChange={setDirty} onSelect={s=>navigate(ontologySelectionHref(s,category))}/></>:view==='rules'?<OntologyWorkbench/>:<>
 <p className="ontology-capability-note">{view==='authoring'?'通用核心与领域模块目前仅支持查看与导出。下方编辑器适用于现有工作区对象规则，模块编制能力待建设。':'通用核心与领域模块尚未开放发布。下方仅封存现有工作区规则的固定版本；审核、发布记录与模块分发待建设。'}</p>
 {view==='authoring'?<OntologyWorkbench mode="edit"/>:<OntologyAuthoring mode="release" endpoint={businessEndpoint} source={null} onSealed={()=>{}}/>}
 </>}
 </div></main></div>;
}
