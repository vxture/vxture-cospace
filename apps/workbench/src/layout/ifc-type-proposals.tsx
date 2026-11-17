import React,{useEffect,useRef,useState} from 'react';
import {Button,NativeSelect} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {checkedTypeProposals,type OntologyPin,type SourceType,type TypeProposals} from './ifc-type-proposal-contract';

type Version=OntologyPin&{title:string};
type Definition={record:OntologyPin;integrity:string;definition:{types:Record<string,{title:string}>}};
const versionKey=(v:OntologyPin)=>`${v.ontology_id}/${v.version}/${v.sha256}`;
export function IfcTypeProposals(props:Readonly<{space:string;pin:string;sources:SourceType[];selectedId?:string}>){
 const [open,setOpen]=useState(false);
 return <section className="flex flex-col gap-md"><Button variant="ghost" size="sm" className="self-start" aria-expanded={open} onClick={()=>setOpen(!open)}>本体类型提案{open?' · 收起':' · 配置'}</Button>{open&&<ProposalForm key={`${props.space}:${props.pin}`} {...props}/>}</section>;
}
function ProposalForm({space,pin,sources,selectedId}:Readonly<{space:string;pin:string;sources:SourceType[];selectedId?:string}>){
 const [versions,setVersions]=useState<Version[]>([]),[chosen,setChosen]=useState(''),[definition,setDefinition]=useState<Definition|null>(null);
 const [rules,setRules]=useState<Record<string,string>>({}),[result,setResult]=useState<TypeProposals|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const active=useRef<AbortController|null>(null);
 useEffect(()=>()=>active.current?.abort(),[]);
 useEffect(()=>{const controller=new AbortController();
  fetch(`${endpoint}/api/ontologies`,{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok){throw new Error('本体版本读取失败，请关闭后重试。');}
   const body=await r.json();
   if(!Array.isArray(body.ontologies))throw new Error('本体版本响应不完整。');
   return body.ontologies as Version[];
  }).then(v=>{if(!controller.signal.aborted)setVersions(v);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
  return()=>controller.abort();
 },[]);
 const current=versions.find(v=>versionKey(v)===chosen);
 useEffect(()=>{const controller=new AbortController();setDefinition(null);
  if(current)fetch(`${endpoint}/api/ontologies/${encodeURIComponent(current.ontology_id)}/${encodeURIComponent(current.version)}?${new URLSearchParams({sha256:current.sha256})}`,{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok){throw new Error('固定本体版本读取失败，请重新选择。');}
   const body=await r.json() as Definition;
   if(body.integrity!=='verified'||versionKey(body.record)!==chosen||!body.definition?.types){throw new Error('本体版本响应不一致。');}
   return body;
  }).then(v=>{if(!controller.signal.aborted)setDefinition(v);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
  return()=>controller.abort();
 },[current,chosen]);
 function invalidate(){active.current?.abort();setBusy(false);setResult(null);setError('');}
 async function propose(){
  if(!current||!definition)return;
  invalidate();const controller=new AbortController();active.current=controller;setBusy(true);
  const rows=Object.entries(rules).filter(([,target])=>target).map(([ifc_type,target_type_id])=>({ifc_type,target_type_id}));
  try{
   const response=await fetch(`${endpoint}/api/scene-ifc/type-proposals`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:space,catalog_sha256:pin,mapping:{profile:'cospace.ifc-ontology-mapping/0.1',ontology_ref:{ontology_id:current.ontology_id,version:current.version,sha256:current.sha256},rules:rows}})});
   if(!response.ok)throw new Error('提案生成失败，请检查权限、资料版本与本体规则。');
   const value=checkedTypeProposals(await response.json(),space,pin,current,sources,rules);
   if(!controller.signal.aborted)setResult(value);
  }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}
  finally{if(!controller.signal.aborted)setBusy(false);}
 }
 const types=[...new Set(sources.map(e=>e.ifc_type))].sort((a,b)=>a.localeCompare(b));
 const selected=result?.entities.find(e=>e.source_entity_id===selectedId);
 const ruleCount=Object.values(rules).filter(Boolean).length;
 function download(){
  if(!result)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`ifc-type-proposals-${result.mapping_sha256}.json`;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),0);
 }
 return <div className="flex flex-col gap-md">
  <p className="text-body-small text-muted-foreground">显式选择类型规则，仅生成提案；不保存关联或确认现场实例。</p>
  <label className="flex flex-col gap-xs text-body-small">固定本体版本<NativeSelect value={chosen} onChange={e=>{invalidate();setRules({});setChosen(e.target.value);}}><option value="">请选择本体版本</option>{versions.map(v=><option key={versionKey(v)} value={versionKey(v)}>{v.title} · {v.version}</option>)}</NativeSelect></label>
  {definition&&<><div className="grid grid-cols-1 md:grid-cols-2 gap-md">{types.map(type=><label key={type} className="flex flex-col gap-xs text-body-small">{type}<NativeSelect value={rules[type]||''} onChange={e=>{invalidate();setRules({...rules,[type]:e.target.value});}}><option value="">保留未映射</option>{Object.entries(definition.definition.types).map(([id,t])=><option key={id} value={id}>{t.title} · {id}</option>)}</NativeSelect></label>)}</div><Button variant="outline" size="sm" className="self-start" disabled={busy||ruleCount===0||ruleCount>100} onClick={()=>void propose()}>{busy?'正在生成…':'生成类型提案'}</Button>{ruleCount>100&&<p className="text-body-small">最多配置 100 条类型规则，请减少本次映射。</p>}</>}
  {error&&<p role="alert" className="text-body-small">{error}</p>}
  {result&&<div className="flex flex-col gap-xs text-body-small"><output>已生成 {result.proposed_count} 项类型提案 · {result.unmapped_count} 项未映射</output>{selected&&<p>当前构件：{selected.target_type_id?`${definition?.definition.types[selected.target_type_id]?.title||selected.target_type_id} · 待核验`:'未映射'}</p>}<p className="text-label-small text-muted-foreground">未保存 · 实例属性、空间连接与本体关系尚未核验</p><Button variant="ghost" size="sm" className="self-start" onClick={download}>导出提案</Button></div>}
 </div>;
}
