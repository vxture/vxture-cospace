import React,{useEffect,useState} from 'react';
import {Badge,Button,Select,SelectContent,SelectItem,SelectTrigger} from '@vxture/design-system';
import {ArrowClockwise,ArrowRight,Compass,Cube,Eye,Info,WarningCircle} from '@phosphor-icons/react';
import {appNavigate} from './app-router';
import {associationSource,associationTitle,associationTime,type AssociationSource} from './association-context';
import {businessEndpoint} from './business-endpoint';
import {recordLink,useRecordNavigation} from './record-navigation';
import {candidateScreenHref} from './real-space-data';
import {SceneRegistration} from './scene-registration';
import {WorkflowPageHeader} from './workflow-page-header';
import {WorkflowNavigationToggle} from './workflow-navigation';
import {BuildSceneLink} from './build-context';
import {SpaceSettings,useSpaceInformationRevision} from './space-settings';
import {runGuarded} from './unsaved-navigation';
import './publication-workspace.css';
import './spatial-reference-workspace.css';

export function SpatialReferenceWorkspace(){
 const target=useRecordNavigation();
 const information=useSpaceInformationRevision(target.space),showInfo=target.tab==='info';
 const [navOpen,setNavOpen]=useState(()=>innerWidth>=1100);
 const [jobs,setJobs]=useState<AssociationSource[]>([]),[selected,setSelected]=useState<string|null>(null),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const {available,current}=associationSource(jobs,target.space,target.job,selected);
 useEffect(()=>{
  const abort=new AbortController();setLoaded(false);setError('');setJobs([]);setSelected(null);
  Promise.all([fetch(businessEndpoint+'/api/builds?'+new URLSearchParams({space_id:target.space}),{cache:'no-store',signal:abort.signal}),fetch(businessEndpoint+'/api/selection?'+new URLSearchParams({space_id:target.space}),{cache:'no-store',signal:abort.signal})]).then(async responses=>{
   if(responses.some(response=>!response.ok))throw Error('模型来源暂不可读，请核查场景权限后重试。');
   const [builds,selection]=await Promise.all(responses.map(response=>response.json()));
   if(!Array.isArray(builds.jobs)||builds.jobs.some((job:AssociationSource)=>job.space_id!==target.space))throw Error('模型来源与当前场景不一致。');
   if(!abort.signal.aborted){setJobs(builds.jobs);setSelected(selection.candidate_id);setLoaded(true);}
  }).catch(reason=>{if(!abort.signal.aborted)setError(reason.message);});
  return()=>abort.abort();
 },[target.space,refresh]);
 // An editor always has an explicit fixed model in its URL.
 useEffect(()=>{if(!showInfo&&loaded&&current&&!target.job)appNavigate(recordLink('registration',{space:target.space,job:current.id}),true);},[loaded,current?.id,target.job,target.space,showInfo]);
 const ready=loaded&&!!current&&target.job===current.id;
 function navigate(tab:'info'|'overview',job=current?.id){appNavigate(recordLink('registration',{space:target.space,tab,...(job?{job}:{})}));if(innerWidth<1100)setNavOpen(false);}
 return <section className="publication-workspace spatial-reference-workspace" aria-label="空间基准工作面">
  {navOpen?<aside className="publication-nav workflow-nav-panel spatial-reference-nav" id="registration-navigation" aria-label="空间基准导航"><header className="workflow-nav-heading"><Compass size={18}/><h2>空间基准</h2><Badge variant="outline">{available.length}</Badge><WorkflowNavigationToggle open label="空间基准" panelId="registration-navigation" onToggle={()=>setNavOpen(false)}/></header><div className="publication-nav-surface">
   <BuildSceneLink selected={showInfo} onSelect={()=>navigate('info')}/>
   <Select value={current?.id||''} disabled={!loaded||!available.length} onValueChange={job=>navigate('overview',job)}><SelectTrigger aria-label="选择配准模型" className="publication-version-trigger"><span>{current?<><strong>{associationTitle(current)}</strong><small>快照 {current.id.slice(-8).toUpperCase()} · {associationTime(current.created_at)}</small></>:loaded?'选择配准模型':'读取模型来源…'}</span></SelectTrigger><SelectContent>{[...available].reverse().map(job=><SelectItem key={job.id} value={job.id}><span className="publication-version-option"><strong>{associationTitle(job)}</strong><small>{associationTime(job.created_at)}</small></span></SelectItem>)}</SelectContent></Select>
   <nav aria-label="空间基准功能"><Button variant={!showInfo?'secondary':'ghost'} aria-current={!showInfo?'page':undefined} onClick={()=>navigate('overview')}><Compass size={18}/>地图配准</Button></nav>
   <div className="publication-nav-foot"><Info size={14}/><p>配准资料绑定固定模型；核准后显式采用，已有服务发布保持固定。</p></div>
  </div></aside>:<WorkflowNavigationToggle open={false} label="空间基准" panelId="registration-navigation" onToggle={()=>setNavOpen(true)}/>}
  <div className="publication-content spatial-reference-content" role="region" tabIndex={0} aria-label="空间基准内容">
  <WorkflowPageHeader space={target.space} icon={<Compass size={32}/>} process="空间基准" stage={showInfo?'基本信息':'地图配准'} version={!showInfo&&current?(current.display_code||current.build_code||current.id.slice(-8).toUpperCase()):undefined} revision={showInfo?information.revision:undefined} details={!showInfo&&current&&<time dateTime={current.created_at}>{associationTime(current.created_at)}</time>} actions={!showInfo&&<>{current&&<Button asChild size="sm" variant="outline"><a href={candidateScreenHref(target.space,current.id)} target="_blank" rel="noopener noreferrer"><Eye size={16}/>查看模型</a></Button>}<Button size="icon-md" variant="ghost" aria-label="刷新配准模型" onClick={()=>{void runGuarded(()=>setRefresh(value=>value+1));}}><ArrowClockwise size={20}/></Button></>}/>
  {showInfo?<SpaceSettings embedded onRevisionChange={information.onRevisionChange}/>:<>
   {error&&<div className="spatial-reference-message" role="alert"><WarningCircle size={20}/><span>{error}</span><Button size="sm" variant="outline" onClick={()=>setRefresh(value=>value+1)}>重试</Button></div>}
   {!loaded&&!error&&<output>正在读取空间基准来源…</output>}
   {loaded&&!current&&<div className="spatial-reference-empty"><Cube size={36}/><h3>{target.job?'目标模型不可用':available.length?'选择配准模型':'尚无可用模型'}</h3><p>{target.job?'目标模型不存在、未完成或无权访问，请从导航栏重新选择。':available.length?'从板块导航栏选择已完成的模型，维护该模型的空间基准。':'先完成模型构建，再录入控制资料并进行配准。'}</p>{!available.length&&<Button asChild size="sm" variant="secondary"><a href={recordLink('build',{space:target.space})}>前往构建中心<ArrowRight size={16}/></a></Button>}</div>}
   {ready&&<SceneRegistration key={current.id+':'+refresh} spaceId={target.space} candidateId={current.id}/>}
  </>}
 </div></section>;
}
