import React,{useEffect,useRef,useState} from 'react';
import {Button,NativeSelect,Textarea,Table,TableHeader,TableBody,TableRow,TableHead,TableCell} from '@vxture/design-system';
import {dataRequest} from './data-project-client';
import type {ResourceUse} from './data-sharing-contract';
import {parseUpgradeReport,versionComparison,type UpgradeReport} from './data-upgrade-contract';
import {useUnsavedNavigation} from './unsaved-navigation';
import {useOperationConfirmation} from './operation-confirmation';

export function DataUpgradePanel({use,workspace,onChanged,onClose}:Readonly<{use:ResourceUse;workspace:string;onChanged:()=>void;onClose:()=>void}>){
 const [report,setReport]=useState<UpgradeReport|null>(null),[offset,setOffset]=useState(0),[selection,setSelection]=useState(''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[generation,setGeneration]=useState(0);
 const gate=useRef(false),request=useRef<AbortController|null>(null),pending=useRef<{key:string;body:Record<string,unknown>}|null>(null);
 const confirm=useOperationConfirmation('data-upgrade:'+use.id);
 useUnsavedNavigation(!!reason||busy,'版本升级');useEffect(()=>()=>request.current?.abort(),[]);
 useEffect(()=>{const c=new AbortController();setLoading(true);setReport(null);setSelection('');setError('');
  void dataRequest('/api/data-reference-upgrade?'+new URLSearchParams({use_id:use.id,offset:String(offset),limit:'20'}),c.signal).then(v=>parseUpgradeReport(v,use,workspace,offset)).then(v=>{if(!c.signal.aborted)setReport(v);}).catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:'版本读取失败。');}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();
 },[use.id,use.revision,workspace,offset,generation]);
 const selected=report?.candidates.find(v=>v.grant.id===selection);
 async function upgrade(){
  if(gate.current||!report||!selected){return;}gate.current=true;setBusy(true);setError('');const c=new AbortController();request.current=c;
  const fields={action:'upgrade',use_id:use.id,grant_id:selected.grant.id,expected_grant_revision:selected.grant.revision,expected_revision:report.use.revision,expected_version:report.use.version_id,reason},key=JSON.stringify(fields),body=pending.current?.key===key?pending.current.body:{...fields,request_id:crypto.randomUUID().replaceAll('-','')};pending.current={key,body};
  try{await dataRequest('/api/data-sharing',c.signal,body);if(!c.signal.aborted){setReason('');onChanged();onClose();}}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'升级失败，原引用保持不变。');}finally{gate.current=false;if(!c.signal.aborted)setBusy(false);}
 }
 return <section className="data-upgrade-panel data-sharing-form" aria-label="比较与升级"><div className="data-lineage-heading"><h3>比较与升级</h3><Button size="sm" variant="outline" disabled={loading||busy} onClick={()=>setGeneration(v=>v+1)}>刷新</Button></div>
 {loading&&<output>正在读取已授权版本…</output>}{error&&<p role="alert">{error}</p>}{report&&<>{!report.total?<p className="data-resource-secondary">暂无其他已授权版本。管理方共享新版本后，可在此比较并确认升级。</p>:<><label>候选版本<NativeSelect disabled={busy} value={selection} onChange={e=>setSelection(e.target.value)}><option value="">选择已授权版本</option>{report.candidates.map(v=><option key={v.grant.id} value={v.grant.id}>{v.snapshot.label} · {v.grant.version_id.slice(0,12)} · {v.grant.target_kind==='workspace'?'工作区授权':'项目授权'}</option>)}</NativeSelect></label>{selected&&<Table className="data-upgrade-table"><TableHeader><TableRow><TableHead>项目</TableHead><TableHead>当前引用</TableHead><TableHead>候选版本</TableHead></TableRow></TableHeader><TableBody>{versionComparison(report.current,selected.snapshot).map(([label,current,next])=><TableRow key={label}><TableCell>{label}</TableCell><TableCell>{current}</TableCell><TableCell>{next}</TableCell></TableRow>)}</TableBody></Table>}</>}
 {report.total>20&&<div className="data-sharing-pagination"><span>共 {report.total} 项</span><Button size="sm" variant="outline" disabled={busy||!offset} onClick={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><Button size="sm" variant="outline" disabled={busy||report.next_offset===null} onClick={()=>setOffset(report.next_offset!)}>下一页</Button></div>}</>}
 <label>升级原因<Textarea value={reason} maxLength={200} disabled={busy} onChange={e=>setReason(e.target.value)}/></label><p className="data-resource-secondary">仅更新此条参考关联的固定版本，保留原用途、关联场景与升级审计。构建输入和已发布服务保持原固定版本。</p>
 <div className="data-drawer-footer"><Button variant="outline" disabled={busy} onClick={onClose}>{reason?'放弃修改':'关闭比较'}</Button><Button disabled={loading||busy||!selected||!reason.trim()} onClick={()=>void confirm({verb:'升级引用',target:use.snapshot.label,consequence:'将此条参考关联切换到所选固定版本，保留升级前的审计记录。'},upgrade)}>{busy?'保存中…':'确认升级'}</Button></div></section>;
}
