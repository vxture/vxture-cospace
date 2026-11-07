import {useUnsavedNavigation} from './unsaved-navigation';
import {businessEndpoint} from './business-endpoint';
import React,{useEffect,useRef,useState} from 'react';
import {AnchorPicker} from './anchor-picker';
import {Button,Card,CardHeader,CardTitle,CardContent,NativeSelect,Input,StatusBadge} from '@vxture/design-system';
import {recordLink,useRecordNavigation} from './record-navigation';

const endpoint=businessEndpoint;
type Ref={ontology_id:string;version:string;sha256:string};
type Version=Ref&{title:string};
type Draft={object_id:string;type_id:string;properties:Record<string,string>;point_index:number};
type Rules={types:Record<string,{title:string;properties:Record<string,{title:string;required:boolean;min_length:number;max_length:number}>}>};
type Anchor={candidate_id:string;model_manifest_sha256:string;point_index:number;point_count:number;anchor_m:number[];frame_id:string};
const key=(ref:Ref)=>`${ref.ontology_id}/${ref.version}/${ref.sha256}`;
export function ObjectAnnotations(){
 const target=useRecordNavigation();
 return <ObjectAnnotationEditor key={target.space+'|'+target.job}/>;
}
function ObjectAnnotationEditor(){
 const target=useRecordNavigation();
 const [jobs,setJobs]=useState<{id:string;state:string}[]>([]),[versions,setVersions]=useState<Version[]>([]),[baseId,setBaseId]=useState(''),[refKey,setRefKey]=useState(''),[rules,setRules]=useState<Rules|null>(null);
 const [base,setBase]=useState<Anchor|null>(null),[anchor,setAnchor]=useState<Anchor|null>(null),[index,setIndex]=useState('0'),[identity,setIdentity]=useState(''),[typeId,setTypeId]=useState(''),[properties,setProperties]=useState<Record<string,string>>({}),[objects,setObjects]=useState<Draft[]>([]);
 const [editing,setEditing]=useState(''),[original,setOriginal]=useState('[]');
 const generation=useRef(0),anchorRequest=useRef<AbortController|null>(null),saving=useRef(false);
 useEffect(()=>()=>{generation.current++;anchorRequest.current?.abort();},[]);
 const [busy,setBusy]=useState(false),[reading,setReading]=useState(false),[error,setError]=useState(''),[created,setCreated]=useState<{id:string;candidate_url:string}|null>(null);
 useUnsavedNavigation(!!base&&!created&&(JSON.stringify(objects)!==original||!!identity||!!editing),'对象标注');
 useEffect(()=>{
  if(!target.space)return;const controller=new AbortController();setError('');
  Promise.all([fetch(`${endpoint}/api/builds?space_id=${target.space}`,{signal:controller.signal}),fetch(`${endpoint}/api/ontologies`,{signal:controller.signal}),fetch(`${endpoint}/api/selection?space_id=${target.space}`,{signal:controller.signal})]).then(async responses=>{
   if(responses.some(r=>!r.ok))throw Error('对象工作面读取失败，请检查空间、候选和本体规则库。');
   const [j,o,s]=await Promise.all(responses.map(r=>r.json()));if(controller.signal.aborted)return;
   const available=j.jobs.filter((job:{state:string})=>job.state==='succeeded');setJobs(available);setVersions(o.ontologies);
   setBaseId(available.some((job:{id:string})=>job.id===target.job)?target.job:s.candidate_id||'');
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[target.space,target.job]);
 useEffect(()=>{
  const controller=new AbortController();generation.current++;anchorRequest.current?.abort();setBase(null);setAnchor(null);setObjects([]);setOriginal('[]');setCreated(null);setIndex('0');setIdentity('');setEditing('');setError('');
  if(!baseId){setReading(false);return()=>controller.abort();}setReading(true);
  fetch(`${endpoint}/candidates/${baseId}/api/anchor?point_index=0`,{signal:controller.signal}).then(async a=>{
   if(!a.ok)throw Error('模型锚点读取失败。');const info=await a.json();if(controller.signal.aborted)return;
   if(info.candidate_id!==baseId)throw Error('基础候选响应不一致。');setBase(info);
   if(info.has_semantic_objects){const o=await fetch(`${endpoint}/candidates/${baseId}/api/objects`,{signal:controller.signal});if(!o.ok)throw Error('已有对象快照无法读取。');const existing=await o.json();if(controller.signal.aborted)return;setRefKey(key(existing.ontology_ref));const saved=existing.objects.map((obj:{object_id:string;type_id:string;properties:Record<string,string>;evidence:{point_index:number}})=>({object_id:obj.object_id,type_id:obj.type_id,properties:obj.properties,point_index:obj.evidence.point_index}));setObjects(saved);setOriginal(JSON.stringify(saved));}
  }).catch(e=>{if(!controller.signal.aborted){setBase(null);setError(e.message);}}).finally(()=>{if(!controller.signal.aborted)setReading(false);});return()=>controller.abort();
 },[baseId]);
 useEffect(()=>{
  const controller=new AbortController();setRules(null);setTypeId('');setProperties({});
  const ref=versions.find(v=>key(v)===refKey);if(!ref)return()=>controller.abort();
  fetch(`${endpoint}/api/ontologies/${ref.ontology_id}/${ref.version}?sha256=${ref.sha256}`,{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('固定本体规则无法读取。');return r.json();}).then(body=>{if(!controller.signal.aborted)setRules(body.definition);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[refKey,versions]);
 async function readAnchor(selected=Number(index)){
  if(!base||!Number.isSafeInteger(selected)||selected<0||selected>=base.point_count)return;
  const run=generation.current,controller=new AbortController();anchorRequest.current?.abort();anchorRequest.current=controller;
  setIndex(String(selected));setReading(true);setError('');setAnchor(null);
  try{const r=await fetch(`${endpoint}/candidates/${baseId}/api/anchor?point_index=${selected}`,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('点索引超出模型范围或候选不可读。');const value=await r.json();if(value.candidate_id!==baseId||value.point_index!==selected||value.frame_id!==base.frame_id||value.model_manifest_sha256!==base.model_manifest_sha256)throw Error('基础模型已变化，请重新选择候选。');if(run===generation.current&&!controller.signal.aborted)setAnchor(value);}catch(e){if(run===generation.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'锚点读取失败');}finally{if(run===generation.current&&!controller.signal.aborted)setReading(false);}
 }
 function add(e:React.FormEvent){
  e.preventDefault();if(!anchor||!rules||!typeId)return;setError('');setCreated(null);
  if(objects.some(o=>o.object_id===identity.trim()&&o.object_id!==editing)){setError('本次标注中对象ID已存在，请使用稳定且唯一的ID。');return;}
  const values=Object.fromEntries(Object.entries(properties).filter(([,value])=>value!==''));
  const draft={object_id:identity.trim(),type_id:typeId,properties:values,point_index:anchor.point_index};
  setObjects(current=>editing?current.map(obj=>obj.object_id===editing?draft:obj):[...current,draft]);setIdentity('');setEditing('');setAnchor(null);
 }
 async function save(){
  const ref=versions.find(v=>key(v)===refKey);if(!ref||!base||!objects.length||saving.current)return;const run=generation.current;saving.current=true;setBusy(true);setError('');setCreated(null);
  try{const r=await fetch(`${endpoint}/api/semantic-candidates`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:target.space,base_candidate_id:baseId,base_manifest_sha256:base.model_manifest_sha256,ontology_ref:{ontology_id:ref.ontology_id,version:ref.version,sha256:ref.sha256},objects})});const body=await r.json();if(!r.ok){const detail=body.detail;if(detail?.issues)throw Error(detail.issues.map((issue:{object_id:string;path:string;message:string})=>`${issue.object_id} ${issue.path}：${issue.message}`).join('；'));throw Error(`生成失败：${typeof detail==='string'?detail:'请检查字段、锚点和固定引用。'}`);}if(run===generation.current)setCreated(body);}catch(e){if(run===generation.current)setError(e instanceof Error?e.message:'生成失败');}finally{saving.current=false;if(run===generation.current)setBusy(false);}
 }
 if(!target.space)return <p className="text-body-small text-muted-foreground">选择工程空间后可建立对象标注候选。</p>;
 return <Card className="module-surface" aria-label="对象标注工作面"><CardHeader><CardTitle>对象标注</CardTitle></CardHeader><CardContent className="flex flex-col gap-lg">
  <p className="text-body-small text-muted-foreground">在固定模型上人工标注，生成独立新候选。锚点来自真实模型；对象类型和名称仍待现场核实。</p>
  <label htmlFor="annotation-base" className="text-body-small">基础候选</label><NativeSelect id="annotation-base" aria-label="标注基础候选" value={baseId} onChange={e=>setBaseId(e.target.value)} disabled={busy||reading}><option value="">请选择已有候选</option>{jobs.map(job=><option key={job.id} value={job.id}>{job.id}</option>)}</NativeSelect>
  <label htmlFor="annotation-ontology" className="text-body-small">固定本体版本</label><NativeSelect id="annotation-ontology" aria-label="标注本体版本" value={refKey} onChange={e=>{setRefKey(e.target.value);setCreated(null);setEditing('');setIdentity('');setAnchor(null);}} disabled={busy}><option value="">请选择规则版本</option>{versions.map(v=><option key={key(v)} value={key(v)}>{v.title} · V{v.version}</option>)}</NativeSelect>
  {base&&<p className="break-all text-label-small text-muted-foreground">坐标：{base.frame_id} · 米 · {base.point_count.toLocaleString()} 个模型点 · 基础摘要 {base.model_manifest_sha256}</p>}
  {base&&rules&&<form onSubmit={add} className="flex flex-col gap-md border-t border-border pt-lg">
   <div className="grid grid-cols-1 gap-md md:grid-cols-2"><div className="flex flex-col gap-sm"><label htmlFor="object-id">对象ID</label><Input id="object-id" aria-label="标注对象ID" value={identity} onChange={e=>setIdentity(e.target.value)} placeholder="object-001" maxLength={160} pattern="[a-zA-Z0-9][a-zA-Z0-9_.:\-]*" required disabled={busy||Boolean(editing)}/></div><div className="flex flex-col gap-sm"><label htmlFor="object-type">类型</label><NativeSelect id="object-type" aria-label="标注对象类型" value={typeId} onChange={e=>{setTypeId(e.target.value);setProperties({});}} required disabled={busy}><option value="">请选择本体类型</option>{Object.entries(rules.types).map(([id,type])=><option key={id} value={id}>{type.title} · {id}</option>)}</NativeSelect></div></div>
   {Object.entries(rules.types[typeId]?.properties||{}).map(([name,rule])=><div key={name} className="flex flex-col gap-sm"><label htmlFor={`object-property-${name}`}>{rule.title}{rule.required?'（必填）':'（选填）'}</label><Input id={`object-property-${name}`} aria-label={`标注属性 ${name}`} value={properties[name]||''} onChange={e=>setProperties({...properties,[name]:e.target.value})} required={rule.required} minLength={rule.min_length} maxLength={rule.max_length} disabled={busy}/></div>)}
   <AnchorPicker endpoint={endpoint} space={target.space} candidate={baseId} manifest={base.model_manifest_sha256} onPick={i=>void readAnchor(i)} disabled={busy||reading}/><details><summary>按模型索引选择（备用）</summary><div className="flex flex-wrap items-end gap-sm"><div className="flex flex-col gap-sm"><label htmlFor="object-point-index">模型点索引</label><Input id="object-point-index" aria-label="标注模型点索引" type="number" step="1" min="0" max={base.point_count-1} value={index} onChange={e=>{setIndex(e.target.value);setAnchor(null);}} disabled={busy||reading}/></div><Button type="button" variant="outline" onClick={()=>void readAnchor()} disabled={busy||reading||index===''}>读取锚点</Button><Button asChild type="button" variant="ghost"><a href={`${endpoint}/candidates/${encodeURIComponent(baseId)}/`} target="_blank" rel="noopener noreferrer">查看基础模型</a></Button></div></details>
   {anchor&&<p className="text-body-small text-muted-foreground">锚点 [{anchor.anchor_m.map(v=>v.toFixed(4)).join(', ')}] 米 · 证据：spatial.npz 第 {anchor.point_index} 点 · 语义待核实</p>}
   <Button type="submit" className="self-start" variant="outline" disabled={busy||reading||!anchor||!typeId||(!editing&&objects.length>=100)}>{editing?'保存本次修订':'加入本次标注'}</Button>{editing&&<Button type="button" variant="ghost" className="self-start" onClick={()=>{setEditing('');setIdentity('');setAnchor(null);}}>取消对象修订</Button>}
  </form>}
  {objects.length>0&&<section aria-label="本次对象标注" className="flex flex-col gap-md border-t border-border pt-lg"><p className="text-body-small font-medium">本次完整标注集 · {objects.length} 个对象</p>{objects.map(obj=><div key={obj.object_id} className="flex flex-wrap items-center justify-between gap-sm border-b border-border pb-sm"><div className="min-w-0 break-all"><p className="text-body-small">{obj.properties.name||obj.object_id} · {obj.object_id}</p><p className="text-label-small text-muted-foreground">{obj.type_id} · 点 {obj.point_index} · 待核实</p></div><div className="flex flex-wrap gap-sm"><Button aria-label={`修订 ${obj.object_id}`} size="sm" variant="outline" disabled={busy||Boolean(editing)} onClick={()=>{setEditing(obj.object_id);setIdentity(obj.object_id);setTypeId(obj.type_id);setProperties({...obj.properties});setIndex(String(obj.point_index));setAnchor(null);setCreated(null);}}>修订</Button><Button aria-label={`移除 ${obj.object_id}`} size="sm" variant="ghost" disabled={busy||Boolean(editing)} onClick={()=>{setObjects(items=>items.filter(o=>o.object_id!==obj.object_id));setCreated(null);}}>移除</Button></div></div>)}</section>}
  {error&&<p role="alert" className="whitespace-pre-wrap text-body-small">{error}</p>}
  <Button className="self-start" disabled={busy||reading||!base||!rules||!objects.length||Boolean(editing)} onClick={save}>{busy?'生成中…':'生成标注候选'}</Button>
  {created&&<div role="status" className="flex flex-wrap items-center gap-sm"><StatusBadge tone="success">标注候选已保存</StatusBadge><span className="text-label-small">{created.id}</span><Button asChild size="sm" variant="outline"><a href={`${endpoint}${created.candidate_url}`} target="_blank" rel="noopener noreferrer">查看对象与双视图</a></Button><Button asChild size="sm"><a href={recordLink('build',{job:created.id})}>前往构建中心核对</a></Button><p className="w-full text-label-small text-muted-foreground">尚未选择或发布；几何未重新估计，所有对象保留待核实状态。</p></div>}
 </CardContent></Card>;
}
