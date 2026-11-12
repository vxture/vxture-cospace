import React,{useEffect,useState} from 'react';
import {businessEndpoint} from './business-endpoint';
import {Button,Drawer,StatusBadge,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {Cube,Database,FlowArrow,Package,DotsThreeVertical,Link} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {scenePhases,scenePhase,sceneDestinations,publicationAvailable,publicationLabel} from './scene-catalog-contract';
import {usePlatformSession} from './platform-auth';
import {sceneBuildMode,sceneViewSummary,type OverviewJob,type OverviewStages} from './scene-overview-contract';

const destinationIcons={data:Database,build:FlowArrow,association:Link,delivery:Package};
export function SceneMoreMenu({scene,onDetails}:{scene:SceneSpace;onDetails:()=>void}){
 return <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-xl" variant="secondary" aria-label={scene.name+'更多操作'}><DotsThreeVertical size={16}/></Button></DropdownMenuTrigger>
  <DropdownMenuContent align="end" className="scene-action-menu">
   <DropdownMenuItem onSelect={onDetails}><Cube size={16}/>场景概览</DropdownMenuItem>
   <DropdownMenuSeparator/>
   {sceneDestinations(scene).map(item=>{const Icon=destinationIcons[item.key as keyof typeof destinationIcons];return item.enabled?<DropdownMenuItem key={item.key} asChild><a href={item.href}><Icon size={16}/>{item.label}</a></DropdownMenuItem>:<DropdownMenuItem key={item.key} disabled title="当前账号无此操作权限"><Icon size={16}/>{item.label}</DropdownMenuItem>;})}
  </DropdownMenuContent>
 </DropdownMenu>;
}
export function SceneDetail({scene,onClose,mapOverlay=false}:{scene?:SceneSpace;onClose:()=>void;mapOverlay?:boolean}){
 return <Drawer open={!!scene} onClose={onClose} side="right" width="md" title="场景概览" description={scene?.name} closeLabel="关闭场景概览" className={'scene-detail-panel'+(mapOverlay?' scene-map-detail-panel':'')}>
  {scene&&<SceneOverview key={scene.id} scene={scene}/>}
 </Drawer>;
}
type Workflow={space_id:string;quality?:string;candidate_ref:{candidate_id:string}|null;counts:Record<string,number>;stages:{id:string;status:string;detail:string}[];preparation?:{inputs:{input_id:string;label:string}[]}};
const jobStates:Record<string,string>={queued:'排队中',running:'构建中',succeeded:'已完成',failed:'构建失败',interrupted:'已中断',views_failed:'视图待恢复'};
const time=(value:string)=>Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未记录';
function SceneOverview({scene}:{scene:SceneSpace}){
 const platform=usePlatformSession(),canReadBuild=!platform||!!scene.capabilities?.includes('build.run');
 const [report,setReport]=useState<Workflow|null>(null),[job,setJob]=useState<OverviewJob|null>(null),[stages,setStages]=useState<OverviewStages|null>(null);
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[buildError,setBuildError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setReport(null);setJob(null);setStages(null);setLoading(true);setError('');setBuildError('');
  const read=async(path:string)=>{const r=await fetch(businessEndpoint+path,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error();return r.json();};
  (async()=>{
   const workflow:Workflow=await read('/api/workflow?'+new URLSearchParams({space_id:scene.id}));
   if(workflow.space_id!==scene.id||!Array.isArray(workflow.stages)||!workflow.counts)throw Error();
   if(controller.signal.aborted)return;setReport(workflow);
   if(!canReadBuild)return;
   try{
    const result=await read('/api/builds?'+new URLSearchParams({space_id:scene.id}));
    if(!Array.isArray(result.jobs)||result.jobs.some((j:OverviewJob)=>j.space_id!==scene.id))throw Error();
    // Follow the selected candidate; a newer unselected task must not replace it.
    const selected=workflow.candidate_ref?.candidate_id;
    const current:OverviewJob|undefined=selected?result.jobs.find((j:OverviewJob)=>j.id===selected):[...result.jobs].sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at))[0];
    if(selected&&!current)throw Error();
    if(controller.signal.aborted)return;setJob(current||null);
    if(current){
     const saved:OverviewStages=await read('/api/build-stages?'+new URLSearchParams({space_id:scene.id,candidate_id:current.id}));
     if(saved.space_id!==scene.id||saved.job_id!==current.id||!saved.views)throw Error();
     if(!controller.signal.aborted)setStages(saved);
    }
   }catch{if(!controller.signal.aborted)setBuildError('构建记录暂不可读');}
  })().catch(()=>{if(!controller.signal.aborted)setError('概览状态暂不可读');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[scene.id,canReadBuild,revision]);
 const state=scenePhases[scenePhase(scene)],releases=[...(scene.publications||[])].sort((a,b)=>(Date.parse(b.created_at)||0)-(Date.parse(a.created_at)||0));
 const source=job?.input_binding?.label||report?.preparation?.inputs.find(i=>i.input_id===job?.input_id)?.label||job?.input_id;
 const association=report?.stages.find(s=>s.id==='association');
 const count=(key:string)=>Number.isSafeInteger(report?.counts[key])?report!.counts[key]:null;
 const objects=count('objects'),bindings=count('business_bindings'),relations=count('object_relations');
 return <div className="scene-detail-content" data-tone={state.tone}>
  <section aria-label="场景概要"><div className="scene-detail-section-heading"><h3>场景概要</h3><StatusBadge size="sm" icon={false} tone={state.tone}>{state.label}</StatusBadge></div>
   <dl><dt>场景</dt><dd>{scene.name}</dd>{scene.project_name&&<><dt>所属项目</dt><dd>{scene.project_name}</dd></>}<dt>位置</dt><dd>{scene.address||(scene.location?`${scene.location.longitude}, ${scene.location.latitude} · ${scene.location.crs}`:'位置未登记')}</dd><dt>构建模式</dt><dd>{canReadBuild?job?sceneBuildMode(job):loading?'读取中…':buildError||error||'尚无构建记录':'需构建查看权限'}</dd>{scene.description&&<><dt>用途说明</dt><dd>{scene.description}</dd></>}</dl>
  </section>
  <section aria-label="场景构建"><div className="scene-detail-section-heading"><h3>场景构建</h3>{job&&<StatusBadge size="sm" icon={false} tone={job.state==='succeeded'?'success':['failed','interrupted','views_failed'].includes(job.state)?'danger':'info'}>{jobStates[job.state]||'状态未记录'}</StatusBadge>}</div>
   {loading&&<p role="status">正在读取构建概况…</p>}
   {(error||buildError)&&<div className="scene-overview-note" role="status"><span>{error||buildError}</span><Button variant="ghost" size="sm" onClick={()=>setRevision(n=>n+1)}>重试</Button></div>}
   {!canReadBuild?<p>当前账号无构建查看权限。</p>:<dl>
    <dt>数据来源</dt><dd>{source||(!loading&&!error&&!buildError?'尚未绑定构建资料':'暂不可读')}</dd>
    <dt>{report?.candidate_ref?'当前候选':'最近构建'}</dt><dd>{job?(job.display_code||job.build_code||job.id):loading?'读取中…':error||buildError||'尚无构建记录'}</dd>
    <dt>视觉表达</dt><dd>{job?sceneViewSummary(stages,'human'):loading?'读取中…':error||buildError||'尚未构建'}</dd>
    <dt>计算表达</dt><dd>{job?sceneViewSummary(stages,'agent'):loading?'读取中…':error||buildError||'尚未构建'}</dd>
    <dt>空间关联</dt><dd>{report&&!report.candidate_ref?'尚未选择工作候选':objects!==null&&bindings!==null&&relations!==null?`${objects} 个对象 · ${bindings} 个业务绑定 · ${relations} 条关系`:association?.detail||(!loading?'暂不可读':'读取中…')}</dd>
    <dt>精度验证</dt><dd>{report?'尚无独立精度验收记录':loading?'读取中…':'暂不可读'}</dd>
   </dl>}
   {report&&canReadBuild&&<p className="scene-overview-footnote">基于{report.candidate_ref?'当前候选':'最近构建'}的保存记录；关联按当前候选统计，精度需独立验收。</p>}
  </section>
  <section aria-label="场景发布"><div className="scene-detail-section-heading"><h3>场景发布</h3><span>{releases.length} 个版本</span></div>
   {!releases.length?<p>尚未发布</p>:<ol className="scene-overview-releases">{releases.map(release=><li key={release.id}>
    <div className="scene-overview-release-heading"><strong title={release.id}>{publicationLabel(release)}</strong><StatusBadge size="sm" icon={false} tone={publicationAvailable(release)?'brand':release.lifecycle_state==='paused'?'warning':release.lifecycle_state==='retired'?'neutral':'danger'}>{publicationAvailable(release)?'已发布':release.lifecycle_state==='paused'?'已暂停':release.lifecycle_state==='retired'?'已退役':'不可用'}</StatusBadge></div>
    <div className="scene-overview-release-meta"><time dateTime={release.created_at}>{time(release.created_at)}</time>{release.id===scene.publication_id&&<span>当前发布</span>}</div>
   </li>)}</ol>}
  </section>
 </div>;
}
