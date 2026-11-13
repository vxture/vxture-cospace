import React,{useEffect,useState} from 'react';
import {businessEndpoint} from './business-endpoint';
import {Button,Drawer,StatusBadge,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {Cube,Database,FlowArrow,Package,DotsThreeVertical,Link,Broadcast} from '@phosphor-icons/react';
import type {SceneSpace} from './scene-directory';
import {scenePhases,scenePhase,sceneDestinations,publicationAvailable,publicationLabel} from './scene-catalog-contract';
import {usePlatformSession} from './platform-auth';
import {sceneBuildMode,sceneViewSummary,type OverviewJob,type OverviewStages} from './scene-overview-contract';

const destinationIcons={data:Database,build:FlowArrow,association:Link,delivery:Package,services:Broadcast};
export function SceneMoreMenu({scene,onDetails}:{scene:SceneSpace;onDetails:()=>void}){
 return <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-xl" variant="secondary" aria-label={scene.name+'更多操作'}><DotsThreeVertical size={16}/></Button></DropdownMenuTrigger>
  <DropdownMenuContent align="end" className="scene-action-menu">
   <DropdownMenuItem onSelect={onDetails}><Cube size={16}/>场景概览</DropdownMenuItem>
   {sceneDestinations(scene).map((item,index)=>{const Icon=destinationIcons[item.key as keyof typeof destinationIcons];return <React.Fragment key={item.key}>{(index===1||item.key==='data')&&<DropdownMenuSeparator/>}{item.enabled?<DropdownMenuItem asChild><a href={item.href}><Icon size={16}/>{item.label}</a></DropdownMenuItem>:<DropdownMenuItem disabled title="当前账号无此操作权限"><Icon size={16}/>{item.label}</DropdownMenuItem>}</React.Fragment>;})}
  </DropdownMenuContent>
 </DropdownMenu>;
}
export function SceneDetail({scene,onClose,mapOverlay=false}:{scene?:SceneSpace;onClose:()=>void;mapOverlay?:boolean}){
 return <Drawer open={!!scene} onClose={onClose} side="right" width="md" title="场景概览" description={scene?.name} closeLabel="关闭场景概览" className={'scene-detail-panel'+(mapOverlay?' scene-map-detail-panel':'')}>
  {scene&&<SceneOverview key={scene.id} scene={scene}/>}
 </Drawer>;
}
type Overview={space_id:string;candidate_ref:{candidate_id:string}|null;job:OverviewJob|null;stages:OverviewStages|null;counts:Record<string,number>|null};
const jobStates:Record<string,string>={queued:'排队中',running:'构建中',succeeded:'已完成',failed:'构建失败',interrupted:'已中断',views_failed:'视图待恢复'};
const time=(value:string)=>Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'时间未记录';
function SceneOverview({scene}:{scene:SceneSpace}){
 const platform=usePlatformSession(),canReadBuild=!platform||!!scene.capabilities?.includes('build.run');
 const [report,setReport]=useState<Overview|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');
  if(!canReadBuild){setLoading(false);return()=>controller.abort();}
  fetch(businessEndpoint+'/api/scene-overview?'+new URLSearchParams({space_id:scene.id}),{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error();const saved:Overview=await response.json();
   if(saved.space_id!==scene.id||saved.job&&saved.job.space_id!==scene.id||saved.stages&&(saved.stages.space_id!==scene.id||saved.stages.job_id!==saved.job?.id))throw Error();
   if(!controller.signal.aborted)setReport(saved);
  }).catch(()=>{if(!controller.signal.aborted)setError('概览状态暂不可读');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[scene.id,canReadBuild,revision]);
 const job=report?.job,stages=report?.stages||null;
 const state=scenePhases[scenePhase(scene)],releases=[...(scene.publications||[])].sort((a,b)=>(Date.parse(b.created_at)||0)-(Date.parse(a.created_at)||0));
 const source=job?.input_binding?.label||job?.input_id;
 const count=(key:string)=>Number.isSafeInteger(report?.counts?.[key])?report!.counts![key]:null;
 const objects=count('objects'),bindings=count('business_bindings'),relations=count('object_relations');
 const pending=loading?'—':error||'尚无构建记录';
 return <div className="scene-detail-content" data-tone={state.tone}>
  <section aria-label="场景概要"><div className="scene-detail-section-heading"><h3>场景概要</h3><StatusBadge size="sm" icon={false} tone={state.tone}>{state.label}</StatusBadge></div>
   <dl><dt>场景</dt><dd>{scene.name}</dd>{scene.project_name&&<><dt>所属项目</dt><dd>{scene.project_name}</dd></>}<dt>位置</dt><dd>{scene.address||(scene.location?`${scene.location.longitude}, ${scene.location.latitude} · ${scene.location.crs}`:'位置未登记')}</dd><dt>构建模式</dt><dd>{canReadBuild?job?sceneBuildMode(job):pending:'需构建查看权限'}</dd>{scene.description&&<><dt>用途说明</dt><dd>{scene.description}</dd></>}</dl>
  </section>
  <section aria-label="场景构建" aria-busy={loading}><div className="scene-detail-section-heading"><h3>场景构建</h3>{job&&<StatusBadge size="sm" icon={false} tone={job.state==='succeeded'?'success':['failed','interrupted','views_failed'].includes(job.state)?'danger':'info'}>{jobStates[job.state]||'状态未记录'}</StatusBadge>}</div>
   {error&&<div className="scene-overview-note" role="status"><span>{error}</span><Button variant="ghost" size="sm" onClick={()=>setRevision(n=>n+1)}>重试</Button></div>}
   {!canReadBuild?<p>当前账号无构建查看权限。</p>:<dl>
    <dt>数据来源</dt><dd>{source||(loading?'—':error||'尚未绑定构建资料')}</dd>
    <dt>{report?.candidate_ref?'当前候选':'最近构建'}</dt><dd>{job?(job.display_code||job.build_code||job.id):pending}</dd>
    <dt>视觉表达</dt><dd>{job?sceneViewSummary(stages,'human'):loading?'—':error||'尚未构建'}</dd>
    <dt>计算表达</dt><dd>{job?sceneViewSummary(stages,'agent'):loading?'—':error||'尚未构建'}</dd>
    <dt>空间关联</dt><dd>{report&&!report.candidate_ref?'尚未选择工作候选':objects!==null&&bindings!==null&&relations!==null?`${objects} 个对象 · ${bindings} 个业务绑定 · ${relations} 条关系`:loading?'—':'暂不可读'}</dd>
    <dt>精度验证</dt><dd>{report?'尚无独立精度验收记录':loading?'—':'暂不可读'}</dd>
   </dl>}

  </section>
  <section aria-label="场景发布"><div className="scene-detail-section-heading"><h3>场景发布</h3><span>{releases.length} 个版本</span></div>
   {!releases.length?<p>尚未发布</p>:<ol className="scene-overview-releases">{releases.map(release=><li key={release.id}>
    <div className="scene-overview-release-heading"><strong title={release.id}>{publicationLabel(release)}</strong><div className="scene-overview-release-status">{release.id===releases[0]?.id&&<span>最新版本</span>}<StatusBadge size="sm" icon={false} tone={publicationAvailable(release)?'brand':release.lifecycle_state==='paused'?'warning':release.lifecycle_state==='retired'?'neutral':'danger'}>{publicationAvailable(release)?'已发布':release.lifecycle_state==='paused'?'已暂停':release.lifecycle_state==='retired'?'已退役':'不可用'}</StatusBadge></div></div>
    <div className="scene-overview-release-meta"><time dateTime={release.created_at}>{time(release.created_at)}</time></div>
   </li>)}</ol>}
  </section>
 </div>;
}
