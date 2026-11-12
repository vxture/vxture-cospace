import React from 'react';
import {Button,NativeSelect,StatusBadge,Tabs,TabsList,TabsTrigger,TabsContent} from '@vxture/design-system';
import {ArrowSquareOut,ArrowsClockwise} from '@phosphor-icons/react';
import {Cube} from '@phosphor-icons/react';
import {WorkspaceHeading} from './workspace-frame';
import {serviceKinds,type ServiceSpace,type ServiceVersion} from './spatial-service-contract';
import {sceneServiceTabs,type SceneServiceTab} from './service-workspace-contract';
import {serviceStateLabels,serviceVersionLabel} from './spatial-service-list';
import {ServiceAccess} from './spatial-service-detail';
import {OnlineServiceMonitor,useServiceReport} from './online-service-monitor';
import {realScreenHref} from './real-space-data';
import {locationLabel} from './geographic-location';

export function UnavailableServiceSection({section}:{section:'feedback'|'recipients'}){
 return <section className="service-unavailable" aria-label={sceneServiceTabs[section]}><StatusBadge size="sm" icon={false} tone="neutral">尚未开放</StatusBadge><h2>{section==='feedback'?'态势反馈接入尚未开放':'服务对象登记尚未开放'}</h2><p>{section==='feedback'?'开放后可在此查看反馈接入、反馈记录与处理状态。':'开放后可在此查看服务对象、使用方式及关联版本。'}</p></section>;
}

function ServiceOverview({group,version,revision}:{group:ServiceSpace;version:ServiceVersion;revision:number}){
 const {allowed,report,error}=useServiceReport(group.scene,group.scene.id,revision);
 const configLabels={configured:'接入已配置',not_configured:'接入未配置',not_granted:'未授权接入',unavailable:'接入配置异常'};
 const checkLabels={integration:'接入授权需核对',publication:'可分发版本需核对',freshness:'观测时效未核验',observation:'监测覆盖需核对'};
 const attention=report?.assurance.checks.filter(check=>check.state!=='pass')||[];
 return <div className="scene-service-overview">
  <section className="service-page-section"><h2>服务能力</h2><p className="spatial-service-section-note">发布于 {new Date(version.release.created_at).toLocaleString('zh-CN',{hour12:false})}</p><div className="service-capability-summary">{(['preview','query','offline'] as const).map(kind=>{
   const item=version.services.find(value=>value.kind===kind);
   return <div key={kind}><span>{serviceKinds[kind].label}</span><StatusBadge size="sm" icon={false} tone={item?.available?'success':'neutral'}>{!item?'未授权':item.available?'可使用':serviceStateLabels[item.state]}</StatusBadge></div>;
  })}</div><p className="spatial-service-section-note">操作固定到页头所选版本，新发布不会自动替换。</p></section>
  <section className="service-page-section"><h2>接入与调用</h2>{!allowed?<p className="spatial-service-section-note">当前账号没有运行监测权限，可使用已授权的服务能力。</p>:error?<p role="alert" className="spatial-service-section-note">{error}</p>:!report?<p role="status" className="spatial-service-section-note">正在读取运行摘要…</p>:<><dl className="service-summary-metrics"><div><dt>服务身份接入</dt><dd>{configLabels[report.configuration.state]||'待核对'}</dd></div><div><dt>场景调用 · 近 24 小时</dt><dd>{report.request_count.toLocaleString()} 次</dd></div><div><dt>服务异常 · 近 24 小时</dt><dd>{report.counts.failed} 次</dd></div></dl><p className="spatial-service-section-note">调用摘要覆盖此场景的全部版本。{report.coverage.partial?'当前统计窗口记录不完整。':''}未记录到调用不代表设备离线。</p></>}</section>
  <section className="service-page-section"><h2>需要关注</h2>{!version.available&&<p className="service-attention">所选版本{serviceStateLabels[version.state]}，预览、查询与交付操作均已停用。</p>}{attention.map(check=><p className="service-attention" key={check.key}>{checkLabels[check.key]}</p>)}{!attention.length&&<p className="spatial-service-section-note">{!allowed?'运行监测信息仅向场景发布管理员开放。':error?'监测暂不可读，无法判断运行情况。':!report?'正在核对服务情况…':'当前核查项未发现需关注记录。'}</p>}</section>
 </div>;
}

export function SceneServicePage({group,version,tab,revision,onTab,onVersion,onRefresh}:{group:ServiceSpace;version?:ServiceVersion;tab:SceneServiceTab;revision:number;onTab:(tab:SceneServiceTab)=>void;onVersion:(id:string)=>void;onRefresh:()=>void}){
 const preview=version?.services.find(item=>item.kind==='preview'),query=version?.services.find(item=>item.kind==='query'),offline=version?.services.find(item=>item.kind==='offline');
 const scene=group.scene;
 return <Tabs value={tab} onValueChange={value=>onTab(value as SceneServiceTab)} className="scene-service-page">
  <div className="scene-service-top">
   <WorkspaceHeading icon={Cube} title={`${scene.name} · 场景服务`} description={`${scene.project_name||'未指定项目'} · ${scene.address||locationLabel(scene.location)}`} secondary={version&&<StatusBadge size="sm" icon={false} tone={version.available?'success':'neutral'}>{serviceStateLabels[version.state]}</StatusBadge>} actions={<div className="scene-service-heading-actions"><NativeSelect wrapperClassName="scene-service-version-select" id="scene-service-version" aria-label="查看服务版本" value={version?.release.id||''} onChange={event=>onVersion(event.target.value)}>{!version&&<option value="" disabled>所选版本不可用，请重新选择</option>}{group.versions.map(value=><option key={value.release.id} value={value.release.id}>Ver: {serviceVersionLabel(value)} · {serviceStateLabels[value.state]}</option>)}</NativeSelect>
    {preview?.available?<Button size="xl" variant="outline" asChild><a href={realScreenHref(scene.id,preview.release.id)} target="_blank" rel="noopener noreferrer">空间预览<ArrowSquareOut size={16}/></a></Button>:<Button size="xl" variant="outline" disabled>空间预览<ArrowSquareOut size={16}/></Button>}<Button size="icon-xl" variant="outline" aria-label="刷新场景服务" onClick={onRefresh}><ArrowsClockwise size={16}/></Button></div>}/>
   <div className="scene-service-tab-scroll"><TabsList aria-label="场景服务维度">{Object.entries(sceneServiceTabs).map(([key,label])=><TabsTrigger key={key} value={key}>{label}</TabsTrigger>)}</TabsList></div>
  </div>
  {!version?<p className="spatial-service-section-note" role="alert">所选发布版本已不可访问，操作已停止。请明确选择其他版本。</p>:<>
   <TabsContent value="overview"><ServiceOverview group={group} version={version} revision={revision}/></TabsContent>
   <TabsContent value="online"><div className="service-tab-body">{query?<ServiceAccess key={query.id} item={query}/>:<p className="spatial-service-section-note">当前账号未获此版本的在线查询权限。</p>}<OnlineServiceMonitor scene={scene} space={scene.id} revision={revision}/></div></TabsContent>
   <TabsContent value="offline">{offline?<ServiceAccess key={offline.id} item={offline}/>:<p className="spatial-service-section-note">当前账号未获此版本的离线交付权限。</p>}</TabsContent>
   <TabsContent value="feedback"><UnavailableServiceSection section="feedback"/></TabsContent>
   <TabsContent value="recipients"><UnavailableServiceSection section="recipients"/></TabsContent>
  </>}
 </Tabs>;
}
