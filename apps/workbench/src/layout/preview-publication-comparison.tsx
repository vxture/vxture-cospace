import React,{useEffect,useRef,useState} from 'react';
import {Button,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter,Select,SelectTrigger,SelectValue,SelectContent,SelectItem} from '@vxture/design-system';
import {previewEndpoint,realScreenHref} from './real-space-data';
import {recordLink} from './record-navigation';

type Publication={lifecycle_state?:string;id:string;candidate_id:string;created_at:string;preview_url:string};
type ModelRef={candidate_id:string;model_manifest_sha256:string};
type PublicationRef=ModelRef&{publication_id:string;created_at:string;publication_record_sha256:string};
type ObjectInfo={object_id:string;properties:Record<string,string>};
type Provenance={status:'not_recorded'|'internally_consistent'|'binding_mismatch';matches_requested_base_model:boolean|null;
 saved_review:null|{reviewed_at?:string;note?:string;reviewer?:string;comparison?:{base_ref?:ModelRef|null;target_ref?:ModelRef;comparison_sha256?:string}}};
type Report={comparison_sha256:string;space_id?:string;base_publication:PublicationRef;target_publication:PublicationRef;geometry_comparable:boolean;
 changes:{coordinate:{same_frame:boolean;same_resolution:boolean};geometry:{same_source_model:boolean;base_surface_cells:number;target_surface_cells:number;added_surface:{count:number}|null;removed_surface:{count:number}|null};
 relations?:{added:unknown[];removed:unknown[];modified:unknown[]};business?:{added:unknown[];removed:unknown[];modified:unknown[]};ontology:{changed:boolean;base_ref:unknown;target_ref:unknown};objects:{base_available:boolean;target_available:boolean;added:ObjectInfo[];removed:ObjectInfo[];modified:{object_id:string;fields:string[];before:ObjectInfo;after:ObjectInfo}[];unchanged_count:number}};
 provenance:{base:Provenance;target:Provenance}};

function ReviewRecord({label,record,target=false}:{label:string;record:Provenance;target?:boolean}){
 const titles={not_recorded:'未记录更新核对',internally_consistent:'已保存核对 · 内部绑定一致',binding_mismatch:'保存记录绑定不一致'};
 return <section className="flex flex-col gap-sm" aria-label={label}><p className="text-body-small font-medium">{label}</p><p className="text-body-small">{titles[record.status]}</p>
 {record.status==='binding_mismatch'&&<p className="text-label-small text-muted-foreground">请核查发布清单中的保存记录；该记录不能作为本次比较的核对依据。</p>}
 {record.status==='internally_consistent'&&record.saved_review&&<><p className="text-body-small whitespace-pre-wrap break-all">{record.saved_review.note||'无核对说明'}</p>
 {record.saved_review.reviewed_at&&<p className="text-label-small text-muted-foreground">{new Date(record.saved_review.reviewed_at).toLocaleString('zh-CN',{hour12:false})}</p>}
 <p className="text-label-small text-muted-foreground break-all">核对基线候选：{record.saved_review.comparison?.base_ref?.candidate_id||'首次选择或无有效记录'}</p>
 {target&&record.status==='internally_consistent'&&<p className="text-label-small text-muted-foreground">{record.matches_requested_base_model?'核对基线与本次基线的模型一致；不表示已记录两个发布之间的父子关系。':'核对基线与本次基线模型不同；该记录不能代表本次两个版本之间已核对。'}</p>}
 <p className="text-label-small text-muted-foreground">本机保存记录，未认证审批人身份。</p></>}
 </section>;
}

export function PreviewPublicationComparison({target,publications,space,onClose,onTrace}:{target:Publication;publications:Publication[];space:string;onClose:()=>void;onTrace:(publication:string)=>void}){
 const [base,setBase]=useState(''),[report,setReport]=useState<Report|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const controller=useRef<AbortController|null>(null);
 function clear(){controller.current?.abort();setReport(null);setError('');setBusy(false);}
 useEffect(()=>{clear();setBase('');return()=>controller.current?.abort();},[target.id,space]);
 const available=publications.filter(item=>item.id!==target.id&&(!item.lifecycle_state||item.lifecycle_state==='active'));
 async function compare(){
  clear();const request=new AbortController();controller.current=request;setBusy(true);
  try{
   const response=await fetch(`${previewEndpoint}/api/publication-comparisons`,{method:'POST',headers:{'Content-Type':'application/json'},signal:request.signal,
    body:JSON.stringify({space_id:space||null,base_publication_id:base,target_publication_id:target.id})});
   const body=await response.json();if(!response.ok)throw Error(String(body.detail||'发布比较失败'));
   if(body.base_publication?.publication_id!==base||body.target_publication?.publication_id!==target.id||(body.space_id||'')!==space)throw Error('发布比较绑定不一致，请刷新记录。');
   if(!request.signal.aborted)setReport(body);
  }catch(e){if(!request.signal.aborted)setError(e instanceof Error?e.message:'发布比较失败');}
  finally{if(!request.signal.aborted)setBusy(false);}
 }
 function download(){if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`${base}-to-${target.id}.json`;link.click();URL.revokeObjectURL(url);}
 return <Dialog open onOpenChange={v=>{if(!v)onClose();}}><DialogContent className="candidate-review-dialog max-w-panel-lg max-h-[85dvh] overflow-auto"><DialogHeader><DialogTitle>固定发布变化追溯</DialogTitle><DialogDescription>明确选择基线，比较两个固定发布。仅查询快照与保存记录，不切换候选或发布。</DialogDescription></DialogHeader>
 <p className="text-body-small break-all">目标发布：{target.id}</p>
 <div className="flex flex-col gap-sm"><label htmlFor="publication-base" className="text-body-small">基线发布</label><Select value={base} onValueChange={value=>{clear();setBase(value);}}><SelectTrigger id="publication-base" aria-label="基线发布"><SelectValue placeholder="请选择同一空间的固定发布"/></SelectTrigger><SelectContent>{available.map(item=><SelectItem key={item.id} value={item.id}>{item.id} · {new Date(item.created_at).toLocaleString('zh-CN',{hour12:false})}</SelectItem>)}</SelectContent></Select></div>
 {!available.length&&<p className="text-body-small text-muted-foreground">本空间还没有其他固定发布，暂不能比较。</p>}
 {busy&&<p role="status" className="text-body-small">正在比较固定发布…</p>}{error&&<p role="alert" className="text-body-small break-all">{error}</p>}
 {report&&<div className="flex flex-col gap-lg" aria-label="固定发布差异">
 <div className="grid grid-cols-1 gap-lg border-y border-border py-md sm:grid-cols-3"><section><p className="text-body-small font-medium">几何与表面</p><p className="mt-sm text-label-small text-muted-foreground">{report.changes.geometry.same_source_model?'复用同一几何':'几何来源有变化'} · {report.changes.geometry.base_surface_cells.toLocaleString()} → {report.changes.geometry.target_surface_cells.toLocaleString()} 单元</p><p className="mt-xs text-label-small">新增 {report.changes.geometry.added_surface?.count.toLocaleString()??'不可比较'} · 移除 {report.changes.geometry.removed_surface?.count.toLocaleString()??'不可比较'}</p></section>
 <section><p className="text-body-small font-medium">对象标注</p><p className="mt-sm text-label-small">新增 {report.changes.objects.added.length} · 移除 {report.changes.objects.removed.length} · 修改 {report.changes.objects.modified.length}</p><p className="mt-xs text-label-small text-muted-foreground">未变化 {report.changes.objects.unchanged_count} · {report.changes.objects.base_available?'基线有标注':'基线无标注快照'} · {report.changes.objects.target_available?'目标有标注':'目标无标注快照'}</p></section>
 <section><p className="text-body-small font-medium">坐标与本体</p><p className="mt-sm text-label-small">{report.changes.ontology.changed?'本体引用有变化':'本体引用未变化'}</p><p className="mt-xs text-label-small text-muted-foreground">{report.changes.coordinate.same_frame?'坐标声明一致':'坐标声明不同'} · {report.changes.coordinate.same_resolution?'分辨率一致':'分辨率不同'}</p></section></div>
 {!report.geometry_comparable&&<p role="alert" className="text-body-small">坐标声明或分辨率不同，不能直接计算表面单元增减；核对记录仍可查看。</p>}
 {report.changes.relations&&<details><summary className="cursor-pointer text-body-small">对象关系 · 新增 {report.changes.relations.added.length} · 解除 {report.changes.relations.removed.length} · 修订 {report.changes.relations.modified.length}</summary><pre className="mt-md max-h-48 overflow-auto whitespace-pre-wrap break-all text-label-small">{JSON.stringify(report.changes.relations,null,2)}</pre></details>}
 {report.changes.business&&<details><summary className="cursor-pointer text-body-small">业务台账绑定 · 新增 {report.changes.business.added.length} · 解除 {report.changes.business.removed.length} · 换版 {report.changes.business.modified.length}</summary><pre className="mt-md max-h-48 overflow-auto whitespace-pre-wrap break-all text-label-small">{JSON.stringify(report.changes.business,null,2)}</pre></details>}
 <details><summary className="cursor-pointer text-body-small">查看对象与本体差异</summary><div className="mt-md flex flex-col gap-md">
 {report.changes.objects.added.map(obj=><p className="text-body-small break-all" key={'add-'+obj.object_id}>新增标注 · {obj.properties.name||obj.object_id} · {obj.object_id}</p>)}
 {report.changes.objects.removed.map(obj=><p className="text-body-small break-all" key={'remove-'+obj.object_id}>移除标注 · {obj.properties.name||obj.object_id} · {obj.object_id}</p>)}
 {report.changes.objects.modified.map(obj=><div key={obj.object_id}><p className="text-body-small break-all">修改 · {obj.object_id} · {obj.fields.join('、')}</p><pre className="mt-sm max-h-48 overflow-auto whitespace-pre-wrap break-all text-label-small">{JSON.stringify({before:obj.before,after:obj.after},null,2)}</pre></div>)}
 <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-label-small">{JSON.stringify({基线本体:report.changes.ontology.base_ref,目标本体:report.changes.ontology.target_ref},null,2)}</pre></div></details>
 <div className="grid grid-cols-1 gap-lg border-b border-border pb-md sm:grid-cols-2"><ReviewRecord label="基线核对记录" record={report.provenance.base}/><ReviewRecord label="目标核对记录" record={report.provenance.target} target/></div>
 <div className="grid grid-cols-1 gap-lg sm:grid-cols-2">{([['基线',report.base_publication],['目标',report.target_publication]] as const).map(([label,ref])=><section key={label} className="flex min-w-0 flex-col gap-sm"><p className="text-body-small font-medium">{label}快照</p><p className="text-label-small break-all">{ref.publication_id}<br/>{ref.candidate_id}</p><div className="flex flex-wrap gap-sm"><Button asChild size="sm" variant="outline"><a href={space?realScreenHref(space,ref.publication_id):`${previewEndpoint}/publications/${ref.publication_id}/`} target="_blank" rel="noopener noreferrer">打开{label}</a></Button><Button asChild size="sm" variant="ghost"><a href={recordLink('delivery',{space,publication:ref.publication_id})} onClick={()=>{onTrace(ref.publication_id);onClose();}}>来源追溯</a></Button><Button asChild size="sm" variant="ghost"><a href={recordLink('build',{space,job:ref.candidate_id})} onClick={onClose}>构建记录</a></Button></div></section>)}</div>
 <p className="text-label-small text-muted-foreground">表面证据移除不表示空闲，未列出区域保持未知。对象差异是标注差异，不代表实物已确认变化；两类视图对应各自固定快照，精度待验收。</p><p className="text-label-small text-muted-foreground break-all">比较摘要：{report.comparison_sha256}</p>
 </div>}
 <DialogFooter>{report&&<Button variant="outline" onClick={download}>下载比较记录</Button>}<Button variant="outline" onClick={onClose}>关闭</Button><Button disabled={!base||busy} onClick={compare}>{busy?'正在比较':report?'重新比较':'比较版本'}</Button></DialogFooter>
 </DialogContent></Dialog>;
}
