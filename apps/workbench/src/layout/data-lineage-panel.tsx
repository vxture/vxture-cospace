import React,{useEffect,useState} from 'react';
import {Button,StatusBadge} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {dataRequest} from './data-project-client';
import {parseResourceTrace,type ResourceTrace} from './data-lineage-contract';
import {sharingStatus} from './data-sharing-contract';

const date=(value:string|null)=>value?new Date(value).toLocaleString('zh-CN'):'未记录';
function currentLabel(value:boolean|null,view:string){
 if(view==='reference')return '引用固定版本';
 if(value===null)return '当前来源未核验';
 return value?'当前来源':'已登记历史版本';
}
function TraceVersions({report}:Readonly<{report:ResourceTrace}>){
 const unregistered=report.source.state==='current'&&!report.versions.some(v=>v.current);
 return <section className="data-lineage-section" aria-label="版本记录"><div className="data-lineage-heading"><h3>版本记录</h3><span className="data-resource-secondary">共 {report.versions.length} 个</span></div>
 {unregistered&&<p className="data-resource-secondary">当前来源版本尚未登记，已有引用保持原固定版本。</p>}
 {report.versions.map(v=><article key={v.version_id} className="data-lineage-version"><div className="data-sharing-record"><code title={v.version_id}>{v.version_id.slice(0,12)}</code><StatusBadge tone="neutral">{currentLabel(v.current,report.view)}</StatusBadge>{v.snapshot_saved&&<StatusBadge tone="neutral">已保存共享快照</StatusBadge>}{report.view==='source'&&report.resource.kind==='resource_file'&&<Button asChild variant="outline" size="sm"><a href={businessEndpoint+'/api/data-files/download?'+new URLSearchParams({resource_id:report.resource_id,version_id:v.version_id})}>下载原件</a></Button>}</div><p className="data-resource-secondary">{v.format||'格式未记录'} · {v.bytes==null?'大小未记录':`${v.bytes.toLocaleString()} B`} · {date(v.created_at)}</p></article>)}</section>;
}
function TraceImpact({report,offset,onOffset}:Readonly<{report:ResourceTrace;offset:number;onOffset:(value:number)=>void}>){
 return <section className="data-lineage-section" aria-label="引用影响"><div className="data-lineage-heading"><h3>引用影响</h3><span className="data-resource-secondary">仅当前可见范围</span></div><dl className="data-lineage-counts"><div><dt>关联引用</dt><dd>{report.summary.linked_references}</dd></div><div><dt>授权有效</dt><dd>{report.summary.effective_references}</dd></div><div><dt>历史引用</dt><dd>{report.summary.historical_references}</dd></div></dl>
 {report.references.map(u=><article className="data-lineage-reference" key={u.id}><div className="data-sharing-record"><strong>{u.project_name}{u.space_name?' · '+u.space_name:' · 项目级'}</strong><StatusBadge tone={u.access_status==='active'?'neutral':'warning'}>{sharingStatus[u.access_status]}</StatusBadge></div><p>{u.purpose}</p><p className="data-resource-secondary">固定版本 {u.version_id.slice(0,12)} · {date(u.updated_at)}</p></article>)}{!report.total&&<p className="data-resource-secondary">当前可见范围内没有引用记录。</p>}
 {report.total>0&&<div className="data-sharing-pagination"><span>共 {report.total} 条</span><Button size="sm" variant="outline" disabled={!offset} onClick={()=>onOffset(Math.max(0,offset-10))}>上一页</Button><Button size="sm" variant="outline" disabled={report.next_offset===null} onClick={()=>onOffset(report.next_offset!)}>下一页</Button></div>}
 <p className="data-resource-secondary">引用保留固定版本。解除引用保留历史；当前统计不作为删除或归档许可。</p></section>;
}
export function DataLineagePanel({workspace,resource,project}:Readonly<{workspace:string;resource:string;project?:string}>){
 const [offset,setOffset]=useState(0),[generation,setGeneration]=useState(0),[result,setResult]=useState<{key:string;report:ResourceTrace}|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const key=JSON.stringify([workspace,resource,project,offset,generation]),report=result?.key===key?result.report:null;
 useEffect(()=>{const c=new AbortController();setLoading(true);setError('');
  const query=new URLSearchParams({resource_id:resource,offset:String(offset),limit:'10',...(project?{project_id:project}:{})});
  void dataRequest('/api/data-lineage?'+query,c.signal).then(value=>parseResourceTrace(value,{workspace,resource,project,offset})).then(value=>{if(!c.signal.aborted)setResult({key,report:value});}).catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:'追溯记录读取失败。');}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
  return()=>c.abort();
 },[workspace,resource,project,offset,generation]);
 return <section className="data-lineage-panel" aria-label="来源与引用追溯"><div className="data-lineage-heading"><h3>来源与引用追溯</h3><Button variant="outline" size="sm" disabled={loading} onClick={()=>setGeneration(v=>v+1)}>刷新</Button></div>
 {loading&&<output>正在读取追溯记录…</output>}{error&&<p role="alert">{error}</p>}{report&&<>
 <div className="data-lineage-path"><span>{report.resource.owner}</span><span aria-hidden="true">→</span><strong>{report.resource.label}</strong><span aria-hidden="true">→</span><span>{report.summary.projects} 个可见关联项目</span></div>
 {report.source.state==='unavailable'&&<output>当前来源暂不可读取，以下为已保存的版本和引用记录。</output>}
 <TraceVersions report={report}/><TraceImpact report={report} offset={offset} onOffset={setOffset}/>
 </>}</section>;
}
