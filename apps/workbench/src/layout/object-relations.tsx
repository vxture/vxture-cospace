import {useUnsavedNavigation} from './unsaved-navigation';
import React,{useEffect,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent,Input,NativeSelect,Switch,StatusBadge} from '@vxture/design-system';
import {previewEndpoint as endpoint} from './real-space-data';
import {recordLink,useRecordNavigation} from './record-navigation';
type Ref={ontology_id:string;version:string;sha256:string};
type Version=Ref&{title:string;relation_count?:number};
type ObjectInfo={object_id:string;type_id:string;properties:Record<string,string>};
type Relation={relation_id:string;type_id:string;source_id:string;target_id:string;note:string};
type Rule={title:string;source_types:string[];target_types:string[];family:string;symmetric:boolean;parent_endpoint?:string};
type Report={status:string;issues:{code:string;path:string;message:string;relation_id?:string;object_id?:string}[]};
const key=(r:Ref)=>`${r.ontology_id}/${r.version}/${r.sha256}`;
const empty={relation_id:'',type_id:'',source_id:'',target_id:'',note:''};
const clean=(r:Relation):Relation=>({relation_id:r.relation_id,type_id:r.type_id,source_id:r.source_id,target_id:r.target_id,note:r.note});
export function ObjectRelations(){
 const target=useRecordNavigation();
 const [jobs,setJobs]=useState<{id:string}[]>([]),[versions,setVersions]=useState<Version[]>([]),[base,setBase]=useState(''),[hash,setHash]=useState(''),[objects,setObjects]=useState<ObjectInfo[]>([]),[reference,setReference]=useState(''),[rules,setRules]=useState<Record<string,Rule>>({}),[typeTitles,setTypeTitles]=useState<Record<string,string>>({});
 const [relations,setRelations]=useState<Relation[]>([]),[original,setOriginal]=useState(''),[originalRef,setOriginalRef]=useState(''),[draft,setDraft]=useState<Relation>(empty),[editing,setEditing]=useState('');
 const [loading,setLoading]=useState(false),[reading,setReading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[report,setReport]=useState<Report|null>(null),[ack,setAck]=useState(false),[created,setCreated]=useState(''),[revision,setRevision]=useState(0);
 function invalidate(){setReport(null);setAck(false);setCreated('');setError('');}
 useEffect(()=>{
  if(!target.space)return;const abort=new AbortController();setLoading(true);setError('');setBase('');setJobs([]);setVersions([]);
  Promise.all([fetch(`${endpoint}/api/builds?space_id=${target.space}`,{signal:abort.signal}),fetch(`${endpoint}/api/selection?space_id=${target.space}`,{signal:abort.signal}),fetch(`${endpoint}/api/ontologies`,{signal:abort.signal})]).then(async rs=>{
   if(rs.some(r=>!r.ok))throw Error('对象关系工作面无法读取。');const [j,s,o]=await Promise.all(rs.map(r=>r.json()));if(abort.signal.aborted)return;
   const available=j.jobs.filter((job:{state:string})=>job.state==='succeeded');setJobs(available);setVersions(o.ontologies.filter((v:Version)=>(v.relation_count||0)>0));setBase(available.some((job:{id:string})=>job.id===target.job)?target.job:s.candidate_id||'');
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});return()=>abort.abort();
 },[target.space,target.job,revision]);
 useEffect(()=>{
  const abort=new AbortController();setHash('');setObjects([]);setRelations([]);setReference('');setOriginal('');setOriginalRef('');setDraft(empty);setEditing('');invalidate();
  if(!base){setReading(false);return()=>abort.abort();}setReading(true);
  Promise.all([fetch(`${endpoint}/candidates/${base}/api/anchor?point_index=0`,{signal:abort.signal}),fetch(`${endpoint}/candidates/${base}/api/objects`,{signal:abort.signal})]).then(async rs=>{
   if(rs.some(r=>!r.ok))throw Error('基础候选尚无对象标注或固定快照不可用。');const [a,o]=await Promise.all(rs.map(r=>r.json()));if(abort.signal.aborted)return;
   if(a.candidate_id!==base||o.model_id!==base||o.space_id!==target.space)throw Error('基础对象与空间不一致。');
   const ref=key(o.ontology_ref),saved=(o.relations||[]).map(clean);setHash(a.model_manifest_sha256);setObjects(o.objects);setRelations(saved);setOriginal(JSON.stringify(saved));setOriginalRef(ref);setReference(versions.some(v=>key(v)===ref)?ref:'');
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setReading(false);});return()=>abort.abort();
 },[base,versions]);
 useEffect(()=>{
  const abort=new AbortController();setRules({});setTypeTitles({});invalidate();const ref=versions.find(v=>key(v)===reference);if(!ref)return()=>abort.abort();
  fetch(`${endpoint}/api/ontologies/${ref.ontology_id}/${ref.version}?sha256=${ref.sha256}`,{signal:abort.signal}).then(async r=>{if(!r.ok)throw Error('固定关系规则无法读取。');return r.json();}).then(body=>{if(!abort.signal.aborted){if(key(body.record)!==reference)throw Error('关系规则引用不一致。');setRules(body.definition.relations||{});setTypeTitles(Object.fromEntries(Object.entries(body.definition.types).map(([id,t])=>[id,(t as {title:string}).title])));}}).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();
 },[reference]);
 function add(e:React.FormEvent){e.preventDefault();if(relations.some(r=>r.relation_id===draft.relation_id&&r.relation_id!==editing)){setError('关系ID重复，请保持稳定且唯一。');return;}setRelations(current=>editing?current.map(r=>r.relation_id===editing?{...draft}:r):[...current,{...draft}]);setDraft(empty);setEditing('');invalidate();}
 async function validate(){
  const ref=versions.find(v=>key(v)===reference);if(!ref||!hash)return;invalidate();setBusy(true);
  try{const response=await fetch(`${endpoint}/api/ontologies/${ref.ontology_id}/${ref.version}/validate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sha256:ref.sha256,objects:objects.map(o=>({object_id:o.object_id,type_id:o.type_id,properties:o.properties})),relations})});const body=await response.json();if(!response.ok)throw Error('关系校验失败，请检查规则及完整关系集。');if(key(body.ontology_ref)!==reference)throw Error('校验版本不一致。');setReport(body);}catch(e){setError(e instanceof Error?e.message:'校验失败');}finally{setBusy(false);}
 }
 async function save(){
  const ref=versions.find(v=>key(v)===reference);if(!ref||report?.status!=='passed'||!ack)return;setBusy(true);setError('');setCreated('');
  try{const ontology_ref={ontology_id:ref.ontology_id,version:ref.version,sha256:ref.sha256};const response=await fetch(`${endpoint}/api/relation-candidates`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:target.space,base_candidate_id:base,base_manifest_sha256:hash,ontology_ref,relations})});const body=await response.json();if(!response.ok){if(body.detail?.issues){setReport(body.detail);throw Error('服务端关系校验未通过。');}throw Error(`关系候选生成失败：${typeof body.detail==='string'?body.detail:'请重新读取基础与规则。'}`);}if(body.space_id!==target.space||body.base_candidate_id!==base)throw Error('候选响应绑定不一致。');setCreated(body.id);setAck(false);}catch(e){setError(e instanceof Error?e.message:'生成失败');}finally{setBusy(false);}
 }
 const changed=original!==JSON.stringify(relations)||Boolean(reference&&reference!==originalRef),selectedRule=rules[draft.type_id];
 useUnsavedNavigation(!!hash&&!created&&(changed||Object.values(draft).some(Boolean)),'对象间关系');
 if(!target.space)return <p className="text-body-small text-muted-foreground">选择工程空间后可建立对象间关系。</p>;
 return <Card className="module-surface" aria-label="对象间关系"><CardHeader><div className="flex flex-wrap items-center justify-between gap-sm"><CardTitle>对象间关系</CardTitle><Button size="sm" variant="outline" disabled={busy||loading||reading} onClick={()=>setRevision(n=>n+1)}>重新载入关系</Button></div></CardHeader><CardContent className="flex min-w-0 flex-col gap-lg">
 <p className="text-body-small text-muted-foreground">以固定本体规则声明对象间关系，生成新候选后核对发布。关系仍待核实，连接不表示可通行。</p>
 <label className="flex flex-col gap-sm text-body-small">关系基础候选<NativeSelect aria-label="关系基础候选" value={base} disabled={busy||loading||reading} onChange={e=>setBase(e.target.value)}><option value="">请选择已有对象的候选</option>{jobs.map(j=><option key={j.id} value={j.id}>{j.id}</option>)}</NativeSelect></label>
 <label className="flex flex-col gap-sm text-body-small">固定关系本体<NativeSelect aria-label="关系本体版本" value={reference} disabled={busy||loading||reading} onChange={e=>setReference(e.target.value)}><option value="">请选择支持关系的固定版本</option>{versions.map(v=><option key={key(v)} value={key(v)}>{v.title} · V{v.version}</option>)}</NativeSelect></label>
 {!loading&&!versions.length&&<p className="text-body-small text-muted-foreground">尚无关系规则版本，请配置并封存关系词表。</p>}
 {(loading||reading)&&<p role="status" className="text-body-small">正在读取对象与关系快照…</p>}
 {hash&&<p className="break-all text-label-small text-muted-foreground">基础摘要：{hash} · {objects.length} 个固定对象</p>}
 {hash&&objects.length<2&&<p className="text-body-small text-muted-foreground">当前对象不足两个，请先在上方对象标注中准备需要关联的对象。</p>}
 {Object.keys(rules).length>0&&<><section aria-label="本次关系规则" className="flex flex-col gap-sm">{Object.entries(rules).map(([id,r])=><p key={id} className="text-label-small text-muted-foreground">{r.title} · {r.source_types.map(t=>typeTitles[t]||t).join('、')} → {r.target_types.map(t=>typeTitles[t]||t).join('、')} · {r.symmetric?'无向去重':'有向归属'}</p>)}<p className="text-label-small text-muted-foreground">包含与位于共用单一父空间、无环约束；反向等价关系只声明一次。</p></section>
 {objects.length>0&&<form onSubmit={add} className="flex min-w-0 flex-col gap-md border-t border-border pt-lg"><div className="grid grid-cols-1 gap-md sm:grid-cols-2"><label className="flex flex-col gap-sm text-body-small">关系ID<Input aria-label="关系ID" value={draft.relation_id} onChange={e=>setDraft({...draft,relation_id:e.target.value})} pattern="[a-zA-Z0-9][a-zA-Z0-9_.:\-]*" maxLength={160} required disabled={busy||Boolean(editing)}/></label><label className="flex flex-col gap-sm text-body-small">关系类型<NativeSelect aria-label="关系类型" value={draft.type_id} onChange={e=>setDraft({...draft,type_id:e.target.value,source_id:'',target_id:''})} required disabled={busy}><option value="">请选择关系</option>{Object.entries(rules).map(([id,r])=><option key={id} value={id}>{r.title}</option>)}</NativeSelect></label>{(['source_id','target_id'] as const).map((side,i)=><label key={side} className="flex flex-col gap-sm text-body-small">{i===0?'来源对象':'目标对象'}<NativeSelect aria-label={i===0?'关系来源对象':'关系目标对象'} value={draft[side]} onChange={e=>setDraft({...draft,[side]:e.target.value})} required disabled={busy||!selectedRule}><option value="">请选择对象</option>{objects.filter(o=>(i===0?selectedRule?.source_types:selectedRule?.target_types)?.includes(o.type_id)).map(o=><option key={o.object_id} value={o.object_id}>{o.properties.name||o.object_id} · {o.object_id}</option>)}</NativeSelect></label>)}</div><label className="flex flex-col gap-sm text-body-small">关联说明（待核实）<Input aria-label="关系说明" value={draft.note} onChange={e=>setDraft({...draft,note:e.target.value})} required maxLength={500} disabled={busy}/></label><div className="flex flex-wrap gap-sm"><Button type="submit" variant="outline" disabled={busy||(!editing&&relations.length>=200)}>{editing?'保存关系修订':'加入本次关系'}</Button>{editing&&<Button type="button" variant="ghost" onClick={()=>{setEditing('');setDraft(empty);}}>取消关系修订</Button>}</div></form>}
 <section aria-label="本次完整关系集" className="flex min-w-0 flex-col gap-md border-t border-border pt-lg"><p className="text-body-small font-medium">完整关系集 · {relations.length} 项</p>{!relations.length&&<p className="text-label-small text-muted-foreground">当前为空；提交空集合将在新候选中解除全部对象关系。</p>}{relations.map(r=><div key={r.relation_id} className="flex min-w-0 flex-wrap items-center justify-between gap-sm border-b border-border pb-md"><div className="min-w-0 break-all"><p className="text-body-small">{r.source_id} · {rules[r.type_id]?.title||r.type_id} · {r.target_id}</p><p className="text-label-small text-muted-foreground">{r.relation_id} · {r.note} · 待核实</p></div><div className="flex flex-wrap gap-sm"><Button size="sm" variant="outline" aria-label={`修订关系 ${r.relation_id}`} disabled={busy||Boolean(editing)} onClick={()=>{setDraft({...r});setEditing(r.relation_id);invalidate();}}>修订</Button><Button size="sm" variant="ghost" aria-label={`移除关系 ${r.relation_id}`} disabled={busy||Boolean(editing)} onClick={()=>{setRelations(current=>current.filter(item=>item.relation_id!==r.relation_id));invalidate();}}>移除</Button></div></div>)}</section>
 <Button className="self-start" variant="outline" disabled={busy||!hash||Boolean(editing)} onClick={validate}>校验完整关系集</Button>
 {report&&<section aria-label="关系校验结果"><StatusBadge tone={report.status==='passed'?'success':'danger'}>{report.status==='passed'?'关系规则校验通过':'关系规则校验未通过'}</StatusBadge>{report.issues.map((i,index)=><p key={index} className="mt-sm break-all text-body-small">{i.relation_id||i.object_id||'关系集'}：{i.message} <span className="text-label-small text-muted-foreground">{i.path}</span></p>)}</section>}
 <label className="flex items-center gap-sm text-body-small"><Switch aria-label="确认完整对象关系集" checked={ack} onCheckedChange={setAck} disabled={busy||!changed||report?.status!=='passed'||Boolean(editing)}/>确认完整关系集及本体版本；删除的关系会在新候选中解除，现场含义仍待核实</label>
 <Button className="self-start" disabled={busy||!hash||!changed||!ack||report?.status!=='passed'||Boolean(editing)} onClick={save}>{busy?'处理中…':'生成关系候选'}</Button></>}
 {error&&<p role="alert" className="break-all text-body-small">{error}</p>}
 {created&&<div role="status" className="flex flex-wrap gap-sm"><StatusBadge tone="success">关系候选已保存</StatusBadge><span className="break-all text-label-small">{created}</span><Button asChild size="sm"><a href={recordLink('build',{job:created})}>前往构建中心核对</a></Button><p className="w-full text-label-small text-muted-foreground">尚未选择或发布；几何和既有发布保持固定。</p></div>}
 </CardContent></Card>;
}
