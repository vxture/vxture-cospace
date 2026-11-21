import React,{useEffect,useRef,useState} from 'react';
import {Button,Drawer,Input,NativeSelect} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink} from './record-navigation';
import './publication-semantics.css';

export type SemanticSelection={consumer_revision:number;source_manifest_sha256:string;snapshot_sha256:string};
export type RegistrationSelection={registration_revision:number;source_manifest_sha256:string;snapshot_sha256:string};
type Coverage={objects_total:number;linked_objects:number;unlinked_objects:number;relations_total:number;mapped_relations:number;unmapped_relations:number};
type Check={semantic_selection:SemanticSelection;coverage:Coverage;mapped_relation_validation:string};
async function value(response:Response){
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const messages:Record<string,string>={semantic_attributes_invalid:'实例属性校验未通过，请先在空间关联中修正。',semantic_relations_invalid:'已映射关系校验未通过，请先修正。',semantic_evidence_missing:'声明依据尚未填写完整。',link_revision_not_found:'该固定修订不存在。',link_source_changed:'模型来源已变化，请重新打开面板。',semantic_definition_conflict:'固定定义存在版本冲突。',invalid_query_time:'请输入合法的 UTC 时刻，例如 2026-11-20T00:00:00Z。'};
  throw Error(response.status===403?'当前身份无权执行此操作。':messages[data.detail]||'成果暂不可用，请核对来源后重试。');}
 return data;
}
function CoverageRows({coverage}:{coverage:Coverage}){return <dl className="publication-semantic-metrics"><div><dt>对象声明</dt><dd>{coverage.linked_objects} / {coverage.objects_total}</dd></div><div><dt>关系映射</dt><dd>{coverage.mapped_relations} / {coverage.relations_total}</dd></div></dl>;}

export function PublicationPrepare({spaceId,selection,onClose,onProceed}:{spaceId:string;selection:{candidate_id:string|null;revision:number};onClose:()=>void;onProceed:(semantic?:SemanticSelection,registration?:RegistrationSelection)=>void}){
 const [include,setInclude]=useState(false),[revision,setRevision]=useState(''),[source,setSource]=useState('');
 const [loading,setLoading]=useState(true),[checking,setChecking]=useState(false),[error,setError]=useState(''),[check,setCheck]=useState<Check|null>(null);
 const generation=useRef(0),[refresh,setRefresh]=useState(0),mounted=useRef(true);
 const [includeRegistration,setIncludeRegistration]=useState(false),[registration,setRegistration]=useState<RegistrationSelection|null>(null),[registrationError,setRegistrationError]=useState(''),[registrationLoading,setRegistrationLoading]=useState(false);
 useEffect(()=>{const abort=new AbortController();setRegistration(null);setRegistrationError('');setRegistrationLoading(includeRegistration);
  if(!includeRegistration||!selection.candidate_id)return()=>abort.abort();
  (async()=>{const state=await fetch(endpoint+'/api/scene-registrations?'+new URLSearchParams({space_id:spaceId,candidate_id:selection.candidate_id!}),{signal:abort.signal,cache:'no-store'}).then(value);
   if(!state.adopted_revision)throw Error('当前模型尚未采用核准配准，请先在空间基准中完成审核采用。');
   const result=await fetch(endpoint+'/api/publication-registration-preflight',{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:spaceId,candidate_id:selection.candidate_id,registration_selection:{registration_revision:state.adopted_revision,source_manifest_sha256:state.source_sha256}})}).then(value);
   if(!abort.signal.aborted)setRegistration(result.registration_selection);
  })().catch(e=>{if(!abort.signal.aborted)setRegistrationError(e.message);}).finally(()=>{if(!abort.signal.aborted)setRegistrationLoading(false);});return()=>abort.abort();
 },[includeRegistration,spaceId,selection.candidate_id]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;};},[]);
 useEffect(()=>{const abort=new AbortController();generation.current++;setChecking(false);setLoading(true);setCheck(null);setError('');setSource('');
  if(!include||!selection.candidate_id){setLoading(false);return;}
  fetch(endpoint+'/api/scene-ontology-links?'+new URLSearchParams({space_id:spaceId,candidate_id:selection.candidate_id}),{cache:'no-store',signal:abort.signal}).then(value).then(data=>{
   if(data.space_id!==spaceId||data.candidate_id!==selection.candidate_id||!Number.isSafeInteger(data.revision)||data.revision<0||!/^[a-f0-9]{64}$/.test(data.source_sha256))throw Error('实例来源与待发布候选不一致。');
   if(!abort.signal.aborted){setSource(data.source_sha256);setRevision(String(data.revision));}
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});return()=>abort.abort();
 },[spaceId,selection.candidate_id,include,refresh]);
 function changeRevision(text:string){generation.current++;setChecking(false);setRevision(text);setCheck(null);setError('');}
 async function preflight(){const seq=++generation.current;setCheck(null);setError('');const number=Number(revision);
  if(!/^[1-9][0-9]*$/.test(revision)||!Number.isSafeInteger(number)){setError('请选择已有的正整数实例修订。');return;}
  setChecking(true);try{const data:Check=await fetch(endpoint+'/api/publication-semantic-preflight',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:spaceId,candidate_id:selection.candidate_id,semantic_selection:{consumer_revision:number,source_manifest_sha256:source}})}).then(value);
   if(data.semantic_selection.consumer_revision!==number||data.semantic_selection.source_manifest_sha256!==source||!/^[a-f0-9]{64}$/.test(data.semantic_selection.snapshot_sha256))throw Error('预检结果与所选修订不一致。');
   if(mounted.current&&generation.current===seq)setCheck(data);
  }catch(e){if(mounted.current&&generation.current===seq)setError(e instanceof Error?e.message:'预检失败。');}finally{if(mounted.current&&generation.current===seq)setChecking(false);}}
 return <Drawer open side="right" width="md" title="新建发布" description="核对固定来源及本次成果范围" onClose={onClose} closeLabel="关闭发布准备" footer={<div className="publication-semantic-footer"><Button variant="outline" onClick={onClose}>取消</Button><Button disabled={!selection.candidate_id||include&&(!check||checking||loading)||includeRegistration&&(!registration||registrationLoading)} onClick={()=>onProceed(include?check!.semantic_selection:undefined,includeRegistration?registration!:undefined)}>继续发布</Button></div>}><div className="publication-semantic-content">
 <section><h4>固定空间成果</h4><p>{selection.candidate_id||'尚未选择候选'}</p><p>选择修订 {selection.revision} · 沿用已有模型与表达。</p></section>
 <section><label className="publication-semantic-choice"><input type="checkbox" checked={include} onChange={e=>setInclude(e.target.checked)}/>纳入对象语义成果</label><p>冻结所选实例修订、定义闭包、对象属性、关系及依据。</p>
 {include&&<>{loading?<output>正在读取实例来源…</output>:source?<><form className="publication-semantic-toolbar" onSubmit={e=>{e.preventDefault();void preflight();}}><Input aria-label="固定实例修订" value={revision} inputMode="numeric" onChange={e=>changeRevision(e.target.value)}/><Button variant="outline" type="submit" disabled={checking}>{checking?'预检中…':'预检修订'}</Button></form>{revision==='0'&&<p>当前候选尚无实例声明，请先在空间关联中维护。</p>}</>:null}
 {error&&<p role="alert">{error}<Button variant="ghost" size="sm" onClick={()=>{generation.current++;setChecking(false);setRefresh(n=>n+1);}}>重新读取</Button></p>}
 {check&&<><CoverageRows coverage={check.coverage}/><p>实例修订 {check.semantic_selection.consumer_revision} · 属性校验通过（局部）</p><p>{check.mapped_relation_validation==='not_applicable'?'未采用关系映射，关系校验不适用。':'已映射关系校验通过（局部）。'}</p></>}</>}
 </section><section><label className="publication-semantic-choice"><input type="checkbox" checked={includeRegistration} onChange={event=>setIncludeRegistration(event.target.checked)}/>纳入核准配准成果</label><p>显式固定当前采用的核准修订、基准依据和地理适配资料，在线与离线共用。</p>{registrationLoading&&<output>正在预检核准修订…</output>}{registrationError&&<p role="alert">{registrationError}{selection.candidate_id&&<Button asChild size="sm" variant="ghost"><a href={recordLink('registration',{space:spaceId,job:selection.candidate_id})}>前往空间基准</a></Button>}</p>}{registration&&<p>核准修订 {registration.registration_revision} · 已预检</p>}</section><section><h4>交付边界</h4><p>未引用对象和未映射关系不自动补齐。配准核准不替代独立现场精度验收。</p><p>模型与附件为证据引用；本次成果不提供机器人导航或任务执行能力。</p></section></div></Drawer>;
}

type Summary={profile:string;publication_id:string;state:string;revision:number;coverage:Coverage;objects:{object_id:string;name:string}[]};
type Claim={definition:{title:string;definition:string;effective_properties:Record<string,{title:string}>};instance_properties?:Record<string,{value:string|number|boolean;unit?:string}>;evidence_note?:string;time_state:string};
type ObjectView={profile:string;publication_id:string;object_id:string;at:string|null;revision:number;claim:Claim|null;relations:{relation_id:string;source_id:string;target_id:string;definition:{title:string};time_state:string}[]};
const timeLabels:Record<string,string>={active:'该时刻有效',inactive:'该时刻无效',not_recorded:'有效期未记录',not_filtered:'未按时刻筛选'};
export function PublicationSemantics({publicationId}:{publicationId:string}){
 const [summary,setSummary]=useState<Summary|null>(null),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[loading,setLoading]=useState(true);
 const [object,setObject]=useState(''),[time,setTime]=useState(''),[query,setQuery]=useState<{object:string;at:string}|null>(null),[result,setResult]=useState<ObjectView|null>(null),[queryError,setQueryError]=useState(''),[querying,setQuerying]=useState(false);
 const url=endpoint+`/publications/${encodeURIComponent(publicationId)}/api/semantics`;
 useEffect(()=>{const abort=new AbortController();setSummary(null);setError('');setResult(null);setQuery(null);setLoading(true);
  fetch(url,{cache:'no-store',signal:abort.signal}).then(value).then((data:Summary)=>{if(data.profile!=='cospace.publication-semantics/0.1'||data.publication_id!==publicationId||!['included','not_included'].includes(data.state))throw Error('成果与当前发布版本不一致。');if(!abort.signal.aborted){setSummary(data);setObject(data.objects[0]?.object_id||'');}}).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});return()=>abort.abort();
 },[url,publicationId,refresh]);
 useEffect(()=>{if(!query)return;const abort=new AbortController();setResult(null);setQueryError('');setQuerying(true);const params=new URLSearchParams({object_id:query.object});if(query.at)params.set('at',query.at);
  fetch(url+'?'+params,{cache:'no-store',signal:abort.signal}).then(value).then((data:ObjectView)=>{if(data.profile!=='cospace.publication-semantic-object/0.1'||data.publication_id!==publicationId||data.object_id!==query.object||data.at!==(query.at||null)||data.revision!==summary?.revision)throw Error('查询结果与固定成果不一致。');if(!abort.signal.aborted)setResult(data);}).catch(e=>{if(!abort.signal.aborted)setQueryError(e.message);}).finally(()=>{if(!abort.signal.aborted)setQuerying(false);});return()=>abort.abort();
 },[url,publicationId,query,summary?.revision]);
 return <section className="publication-semantic-section" aria-label="对象语义成果"><h4>对象语义成果</h4>{loading&&<output>正在读取固定成果…</output>}{error&&<p role="alert">{error}<Button variant="ghost" size="sm" onClick={()=>setRefresh(n=>n+1)}>重试</Button></p>}
 {summary?.state==='not_included'&&<p>此发布未纳入对象语义成果。</p>}
 {summary?.state==='included'&&<><p>固定实例修订 {summary.revision}</p><CoverageRows coverage={summary.coverage}/><form className="publication-semantic-toolbar" onSubmit={e=>{e.preventDefault();setQuery({object,at:time.trim()});}}><NativeSelect aria-label="查询成果对象" value={object} onChange={e=>{setObject(e.target.value);setResult(null);setQuery(null);}}>{summary.objects.map(item=><option key={item.object_id} value={item.object_id}>{item.name}</option>)}</NativeSelect><Input aria-label="成果查询 UTC 时刻" placeholder="UTC 时刻（可选）" value={time} maxLength={40} onChange={e=>setTime(e.target.value)}/><Button type="submit" variant="outline" disabled={!object||querying}>查询</Button></form>
 {querying&&<output>正在查询固定成果…</output>}{queryError&&<p role="alert">{queryError}</p>}{result&&<div className="publication-semantic-result"><h4>{result.claim?.definition.title||'此对象未纳入本体声明'}</h4>{result.claim&&<><p>{result.claim.definition.definition}</p><p>{timeLabels[result.claim.time_state]||result.claim.time_state}</p><dl>{Object.entries(result.claim.instance_properties||{}).map(([id,property])=><div key={id}><dt>{result.claim!.definition.effective_properties[id]?.title||id}</dt><dd>{String(property.value)} {property.unit||''}</dd></div>)}</dl><p>{result.claim.evidence_note}</p></>}{result.relations.map(item=><p key={item.relation_id}>{item.definition.title} · {item.source_id} → {item.target_id} · {timeLabels[item.time_state]||item.time_state}</p>)}</div>}
 <p className="text-muted-foreground">声明与定义已冻结；模型及附件为外部证据引用。局部校验不替代专业审核与现场核实。</p></>}
 </section>;
}
