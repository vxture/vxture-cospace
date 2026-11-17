import React,{useEffect,useRef,useState} from 'react';
import {Button,Input,NativeSelect} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {checkedTypeProposals,type OntologyPin,type SourceType,type TypeProposals} from './ifc-type-proposal-contract';
import {MAX_MAPPING_FILE_BYTES,readMappingFile,mappingDocument,mappingFile,validateMappingTargets} from './ifc-mapping-file';

type Version=OntologyPin&{title:string};
type Definition={record:OntologyPin;integrity:string;definition:{types:Record<string,{title:string}>}};
const versionKey=(v:OntologyPin)=>`${v.ontology_id}/${v.version}/${v.sha256}`;
async function loadDefinition(version:OntologyPin,signal:AbortSignal){
 const path=`/api/ontologies/${encodeURIComponent(version.ontology_id)}/${encodeURIComponent(version.version)}`;
 const response=await fetch(`${endpoint}${path}?${new URLSearchParams({sha256:version.sha256})}`,{signal,cache:'no-store'});
 if(!response.ok)throw new Error('固定本体版本不可读取。');
 const body=await response.json() as Definition;
 if(body.integrity!=='verified'||!body.record||versionKey(body.record)!==versionKey(version)||!body.definition?.types)throw new Error('固定本体版本响应不一致。');
 return body;
}
export function IfcTypeProposals(props:Readonly<{space:string;pin:string;sources:SourceType[];selectedId?:string}>){
 const [open,setOpen]=useState(false);
 return <section className="flex flex-col gap-md"><Button variant="ghost" size="sm" className="self-start" aria-expanded={open} onClick={()=>setOpen(!open)}>本体类型提案{open?' · 收起':' · 配置'}</Button>{open&&<ProposalForm key={`${props.space}:${props.pin}`} {...props}/>}</section>;
}
function ProposalForm({space,pin,sources,selectedId}:Readonly<{space:string;pin:string;sources:SourceType[];selectedId?:string}>){
 const [versions,setVersions]=useState<Version[]>([]),[chosen,setChosen]=useState(''),[definition,setDefinition]=useState<Definition|null>(null);
 const [rules,setRules]=useState<Record<string,string>>({}),[result,setResult]=useState<TypeProposals|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [notice,setNotice]=useState('');
 const active=useRef<AbortController|null>(null);
 const loading=useRef<AbortController|null>(null);
 const readingFile=useRef<AbortController|null>(null);
 useEffect(()=>()=>{active.current?.abort();loading.current?.abort();readingFile.current?.abort();},[]);
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
 function invalidate(){active.current?.abort();loading.current?.abort();readingFile.current?.abort();setBusy(false);setResult(null);setError('');setNotice('');}
 async function selectVersion(key:string){
  invalidate();setChosen(key);setRules({});setDefinition(null);
  const version=versions.find(v=>versionKey(v)===key);
  if(!version)return;
  const controller=new AbortController();loading.current=controller;const {signal}=controller;
  try{const body=await loadDefinition(version,signal);if(!signal.aborted)setDefinition(body);}
  catch(e){if(!signal.aborted)setError((e as Error).message);}
 }
 async function importFile(file:File){
  readingFile.current?.abort();const controller=new AbortController();readingFile.current=controller;const {signal}=controller;
  setError('');setNotice('');
  try{
   if(file.size>MAX_MAPPING_FILE_BYTES)throw new Error('文件不能超过 8 MiB。');
   const data=await file.arrayBuffer();
   if(signal.aborted)return;
   const imported=readMappingFile(new TextDecoder('utf-8',{fatal:true}).decode(data),space,pin);
   if(signal.aborted)return;
   const version=versions.find(v=>versionKey(v)===versionKey(imported.ontology));
   if(!version)throw new Error('文件引用的固定本体版本当前不可见。');
   const body=await loadDefinition(version,signal);
   validateMappingTargets(imported.rules,body.definition.types);
   if(signal.aborted)return;
   invalidate();setChosen(versionKey(version));setDefinition(body);setRules(imported.rules);
   setNotice('已载入类型规则，请检查后重新生成提案。');
  }catch(e){if(!signal.aborted)setError((e as Error).message);}
 }
 async function propose(){
  if(!current||!definition)return;
  invalidate();const controller=new AbortController();active.current=controller;setBusy(true);
  try{
   const response=await fetch(`${endpoint}/api/scene-ifc/type-proposals`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:space,catalog_sha256:pin,mapping:mappingDocument(current,rules)})});
   if(!response.ok)throw new Error('提案生成失败，请检查权限、资料版本与本体规则。');
   const value=checkedTypeProposals(await response.json(),space,pin,current,sources,rules);
   if(!controller.signal.aborted)setResult(value);
  }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}
  finally{if(!controller.signal.aborted)setBusy(false);}
 }
 const sourceTypes=new Set(sources.map(e=>e.ifc_type));
 const types=[...new Set([...sourceTypes,...Object.keys(rules).filter(type=>rules[type])])].sort((a,b)=>a.localeCompare(b));
 const selected=result?.entities.find(e=>e.source_entity_id===selectedId);
 const ruleCount=Object.values(rules).filter(Boolean).length;
 function download(value:unknown,name:string){
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),0);
 }
 return <div className="flex flex-col gap-md">
  <p className="text-body-small text-muted-foreground">显式选择类型规则，仅生成提案；不保存关联或确认现场实例。</p>
  <label className="flex flex-col gap-xs text-body-small">载入映射配置或旧提案<Input type="file" accept=".json,application/json" disabled={versions.length===0||busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void importFile(file);}}/></label>
  {notice&&<output className="text-body-small">{notice}</output>}
  <label className="flex flex-col gap-xs text-body-small">固定本体版本<NativeSelect value={chosen} onChange={e=>void selectVersion(e.target.value)}><option value="">请选择本体版本</option>{versions.map(v=><option key={versionKey(v)} value={versionKey(v)}>{v.title} · {v.version}</option>)}</NativeSelect></label>
  {definition&&<><div className="grid grid-cols-1 md:grid-cols-2 gap-md">{types.map(type=><label key={type} className="flex flex-col gap-xs text-body-small">{type}{!sourceTypes.has(type)&&' · 当前目录无此类型'}<NativeSelect value={rules[type]||''} onChange={e=>{invalidate();setRules({...rules,[type]:e.target.value});}}><option value="">保留未映射</option>{Object.entries(definition.definition.types).map(([id,t])=><option key={id} value={id}>{t.title} · {id}</option>)}</NativeSelect></label>)}</div><Button variant="outline" size="sm" className="self-start" disabled={busy||ruleCount===0||ruleCount>100} onClick={()=>void propose()}>{busy?'正在生成…':'生成类型提案'}</Button>{ruleCount>100&&<p className="text-body-small">最多配置 100 条类型规则，请减少本次映射。</p>}</>}
  {error&&<p role="alert" className="text-body-small">{error}</p>}
  {definition&&current&&ruleCount>0&&ruleCount<=100&&<Button variant="ghost" size="sm" className="self-start" onClick={()=>download(mappingFile(space,pin,current,rules),`ifc-type-mapping-${pin}.json`)}>导出映射配置</Button>}
  {result&&<div className="flex flex-col gap-xs text-body-small"><output>已生成 {result.proposed_count} 项类型提案 · {result.unmapped_count} 项未映射</output>{selected&&<p>当前构件：{selected.target_type_id?`${definition?.definition.types[selected.target_type_id]?.title||selected.target_type_id} · 待核验`:'未映射'}</p>}<p className="text-label-small text-muted-foreground">未保存 · 实例属性、空间连接与本体关系尚未核验</p><Button variant="ghost" size="sm" className="self-start" onClick={()=>download(result,`ifc-type-proposals-${result.mapping_sha256}.json`)}>导出提案</Button></div>}
 </div>;
}
