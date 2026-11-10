import React,{useEffect,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent,StatusBadge,Table,TableHeader,TableBody,TableHead,TableRow,TableCell} from '@vxture/design-system';
import {ArrowsClockwise} from '@phosphor-icons/react';
import {businessEndpoint} from './business-endpoint';
import {recordLink} from './record-navigation';
import type {SceneSpace} from './scene-directory';

type Report={space_id:string;generated_at:string;window:{from:string;to:string};configuration:{state:'configured'|'not_configured'|'not_granted'|'unavailable';callers:string[]};coverage:{started_at:string;partial:boolean;write_failed_at:string|null;retention_days:number;max_events:number};request_count:number;counts:{historical_result:number;refused:number;rejected:number;failed:number};last_request_at:string|null;p95_ms:number|null;versions:{publication_id:string;requests:number}[];recent:{at:string;caller:string;publication:string;outcome:string;http_status:number;duration_ms:number}[]};
const configLabels={configured:'服务接入已配置',not_configured:'服务接入未配置',not_granted:'当前空间未授权接入',unavailable:'接入配置异常'};
const time=(value:string|null)=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'暂无记录';
const reasons:Record<string,string>={historical_result:'返回历史结果',observation_time_unverified:'观测时效未核验',publication_distribution_paused:'版本已暂停',publication_retired:'版本已退役',consumer_version_mismatch:'版本摘要不匹配',consumer_frame_mismatch:'坐标系不匹配',consumer_space_denied:'空间授权拒绝',consumer_publication_not_found:'版本不存在',consumer_request_or_publication_invalid:'请求或成果无效',subscription_required:'订阅授权拒绝',consumer_dependency_unavailable:'依赖暂不可用'};
export function OnlineServiceMonitor({scene,space,revision}:{scene?:SceneSpace;space:string;revision:number}){
 const allowed=!!scene?.capabilities?.includes('publication.manage');
 const [refresh,setRefresh]=useState(0),[saved,setSaved]=useState<{space:string;report?:Report;error?:string}|null>(null);
 useEffect(()=>{if(!space||!allowed)return;const timer=window.setInterval(()=>{if(document.visibilityState==='visible')setRefresh(value=>value+1);},30000);return()=>window.clearInterval(timer);},[space,allowed]);
 useEffect(()=>{
  if(!space||!allowed)return;
  const controller=new AbortController();setSaved(null);
  fetch(`${businessEndpoint}/api/service-monitor?${new URLSearchParams({space_id:space})}`,{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error(response.status===403?'监测权限已变化，请刷新空间目录。':'服务监测暂不可用，请重试。');
   const report:Report=await response.json();
   if(report.space_id!==space)throw Error('监测记录与当前空间不一致。');
   if(!controller.signal.aborted)setSaved({space,report});
  }).catch(error=>{if(!controller.signal.aborted)setSaved({space,error:error.message});});
  return()=>controller.abort();
 },[space,allowed,revision,refresh]);
 if(!space)return <Card><CardContent className="pt-xl text-body-small text-muted-foreground">请通过顶部空间选择器选择空间，查看其在线服务与运行记录。</CardContent></Card>;
 if(!scene)return <Card><CardContent className="pt-xl text-body-small text-muted-foreground">正在核对当前空间授权，请稍候；若持续未显示，请刷新空间目录。</CardContent></Card>;
 if(!allowed)return <Card><CardContent className="pt-xl text-body-small text-muted-foreground">当前账号可使用下方已授权服务。调用监测与接入身份信息仅向空间发布管理员开放。</CardContent></Card>;
 const report=saved?.space===space?saved.report:undefined,error=saved?.space===space?saved.error:undefined;
 return <div className="flex flex-col gap-lg mb-xl" aria-label="在线服务监测">
  <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-md"><CardTitle className="text-heading-3">运行概览 · {scene.name}</CardTitle><div className="flex gap-sm"><Button asChild variant="secondary" size="xl"><a href={recordLink('delivery',{space})}>发布管理</a></Button><Button variant="outline" size="icon-xl" aria-label="刷新在线监测" onClick={()=>setRefresh(value=>value+1)}><ArrowsClockwise size={16}/></Button></div></div></CardHeader><CardContent className="flex flex-col gap-lg">
   {error?<p role="alert" className="text-body-small">{error}</p>:!report?<p role="status" className="text-body-small text-muted-foreground">正在读取运行记录…</p>:<>
    <div className="flex flex-wrap items-center gap-sm"><StatusBadge tone={report.configuration.state==='configured'?'info':report.configuration.state==='unavailable'?'danger':'neutral'}>{configLabels[report.configuration.state]}</StatusBadge><span className="text-body-small text-muted-foreground">更新于 {time(report.generated_at)} · 前台每 30 秒刷新</span></div>
    <p className="text-body-small text-muted-foreground">{report.configuration.state==='configured'?'已配置服务票据与空间调用授权；实际消费仍需校验固定版本、发布状态与观测时效。':'当前无法提供此空间的正式服务接入。请由部署管理员核对平台服务身份与空间授权配置。'}</p>
    <dl className="service-monitor-metrics"><div><dt>记录请求 · 近 24 小时</dt><dd>{report.request_count}</dd></div><div><dt>返回历史结果</dt><dd>{report.counts.historical_result}</dd></div><div><dt>时效拒绝</dt><dd>{report.counts.refused}</dd></div><div><dt>请求拒绝 / 服务异常</dt><dd>{report.counts.rejected} / {report.counts.failed}</dd></div><div><dt>请求耗时 P95</dt><dd>{report.p95_ms===null?'—':`${report.p95_ms} ms`}</dd></div><div><dt>最近请求</dt><dd className="text-body-small">{time(report.last_request_at)}</dd></div></dl>
    <p className="text-label-small text-muted-foreground">统计窗口 {time(report.window.from)} — {time(report.window.to)}。开始记录于 {time(report.coverage.started_at)}；{report.coverage.partial?'当前窗口记录不完整':'当前窗口内的已记录请求'}。{report.coverage.write_failed_at&&'曾发生记录写入失败。'}仅统计通过服务身份、租户及空间调用授权的请求；采用尽力记录，非可用率或 SLA 审计。</p>
    <div><h3 className="text-body font-medium mb-sm">已授权调用身份</h3><div className="flex flex-wrap gap-sm">{report.configuration.callers.length?report.configuration.callers.map(caller=><StatusBadge key={caller} tone="neutral">{caller}</StatusBadge>):<p className="text-body-small text-muted-foreground">暂无已配置的空间调用身份</p>}</div><p className="text-label-small text-muted-foreground mt-sm">一个调用身份可代理多个具身智能体，不表示设备数量或在线状态。</p></div>
   </>}
  </CardContent></Card>
  {report&&<Card><CardHeader><CardTitle className="text-heading-3">调用与版本</CardTitle></CardHeader><CardContent className="flex flex-col gap-lg">
   <div className="flex flex-wrap gap-sm" aria-label="调用最多的前十个版本">{report.versions.map(version=><StatusBadge key={version.publication_id} tone="neutral">Ver: {version.publication_id.slice(-8)} · {version.requests} 次</StatusBadge>)}</div>
   {report.recent.length?<div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>请求时间</TableHead><TableHead>调用身份</TableHead><TableHead>版本</TableHead><TableHead>结果</TableHead><TableHead>耗时</TableHead></TableRow></TableHeader><TableBody>{report.recent.map((row,index)=><TableRow key={index}><TableCell>{time(row.at)}</TableCell><TableCell>{row.caller}</TableCell><TableCell title={row.publication}>Ver: {row.publication.slice(-8)}</TableCell><TableCell>{reasons[row.outcome]||'服务异常'} · {row.http_status}</TableCell><TableCell>{row.duration_ms} ms</TableCell></TableRow>)}</TableBody></Table></div>:<p className="text-body-small text-muted-foreground">当前窗口暂无调用记录。未记录到请求不代表设备离线。</p>}
   <p className="text-label-small text-muted-foreground">显示最近 20 条；最多保留 {report.coverage.retention_days} 天，系统总量上限 {report.coverage.max_events.toLocaleString()} 条。不记录票据、查询坐标或返回内容。下方选择固定版本查看接入说明与查询能力。</p>
  </CardContent></Card>}
 </div>;
}
