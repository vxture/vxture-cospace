import {WorkspaceContent} from './workspace-content';
import {SceneOntologyRelationsPanel} from './scene-ontology-relations';
import {RegistrationSummary} from './registration-summary';
import {SceneOntologyLinksPanel} from './scene-ontology-links';
import {WorkflowPageHeader} from './workflow-page-header';
import {WorkflowNextStep} from './workflow-next-step';
import {associationNextStep} from './association-next-step';
import {useAssistantReport} from './workspace-assistant';
import {candidateScreenHref} from './real-space-data';
import {associationExamples,associationExample} from './association-examples';
import {WorkflowNavigationToggle} from './workflow-navigation';
import React,{useEffect,useState} from 'react';
import {Badge,Button,StatusBadge,Select,SelectTrigger,SelectContent,SelectItem} from '@vxture/design-system';
import {LinkSimple,ChartDonut,Selection,TreeStructure,IdentificationCard,Eye,Info,Sparkle,ArrowRight,Cube,WarningCircle,Books,FileText} from '@phosphor-icons/react';
import {ObjectAnnotations} from './object-annotations';
import {BusinessAssociations} from './business-associations';
import {ObjectRelations} from './object-relations';
import {IfcCatalog} from './ifc-catalog';
import {SpaceSettings,useSpaceInformationRevision} from './space-settings';
import {BuildSceneLink} from './build-context';
import {recordLink,useRecordNavigation,RecordNavigationProvider} from './record-navigation';
import {appNavigate} from './app-router';
import {businessEndpoint as endpoint} from './business-endpoint';
import {associationSource,associationTime as time,associationTitle as title,type AssociationSource} from './association-context';
import './publication-workspace.css';
import './association-workspace.css';

const sections=[
 {id:'overview',name:'关联概览',icon:ChartDonut,description:'查看模型来源、已保存的关联内容与后续处理事项。'},
 {id:'objects',name:'对象管理',icon:Selection,description:'在模型上建立对象，维护类型、属性及位置证据。'},
 {id:'relations',name:'空间关系',icon:TreeStructure,description:'维护对象归属与连接声明，按固定规则核验关系。'},
 {id:'business',name:'业务关联',icon:IdentificationCard,description:'为对象关联固定台账版本，保留来源与变更依据。'},
] as const;
type View=typeof sections[number]['id']|'ifc'|'info';
type Objects={model_id:string;space_id:string;ontology_ref?:{ontology_id:string;version:string;sha256:string};objects:{object_id:string;anchor_m:number[];properties:Record<string,string>;business_links?:unknown[]}[];relations?:unknown[]};
type Model={id:string;space_id:string;semantic_annotation?:unknown;frame_id:string;unit:string;construction?:{model_points?:number}};
export function SpatialAssociations(){const target=useRecordNavigation();return <AssociationWorkspace key={target.space}/>;}
function AssociationWorkspace(){
 const target=useRecordNavigation();
 const example=associationExample(new URLSearchParams(location.search).get('example'));
 const view:View=['overview','objects','relations','business','ifc','info'].includes(target.tab)?target.tab as View:'overview';
 const information=useSpaceInformationRevision(target.space);
 const [jobs,setJobs]=useState<AssociationSource[]>([]),[selected,setSelected]=useState<string|null>(null),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const [model,setModel]=useState<Model|null>(null),[objects,setObjects]=useState<Objects|null>(null),[snapshotError,setSnapshotError]=useState(''),[reading,setReading]=useState(false);
 const [visited,setVisited]=useState<View[]>([view]),[navOpen,setNavOpen]=useState(()=>innerWidth>=1100);
 const {available,current}=associationSource(jobs,target.space,target.job,selected);
 const section=sections.find(s=>s.id===(view==='ifc'?'objects':view));
 useEffect(()=>{setVisited(old=>old.includes(view)?old:[...old,view]);},[view]);
 useEffect(()=>{const abort=new AbortController();setLoaded(false);setError('');setJobs([]);setSelected(null);
  if(!target.space){setLoaded(true);return()=>abort.abort();}
  Promise.all([fetch(`${endpoint}/api/builds?`+new URLSearchParams({space_id:target.space}),{signal:abort.signal,cache:'no-store'}),fetch(`${endpoint}/api/selection?`+new URLSearchParams({space_id:target.space}),{signal:abort.signal,cache:'no-store'})]).then(async responses=>{
   if(responses.some(r=>!r.ok))throw Error('模型来源暂时无法读取，请重试。');
   const [j,s]=await Promise.all(responses.map(r=>r.json()));if(abort.signal.aborted)return;
   if(!Array.isArray(j.jobs)||j.jobs.some((r:AssociationSource)=>r.space_id!==target.space))throw Error('模型来源与当前场景不一致。');
   setJobs(j.jobs);setSelected(s.candidate_id);setLoaded(true);
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();
 },[target.space,target.job,refresh]);
 // Pin the server-selected source in the URL before enabling an editor.
 useEffect(()=>{if(view!=='ifc'&&loaded&&current&&!target.job)appNavigate(recordLink('association',{space:target.space,job:current.id,tab:view}),true);},[loaded,current?.id,target.job,target.space,view]);
 useEffect(()=>{const abort=new AbortController();setModel(null);setObjects(null);setSnapshotError('');setReading(false);if(!current)return()=>abort.abort();setReading(true);
  (async()=>{const response=await fetch(`${endpoint}/candidates/${current.id}/api/preview`,{signal:abort.signal,cache:'no-store'});if(!response.ok)throw Error('模型快照无法读取，请核查权限及来源。');const manifest:Model=await response.json();if(manifest.id!==current.id||manifest.space_id!==target.space)throw Error('模型快照与当前来源不一致。');
   let contents:Objects|null=null;if(manifest.semantic_annotation){const r=await fetch(`${endpoint}/candidates/${current.id}/api/objects`,{signal:abort.signal,cache:'no-store'});if(!r.ok)throw Error('已保存的对象快照无法读取。');contents=await r.json();if(!contents||contents.model_id!==current.id||contents.space_id!==target.space||!Array.isArray(contents.objects))throw Error('对象快照与当前来源不一致。');}
   if(!abort.signal.aborted){setModel(manifest);setObjects(contents);}
  })().catch(e=>{if(!abort.signal.aborted)setSnapshotError(e.message);}).finally(()=>{if(!abort.signal.aborted)setReading(false);});return()=>abort.abort();
 },[current?.id,target.space,refresh]);
 function navigate(next:View,job=current?.id){appNavigate(recordLink('association',{space:target.space,tab:next,...(job&&next!=='ifc'?{job}:{})}));if(innerWidth<1100)setNavOpen(false);}
 const ready=loaded&&!!current&&target.job===current.id;
 const next=associationNextStep(view,current?.id===selected);
 useAssistantReport({title:'关联检查',status:error||snapshotError?'error':!loaded||reading?'loading':'ready',note:error||snapshotError||(!current?'当前场景没有可用的模型来源。':undefined),tasks:!loaded||reading||error||snapshotError||!current?[]:[{id:'next',title:'继续下一环节',evidence:next.description,label:next.label,run:()=>appNavigate(recordLink(next.module,{space:target.space,job:current.id,tab:next.tab}))},{id:'objects',title:objects?.objects.length?'核对对象与位置':'建立场景对象',evidence:objects?.objects.length?`当前快照已保存 ${objects.objects.length} 个对象。`:'当前模型尚未保存对象标注。',label:'对象管理',run:()=>navigate('objects')},...(objects?.objects.length?[{id:'relations',title:'核对空间关系',evidence:`已保存 ${objects.relations?.length||0} 条关系声明，需按现场含义核实。`,label:'空间关系',run:()=>navigate('relations')},{id:'business',title:'核对业务关联',evidence:'业务引用需要固定台账版本并保留来源。',label:'业务关联',run:()=>navigate('business')}]:[])]});

 return <section className={`publication-workspace association-workspace `} aria-label="空间关联工作区">
  {navOpen?<aside className="publication-nav association-nav workflow-nav-panel" id="association-navigation" aria-label="关联导航"><header className="workflow-nav-heading"><LinkSimple size={18}/><h2>空间关联</h2><Badge variant="outline">{available.length}</Badge><WorkflowNavigationToggle open={true} label="关联" panelId="association-navigation" onToggle={()=>setNavOpen(false)}/></header><div className="publication-nav-surface"><BuildSceneLink selected={view==='info'} onSelect={()=>navigate('info')}/><Select value={current?.id||''} onValueChange={id=>navigate(view,id)} disabled={!loaded}><SelectTrigger aria-label="选择关联模型" className="publication-version-trigger"><span>{current?<><strong>来源构建 {title(current)}</strong><small>快照 {current.id.slice(-8).toUpperCase()} · {time(current.created_at)}</small></>:loaded?'选择来源构建':'读取模型来源…'}</span></SelectTrigger><SelectContent>{[...available].reverse().map(j=><SelectItem key={j.id} value={j.id}><span className="publication-version-option"><strong>{title(j)} · {j.id.slice(-8).toUpperCase()}</strong><small>{time(j.created_at)} · {j.view_parent_id||j.base_candidate_id?'派生候选':'构建候选'}</small></span></SelectItem>)}</SelectContent></Select><nav aria-label="关联功能">{sections.map(s=><Button key={s.id} variant={section?.id===s.id?'secondary':'ghost'} aria-current={section?.id===s.id?'page':undefined} onClick={()=>navigate(s.id)}><s.icon size={18}/>{s.name}</Button>)}</nav><div className="publication-nav-foot"><Info size={14}/><p>模型声明保存为新候选；本体应用保存为消费侧修订。既有服务发布保持固定。</p></div></div></aside>:<WorkflowNavigationToggle open={false} label="关联" panelId="association-navigation" onToggle={()=>setNavOpen(true)}/>}
  <div className="publication-content association-content workspace-content-viewport" role="region" tabIndex={0} aria-label="关联内容"><WorkspaceContent className="workspace-content-stack"><WorkflowPageHeader space={target.space} icon={<LinkSimple size={32}/>} process="空间关联" stage={view==='info'?'基本信息':view==='ifc'?'参考资料':section?.name||'关联概览'} version={view!=='info'&&view!=='ifc'&&current?(current.display_code||current.build_code||current.id.slice(-8).toUpperCase()):undefined}
    revision={view==='info'?information.revision:undefined}
    status={view!=='info'&&view!=='ifc'&&current&&<StatusBadge tone="neutral">历史快照</StatusBadge>}
    details={view!=='info'&&view!=='ifc'&&current&&<><time dateTime={current.created_at}>{time(current.created_at)}</time></>}
    actions={view!=='info'&&<>{view!=='ifc'&&current&&<Button asChild size="sm" variant="outline"><a href={candidateScreenHref(target.space,current.id)} target="_blank" rel="noopener noreferrer"><Eye size={16}/>查看模型</a></Button>}{view!=='ifc'&&target.space&&<Button variant="outline" size="sm" onClick={()=>navigate('ifc')}><Books size={16}/>参考资料</Button>}{view==='ifc'&&<Button variant="outline" size="sm" onClick={()=>navigate('objects')}>返回对象</Button>}</>}/>
   {view==='objects'&&<details className="association-example-templates" open={example?true:undefined}><summary>示例标注模板{example&&` · ${example.name}`}</summary><div className="flex flex-col gap-md"><div className="flex flex-wrap gap-sm">{associationExamples.map(item=><Button asChild key={item.id} variant={example?.id===item.id?'secondary':'ghost'} size="sm"><a href={recordLink('association',{space:target.space,tab:'objects',example:item.id,...(current?{job:current.id}:{})})}>{item.name}</a></Button>)}</div><p className="text-body-small text-muted-foreground">合成示例只提供设备名称与建议类型；选择场景、本体规则和模型后，逐个选点核实。原楼层为示例信息，空间归属在“空间关系”中维护。</p>{example&&<p className="text-label-small">{example.level} · {example.objects.map(o=>o.name).join('、')}</p>}{!target.space&&<output className="block">请从顶部场景选择器选择目标场景。</output>}</div></details>}
   {view!=='ifc'&&error&&<div role="alert" className="publication-message"><WarningCircle size={18}/><span>{error}</span><Button variant="ghost" size="sm" onClick={()=>setRefresh(v=>v+1)}>重试</Button></div>}
   {visited.includes('info')&&<div hidden={view!=='info'} className="association-view"><SpaceSettings embedded onRevisionChange={information.onRevisionChange}/></div>}
   {view==='ifc'&&target.space&&<div className="association-view"><IfcCatalog/></div>}
   {view!=='ifc'&&view!=='info'&&!loaded&&!error&&<output className="block">正在读取关联来源…</output>}
   {view!=='ifc'&&view!=='info'&&target.space&&loaded&&!current&&<AssociationSourceEmpty requested={!!target.job} count={available.length}/>}
   {view!=='ifc'&&ready&&<RecordNavigationProvider value={{...target,job:current.id}}><section className="association-current" aria-label="关联功能内容">
    {view!=='info'&&<header className="workspace-section-heading association-stage-heading"><div><h3>{section&&React.createElement(section.icon,{size:20})}{section?.name}</h3><p>{section?.description}</p></div></header>}
    {visited.includes('overview')&&<div hidden={view!=='overview'} className="association-view"><AssociationOverview model={model} objects={objects} reading={reading} error={snapshotError} source={current} selected={selected} active={view==='overview'} onNavigate={navigate}/><SceneOntologyLinksPanel key={current.id} spaceId={target.space} candidateId={current.id} active={view==='overview'}/></div>}
    {visited.includes('objects')&&<div hidden={view!=='objects'} className="association-view"><ObjectAnnotations key={current.id} embedded active={view==='objects'}/></div>}
    {visited.includes('relations')&&<div hidden={view!=='relations'} className="association-view"><SceneOntologyRelationsPanel key={current.id+'-ontology'} spaceId={target.space} candidateId={current.id} active={view==='relations'}/><section aria-label="原关系声明"><header className="workspace-section-heading association-stage-heading"><div><h3>原关系声明</h3><p>维护模型候选中的关系；保存并切换新候选后，再显式映射本体。</p></div></header><ObjectRelations key={current.id} embedded/></section></div>}
    {visited.includes('business')&&<div hidden={view!=='business'} className="association-view"><BusinessAssociations key={current.id} embedded/></div>}
   </section></RecordNavigationProvider>}
   {ready&&!reading&&!error&&!snapshotError&&!!model&&view!=='info'&&view!=='ifc'&&<WorkflowNextStep description={next.description} label={next.label} href={recordLink(next.module,{space:target.space,job:current.id,tab:next.tab})}/>}
  </WorkspaceContent></div>
 </section>;
}
function AssociationSourceEmpty({requested,count}:{requested:boolean;count:number}){return <section className="publication-empty"><Cube size={36}/><h3>{requested?'目标模型不可用':'选择关联模型'}</h3><p>{requested?'目标候选不存在、未成功或无权访问。请从左栏重新选择。':count?'从左栏选择一个成功构建的模型，开始维护关联。':'当前场景暂无可用模型，请先完成模型构建。'}</p>{!count&&<Button asChild variant="secondary"><a href={recordLink('build',{tab:'flow'})}><ArrowRight size={16}/>前往构建</a></Button>}</section>;}
function AssociationOverview({model,objects,reading,error,source,selected,active,onNavigate}:{model:Model|null;objects:Objects|null;reading:boolean;error:string;source:AssociationSource;selected:string|null;active:boolean;onNavigate:(view:View)=>void}){
 if(reading)return <output className="block">正在读取模型与关联快照…</output>;
 if(error)return <p role="alert" className="publication-message">{error}</p>;
 if(!model)return null;
 const count=objects?.objects.length||0,located=objects?.objects.filter(o=>o.anchor_m?.length===3).length||0,bindings=objects?.objects.filter(o=>o.business_links?.length).length||0;
 return <div className="association-overview"><RegistrationSummary spaceId={source.space_id} candidateId={source.id} active={active}/><div className="association-metrics">{[{name:'已保存对象',value:count,unit:'个',icon:Selection,view:'objects'},{name:'模型位置',value:located,unit:'个点锚',icon:Cube,view:'objects'},{name:'空间关系',value:objects?.relations?.length||0,unit:'项',icon:TreeStructure,view:'relations'},{name:'业务绑定',value:bindings,unit:'个对象',icon:IdentificationCard,view:'business'}].map(m=><button key={m.name} className="association-metric" onClick={()=>onNavigate(m.view as View)}><span><m.icon size={18}/>{m.name}</span><strong>{m.value.toLocaleString()}<small>{m.unit}</small></strong><span>查看清单<ArrowRight size={14}/></span></button>)}</div><section className="association-source-card"><header><Cube size={20}/><div><h4>模型与依据</h4><p>当前页面读取此固定快照，切换功能沿用同一来源。</p></div></header><dl><div><dt>来源构建</dt><dd>{title(source)} · {source.id.slice(-8).toUpperCase()}</dd></div><div><dt>模型规模</dt><dd>{Number.isFinite(model.construction?.model_points)?model.construction!.model_points!.toLocaleString()+' 点':'未记录'}</dd></div><div><dt>模型坐标</dt><dd>{model.frame_id} · {model.unit}</dd></div><div><dt>本体规则</dt><dd>{objects?.ontology_ref?`${objects.ontology_ref.ontology_id} · ${objects.ontology_ref.version}`:'尚未选用'}</dd></div></dl></section><section className="association-next"><header><WarningCircle size={20}/><div><h4>待处理事项</h4><p>按当前已保存内容判断，不代表现场验收结果。</p></div></header><ul>{!count&&<li><span>尚无对象，先添加对象并选择模型位置。</span><Button variant="ghost" size="sm" onClick={()=>onNavigate('objects')}>添加对象<ArrowRight size={14}/></Button></li>}{count>0&&<li><span>{count} 个对象的现场含义待核实。</span><Button variant="ghost" size="sm" onClick={()=>onNavigate('objects')}>查看对象<ArrowRight size={14}/></Button></li>}<li><span>{source.id===selected?'当前来源已被选定；如修改关联，新候选仍需核对。':'当前来源未被选定用于发布，关联完成后需核对。'}</span><Button asChild variant="ghost" size="sm"><a href={recordLink('build',{tab:'flow',job:source.id})}>成果核对<ArrowRight size={14}/></a></Button></li></ul></section><div className="publication-message"><Info size={16}/><span>以上为已保存快照的数量；其他功能页尚未保存的编辑不计入统计。</span></div></div>;
}
