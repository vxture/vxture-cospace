import {useState} from 'react';
import {Button,StatusBadge} from '@vxture/design-system';
import {ArrowRight,Cube,ArrowsClockwise,Broadcast,UploadSimple,Stack} from '@phosphor-icons/react';
import {appNavigate} from './app-router';
import {filterScenes,scenePhase,scenePhases,sceneTimestamp,sceneWorkspaceHref,homeSceneEntry} from './scene-catalog-contract';
import {useSceneDirectory} from './use-scene-directory';
import {useSelectedScene} from './scene-selection';
import {useHomeMonitor} from './use-home-monitor';
import {homeMonitorStatus} from './home-monitor-status';
import {SceneMoreMenu} from './scene-detail';
import './workspace-home.css';

const dateFormat=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'});
const reportTimeFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
function MonitorFooter({href,name,at=null,label='最后上报'}:{href:string;name:string;at?:string|null;label?:string}){
 return <footer><div className="workspace-home-card-time"><span>{label}：</span>{at?<time dateTime={at} title={new Date(at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}>{reportTimeFormat.format(new Date(at))}</time>:<span>—</span>}</div><Button asChild variant="secondary" size="sm"><a href={href} aria-label={name+'详情'}>详情<ArrowRight size={14}/></a></Button></footer>;
}

// A decorative spatial diagram. It represents the product, not a user's scene.
function SpatialMotif(){
 return <svg className="workspace-home-motif" viewBox="0 0 460 255" fill="none" aria-hidden="true">
  <g stroke="currentColor" opacity=".16">
   {Array.from({length:13},(_,i)=><path key={i} d={`M${30+i*17} ${155-i*8}l204 96 M${30+i*17} ${155+i*8}l204 -96`}/>)}
  </g>
  <g stroke="currentColor" strokeLinejoin="round">
   <path className="workspace-home-plane" d="M81 159 232 88l153 71-153 73Z"/>
   <path className="workspace-home-plane" d="M106 123 232 64l126 59-126 60Z"/>
   <path className="workspace-home-plane" d="M132 87 232 40l100 47-100 48Z"/>
   <path opacity=".48" d="M132 87v48l100 48 100-48V87M232 135v48M182 64v47l100 48M282 64v47l-100 48" strokeDasharray="4 4"/>
   <path opacity=".72" d="M155 157l41-19 36 17 54-25 42 20" strokeWidth="1.5"/>
   {[[155,157],[232,155],[286,130],[328,150],[232,40]].map(([x,y])=><circle key={x+':'+y} cx={x} cy={y} r="4" className="workspace-home-node"/>)}
  </g>
 </svg>;
}

export function WorkspaceHome(){
 const [revision,setRevision]=useState(0);
 const {spaces,loading,error}=useSceneDirectory(revision);
 const remembered=useSelectedScene();
 const monitor=useHomeMonitor(error?[]:spaces,revision);
 const sum=(key:'requests'|'failed'|'rejected')=>monitor.rows.reduce((total,row)=>total+row[key],0);
 const monitorPending=loading||!!error||monitor.loading;
 const metric=(key:'requests'|'failed'|'rejected')=>monitorPending||!monitor.rows.length?'—':sum(key).toLocaleString();
 const attention=monitor.rows.filter(row=>row.failed>0||row.rejected>0||row.configuration!=='configured');
 const incomplete=monitor.errors>0||monitor.rows.some(row=>row.partial);
 const serviceStatus=homeMonitorStatus(monitor.rows,monitorPending,monitor.errors);
 const generatedAt=monitor.rows.map(row=>row.generatedAt).filter((value):value is string=>!!value).sort((a,b)=>Date.parse(b)-Date.parse(a))[0]||null;
 const recent=filterScenes(spaces,'','all','time').slice(0,4);
 const resume=!error&&(spaces.find(scene=>scene.id===remembered)||recent[0]);
 return <main className="workspace-home" aria-labelledby="workspace-home-title">
   <section className="workspace-home-hero">
    <div className="workspace-home-wrap workspace-home-hero-layout">
     <SpatialMotif/>
     <div className="workspace-home-intro">
     <span className="workspace-home-kicker"><Cube size={17} weight="duotone"/> CoSpace 工作台</span>
     <h1 id="workspace-home-title">从场景开始</h1>
     <p>管理场景资料、构建空间底图，将成果发布给具身智能体使用。</p>
     <div className="workspace-home-actions">
      <Button asChild size="sm"><a href="/space">进入我的场景<ArrowRight size={15}/></a></Button>
      {resume&&<Button asChild size="sm" variant="outline"><a href={homeSceneEntry(resume).href} title={resume.name+' · '+homeSceneEntry(resume).label}>{resume.id===remembered?'继续上次场景':'进入最近场景'}</a></Button>}
     </div>
     <div className="workspace-home-resume">{resume&&<span title={resume.name}>{resume.id===remembered?'上次选择':'最近更新'} · {resume.name} · {homeSceneEntry(resume).label}</span>}</div>
     </div>
    </div>
   </section>
   <section className="workspace-home-summary" aria-labelledby="workspace-home-progress">
    <div className="workspace-home-wrap workspace-home-summary-layout">
     <div><h2 id="workspace-home-progress">服务运行 · 近 24 小时</h2><p>{monitorPending?'正在读取监测':!monitor.total?'暂无可读取的服务监测':`已读取 ${monitor.rows.length} / ${monitor.total} 个授权场景${incomplete?' · 已读取部分':''}`}</p></div>
      <dl className="workspace-home-metrics">
       <div><dt>场景数量</dt><dd>{loading||error?'—':spaces.length.toLocaleString()}</dd></div>
       <div><dt>服务调用</dt><dd>{metric('requests')}</dd></div>
       <div><dt>服务异常</dt><dd data-alert={sum('failed')>0||undefined}>{metric('failed')}</dd></div>
       <div><dt>请求拒绝</dt><dd data-alert={sum('rejected')>0||undefined}>{metric('rejected')}</dd></div>
      </dl>
    </div>
   </section>
   <div className="workspace-home-wrap workspace-home-content">
    <section className="workspace-home-section workspace-home-watch" aria-labelledby="workspace-home-watch">
     <header><h2 id="workspace-home-watch">需要关注</h2><Button size="sm" variant="outline" onClick={()=>setRevision(n=>n+1)}><ArrowsClockwise size={15}/>刷新监测</Button></header>
     <div className="workspace-home-watch-grid">
      <article data-tone={serviceStatus.tone}>
       <header><Broadcast size={20}/><h3>服务运行</h3><StatusBadge tone={serviceStatus.tone} size="sm" icon={false}>{serviceStatus.label}</StatusBadge></header>
       <div className="workspace-home-watch-body">{monitorPending?<p>正在核对运行记录…</p>:attention.length?<ul>{attention.map(row=><li key={row.space}><a href={'/services?'+new URLSearchParams({section:'online',space:row.space,tab:'online'})}>{spaces.find(scene=>scene.id===row.space)?.name||'场景'}<span>{row.failed} 次异常 · {row.rejected} 次拒绝{row.configuration==='configured'?'':row.configuration==='unavailable'?' · 配置异常':row.configuration==='not_granted'?' · 接入未授权':' · 接入未配置'}</span></a></li>)}</ul>:<p>{!monitor.rows.length?'监测数据暂不可用，无法判断运行情况。':incomplete?'已读取记录中未发现服务异常，部分监测尚不完整。':'已读取记录中未发现服务异常或请求拒绝。'}</p>}</div>
       <MonitorFooter href="/services?section=online" name="服务运行" at={generatedAt} label="监测更新"/>
      </article>
      <article><header><UploadSimple size={20}/><h3>新态势上传</h3><StatusBadge tone="neutral" size="sm" icon={false}>尚未接入</StatusBadge></header><div className="workspace-home-watch-body"><p>态势反馈接入尚未开放，暂时无法统计新增反馈与待处理记录。</p></div><MonitorFooter href="/services?section=feedback" name="新态势上传"/></article>
      <article><header><Stack size={20}/><h3>场景需重建</h3><StatusBadge tone="neutral" size="sm" icon={false}>待接通</StatusBadge></header><div className="workspace-home-watch-body"><p>重建需求需结合态势反馈、数据变更与当前构建版本判定，当前尚未接通重建待办。</p></div><MonitorFooter href="/space" name="场景需重建"/></article>
     </div>
    </section>
    <section className="workspace-home-section" aria-labelledby="workspace-home-recent">
     <header><div><h2 id="workspace-home-recent">场景工作</h2><p>{loading||error?'—':`${spaces.length} 个可访问场景 · ${spaces.filter(scene=>scenePhase(scene)==='published').length} 个已发布`} · 按最近更新排序</p></div><a className="workspace-home-all" href="/space">全部场景<ArrowRight size={16}/></a></header>
     <div className="workspace-home-panel" aria-busy={loading}>
      {loading?<div className="workspace-home-empty" role="status"><Cube size={24}/><span>正在读取场景…</span></div>:error?
       <div className="workspace-home-empty" role="alert"><p>{error}</p><Button size="sm" variant="outline" onClick={()=>setRevision(n=>n+1)}>重试</Button></div>:
       recent.length?<ul className="workspace-home-scenes">
        {recent.map(scene=>{
         const state=scenePhases[scenePhase(scene)],timestamp=sceneTimestamp(scene);
         return <li key={scene.id}><div className="workspace-home-scene"><div className="workspace-home-scene-info">
          <span className="workspace-home-icon"><Cube size={21} weight="duotone"/></span>
          <span className="workspace-home-row-copy"><strong>{scene.name}</strong><small>{scene.project_name||scene.scene_code||'场景空间'}</small></span>
         </div><div className="workspace-home-scene-meta">
          {timestamp>0&&<time dateTime={new Date(timestamp).toISOString()} title="最近更新">{dateFormat.format(timestamp)}</time>}
          <StatusBadge size="sm" tone={scene.state==='no_publication'?'neutral':state.tone} icon={false}>{scene.state==='no_publication'?'未发布':state.label}</StatusBadge>
         </div><div className="workspace-home-scene-actions" role="group" aria-label={scene.name+'操作'}>
          <Button asChild variant="secondary" size="xl"><a href={homeSceneEntry(scene).href} title={homeSceneEntry(scene).label} aria-label={'进入'+scene.name}>进入<ArrowRight size={14}/></a></Button>
          <SceneMoreMenu scene={scene} onDetails={()=>appNavigate(sceneWorkspaceHref(scene.id))}/>
         </div></div></li>;
        })}
       </ul>:
       <div className="workspace-home-empty"><Cube size={28} weight="duotone"/><strong>暂无可访问的场景</strong><p>有创建权限时可从上方新建，也可以联系管理员分配场景权限。</p></div>}
     </div>
    </section>
   </div>
 </main>;
}
