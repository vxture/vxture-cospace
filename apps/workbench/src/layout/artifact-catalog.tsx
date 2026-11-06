import React,{useEffect,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent,Input,Select,SelectTrigger,SelectValue,SelectContent,SelectItem,StatusBadge} from '@vxture/design-system';
import {previewEndpoint,realScreenHref} from './real-space-data';
import {recordLink,useRecordNavigation} from './record-navigation';
import {ArtifactImpact} from './artifact-impact';
import {ArtifactControl} from './artifact-control';

type Kind='input'|'candidate'|'publication'|'offline_package';
type Item={lifecycle_state?:string;lifecycle_revision?:number;key:string;kind:Kind;record_id:string;label:string;classification:string;state:string;created_at:string|null;integrity:string;problems:string[];resources:Record<string,string>;selected:boolean;format?:string;model_manifest_sha256?:string};
type Relation={from:string;to:string|null;relation:string;status:'matched'|'missing'|'mismatch'|'unrecorded'};
type Report={space_id?:string;observed_at:string;items:Item[];relations:Relation[];counts:Record<Kind,number>;job_counts:Record<string,number>;selection_status:string};
const kinds:Record<Kind,string>={input:'登记资料',candidate:'模型候选',publication:'固定发布',offline_package:'离线包'};
const classifications:Record<string,string>={registered_source:'封存来源',geometry_candidate:'几何候选',semantic_candidate:'语义候选',candidate_unknown:'候选待核查',fixed_publication:'固定快照',offline_export:'发布派生包'};
const integrity:Record<string,string>={record_only:'仅登记记录 · 未复核原文件',snapshot_verified:'本次快照完整性通过',unavailable:'不可用 · 需核查',not_generated:'按需导出 · 未生成包摘要',not_checked:'未检查'};
const relations:Record<string,string>={built_from:'构建输入',annotated_from:'标注基线',published_from:'发布候选',exported_from:'导出来源',sourced_from:'保存的输入来源'};
const statuses:Record<Relation['status'],string>={matched:'记录绑定一致',missing:'来源记录缺失',mismatch:'绑定不一致',unrecorded:'未记录来源'};

export function ArtifactCatalog({revision,onOpenInput}:{revision:number;onOpenInput:()=>void}){
 const context=useRecordNavigation();
 const [impactKey,setImpactKey]=useState('');
 const [controlKey,setControlKey]=useState('');
 useEffect(()=>{setImpactKey('');setControlKey('');},[context.space,context.artifact]);
 useEffect(()=>{if(impactKey)document.getElementById('artifact-impact')?.scrollIntoView({block:'start'});},[impactKey]);
 useEffect(()=>{if(controlKey)document.getElementById('artifact-control')?.scrollIntoView({block:'start'});},[controlKey]);
 const [report,setReport]=useState<Report|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[search,setSearch]=useState(''),[kind,setKind]=useState('all'),[refresh,setRefresh]=useState(0);
 useEffect(()=>{
  const request=new AbortController();setReport(null);setError('');setBusy(true);
  const query=context.space?'?'+new URLSearchParams({space_id:context.space}):'';
  fetch(`${previewEndpoint}/api/artifacts${query}`,{signal:request.signal}).then(async response=>{
   const body=await response.json();if(!response.ok)throw Error('成果目录无法读取，请检查本机服务及目录记录。');
   if((body.space_id||'')!==context.space||body.profile!=='cospace.preview-artifact-catalog/0.1')throw Error('成果目录空间绑定不一致。');
   if(!request.signal.aborted)setReport(body);
  }).catch(e=>{if(!request.signal.aborted)setError(e.message);}).finally(()=>{if(!request.signal.aborted)setBusy(false);});
  return()=>request.abort();
 },[context.space,refresh,revision]);
 useEffect(()=>{if(context.artifact&&report)document.getElementById('artifact-details')?.scrollIntoView({block:'nearest'});},[context.artifact,report]);
 const selected=(report?.space_id||'')===context.space?report?.items.find(item=>item.key===context.artifact):undefined;
 const visible=report?.items.filter(item=>(kind==='all'||item.kind===kind)&&`${item.label} ${item.record_id} ${classifications[item.classification]||''}`.toLowerCase().includes(search.trim().toLowerCase()))||[];
 function select(item:Item){setSearch('');setKind('all');location.hash=recordLink('data',{artifact:item.key});}
 function renderRelation(relation:Relation,direction:'source'|'dependent'){
  const key=direction==='source'?relation.to:relation.from;
  const item=report?.items.find(item=>item.key===key);
  return <div key={relation.from+relation.relation} className="flex flex-wrap items-center justify-between gap-sm border-b border-border pb-sm"><div className="min-w-0"><p className="text-body-small">{relations[relation.relation]} · {statuses[relation.status]}</p>{item&&<p className="text-label-small text-muted-foreground break-all">{kinds[item.kind]} · {item.label} · {item.record_id}</p>}</div>{item&&<Button size="sm" variant="outline" onClick={()=>select(item)}>查看关联成果</Button>}</div>;
 }
 const pending=report?Object.entries(report.job_counts).filter(([state])=>state!=='succeeded').reduce((total,[,count])=>total+count,0):0;
 return <div className="flex flex-col gap-lg"><Card aria-label="空间成果目录"><CardHeader><div className="flex flex-wrap items-center justify-between gap-md"><CardTitle>空间成果目录</CardTitle><Button variant="outline" size="sm" disabled={busy} onClick={()=>setRefresh(v=>v+1)}>刷新成果</Button></div></CardHeader><CardContent className="flex flex-col gap-lg">
 <p className="text-body-small text-muted-foreground">按空间整理资料、候选、发布与离线包。点击成果查看上游来源和下游引用。</p>
 {report&&<div className="grid grid-cols-2 gap-md sm:grid-cols-4" aria-label="成果分类统计">{(Object.keys(kinds) as Kind[]).map(type=><Button key={type} variant={kind===type?'secondary':'outline'} className="justify-between gap-sm" onClick={()=>setKind(kind===type?'all':type)}><span className="text-body-small">{kinds[type]}</span><span className="text-body-small font-medium">{report.counts[type]}</span></Button>)}</div>}
 <div className="grid grid-cols-1 gap-md sm:grid-cols-2"><Input aria-label="搜索空间成果" placeholder="搜索成果名称、ID或候选类型" value={search} onChange={e=>setSearch(e.target.value)}/><Select value={kind} onValueChange={setKind}><SelectTrigger aria-label="成果类型"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="all">全部类型</SelectItem>{(Object.keys(kinds) as Kind[]).map(type=><SelectItem key={type} value={type}>{kinds[type]}</SelectItem>)}</SelectContent></Select></div>
 {busy&&<p role="status" className="text-body-small">正在读取成果与绑定关系…</p>}{error&&<p role="alert" className="text-body-small">{error}</p>}
 {report&&<><p className="text-label-small text-muted-foreground">当前显示 {visible.length} 项 · {new Date(report.observed_at).toLocaleString('zh-CN',{hour12:false})} 读取。{pending>0&&`另有 ${pending} 个未成功完成的任务，请在构建中心查看。`}</p>{report.selection_status==='missing_or_mismatch'&&<p role="alert" className="text-body-small">当前候选选择指向缺失或不一致的记录，请到构建中心核查。</p>}{!report.items.length&&<p className="text-body-small text-muted-foreground">当前范围尚无空间成果，可先登记资料。</p>}{!!report.items.length&&!visible.length&&<p className="text-body-small text-muted-foreground">没有匹配的空间成果。</p>}
 {visible.map(item=><article key={item.key} aria-label={`${kinds[item.kind]} ${item.record_id}`} className="flex min-w-0 flex-col gap-sm border-b border-border pb-md"><div className="flex flex-wrap items-start justify-between gap-sm"><button className="min-w-0 text-left text-body-small font-medium text-primary break-all hover:underline" onClick={()=>select(item)}>{item.label}</button><div className="flex flex-wrap gap-sm"><StatusBadge tone={item.integrity==='unavailable'?'danger':'info'}>{classifications[item.classification]}</StatusBadge>{item.lifecycle_state&&item.lifecycle_state!=='active'&&<StatusBadge tone="warning">{item.lifecycle_state==='retired'?'已退役':item.lifecycle_state==='disabled'?'已停用':(item.lifecycle_state==='paused'||item.lifecycle_state==='retired')?'已暂停分发':'已归档'}</StatusBadge>}{item.selected&&<StatusBadge tone="info">当前所选</StatusBadge>}</div></div><p className="text-label-small text-muted-foreground break-all">{item.record_id} · {integrity[item.integrity]}</p><div className="flex flex-wrap items-center justify-between gap-sm"><p className="text-label-small text-muted-foreground">{item.created_at?new Date(item.created_at).toLocaleString('zh-CN',{hour12:false}):item.kind==='offline_package'?'包创建时间未生成':'登记时间未记录'}</p><Button size="sm" variant="outline" onClick={()=>select(item)}>查看成果</Button></div></article>)}</>}
 <p className="text-label-small text-muted-foreground">目录仅核对当前记录和快照；未重新预检源文件，未检查消费端安装状态。快照完整不代表精度验收。</p>
 </CardContent></Card>
 {report&&context.artifact&&!selected&&<p role="alert" className="text-body-small break-all">目标成果不存在于当前空间目录：{context.artifact}</p>}
 {report&&selected&&<Card id="artifact-details" aria-label="成果关系详情"><CardHeader><CardTitle>{kinds[selected.kind]} · 成果关系</CardTitle></CardHeader><CardContent className="flex flex-col gap-lg"><p className="text-body-small font-medium break-all">{selected.label}</p><p className="text-label-small text-muted-foreground break-all">{selected.record_id} · {integrity[selected.integrity]}</p>{selected.model_manifest_sha256&&<p className="text-label-small text-muted-foreground break-all">模型清单摘要：{selected.model_manifest_sha256}</p>}
 {selected.integrity==='unavailable'&&<p role="alert" className="text-body-small">快照不可用或记录绑定不一致，相关下载与预览入口已隐藏；请查看原始记录处理。</p>}
 {context.space&&<Button className="self-start" variant="outline" size="sm" onClick={()=>{setControlKey('');setImpactKey(selected.kind==='offline_package'?'publication:'+selected.record_id:selected.key);}}>{selected.kind==='offline_package'?'检查来源发布生命周期':'检查生命周期影响'}</Button>}
 {context.space&&(selected.kind==='input'||selected.kind==='candidate'||selected.kind==='publication'||selected.kind==='offline_package')&&<Button className="self-start" variant="outline" size="sm" onClick={()=>{setImpactKey('');setControlKey(selected.kind==='offline_package'?'publication:'+selected.record_id:selected.key);}}>管理使用状态</Button>}
 <div className="flex flex-wrap gap-sm">{selected.kind==='input'&&<Button asChild size="sm"><a href={recordLink('data',{input:selected.record_id})} onClick={onOpenInput}>详情与预检</a></Button>}{selected.kind==='candidate'&&<Button asChild size="sm" variant="outline"><a href={recordLink('build',{job:selected.record_id})}>定位构建记录</a></Button>}{(selected.kind==='publication'||selected.kind==='offline_package')&&<Button asChild size="sm" variant="outline"><a href={recordLink('delivery',{publication:selected.record_id})}>定位固定发布</a></Button>}
 {selected.kind==='publication'&&selected.integrity==='snapshot_verified'&&(!selected.lifecycle_state||selected.lifecycle_state==='active')&&<Button asChild size="sm"><a href={context.space?realScreenHref(context.space,selected.record_id):`${previewEndpoint}${selected.resources.preview_url}`} target="_blank" rel="noopener noreferrer">打开固定空间</a></Button>}
 {selected.resources.download_url&&<Button asChild size="sm"><a href={previewEndpoint+selected.resources.download_url} download>下载离线包</a></Button>}{selected.resources.info_url&&<Button asChild size="sm" variant="outline"><a href={previewEndpoint+selected.resources.info_url} target="_blank" rel="noopener noreferrer">查看包摘要与格式</a></Button>}{selected.resources.manifest_url&&<Button asChild size="sm" variant="ghost"><a href={previewEndpoint+selected.resources.manifest_url} target="_blank" rel="noopener noreferrer">查看固定清单</a></Button>}</div>
 <section aria-label="上游来源" className="flex flex-col gap-md"><p className="text-body-small font-medium">上游来源</p>{report.relations.filter(r=>r.from===selected.key).map(r=>renderRelation(r,'source'))}{!report.relations.some(r=>r.from===selected.key)&&<p className="text-body-small text-muted-foreground">{selected.kind==='input'?'这是链路中登记的输入起点。':'当前没有可读取的来源关系，请查看原始记录。'}</p>}</section>
 <section aria-label="下游引用" className="flex flex-col gap-md"><p className="text-body-small font-medium">下游引用</p>{report.relations.filter(r=>r.to===selected.key).map(r=>renderRelation(r,'dependent'))}{!report.relations.some(r=>r.to===selected.key)&&<p className="text-body-small text-muted-foreground">当前目录没有后续引用记录。</p>}</section>
 {selected.kind==='offline_package'&&<p className="text-label-small text-muted-foreground">此项是由固定发布按需导出的包入口。目录未生成ZIP或包摘要，不表示已下载、安装、激活或完成交付。</p>}
 </CardContent></Card>}
 {report&&selected&&impactKey===(selected.kind==='offline_package'?'publication:'+selected.record_id:selected.key)&&context.space&&<ArtifactImpact key={context.space+impactKey} space={context.space} artifact={impactKey} revision={refresh+revision} onClose={()=>setImpactKey('')}/>}
 {report&&selected&&controlKey===(selected.kind==='offline_package'?'publication:'+selected.record_id:selected.key)&&context.space&&<ArtifactControl key={context.space+controlKey} space={context.space} artifact={controlKey} onClose={()=>setControlKey('')} onCommitted={()=>{setImpactKey('');setRefresh(v=>v+1);}}/>}
 </div>;
}
