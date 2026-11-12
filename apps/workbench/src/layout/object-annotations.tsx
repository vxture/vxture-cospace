import {candidateScreenHref} from './real-space-data';
import {associationExample} from './association-examples';
import {useUnsavedNavigation,runGuarded} from './unsaved-navigation';
import {businessEndpoint} from './business-endpoint';
import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Plus,DotsThreeVertical,MapPin,PencilSimple,Trash,X,Selection} from '@phosphor-icons/react';
import {AnchorPicker} from './anchor-picker';
import type {XYZ} from './geometry-preview-data';
import type {GeometryFocus} from './geometry-preview-canvas';
import {Button,Card,CardHeader,CardTitle,CardContent,NativeSelect,Input,StatusBadge,Table,TableHeader,TableBody,TableRow,TableHead,TableCell,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter} from '@vxture/design-system';
import {recordLink,useRecordNavigation} from './record-navigation';

const endpoint=businessEndpoint;
type Ref={ontology_id:string;version:string;sha256:string};
type Version=Ref&{title:string;version_code?:string};
type Draft={object_id:string;type_id:string;properties:Record<string,string>;point_index:number;anchor_m:XYZ};
type Rules={types:Record<string,{title:string;properties:Record<string,{title:string;required:boolean;min_length:number;max_length:number}>}>};
type Anchor={candidate_id:string;model_manifest_sha256:string;point_index:number;point_count:number;anchor_m:XYZ;frame_id:string;space_id:string;source_model_sha256:string};
const key=(ref:Ref)=>`${ref.ontology_id}/${ref.version}/${ref.sha256}`;
export function ObjectAnnotations({embedded=false,active=true}:{embedded?:boolean;active?:boolean}={}){
 const target=useRecordNavigation();
 return <ObjectAnnotationEditor key={target.space+'|'+target.job} embedded={embedded} active={active}/>;
}
function ObjectAnnotationEditor({embedded,active}:{embedded:boolean;active:boolean}){
 const target=useRecordNavigation();
 const example=associationExample(new URLSearchParams(window.location.search).get('example'));
 const [jobs,setJobs]=useState<{id:string;state:string}[]>([]),[versions,setVersions]=useState<Version[]>([]),[baseId,setBaseId]=useState(''),[refKey,setRefKey]=useState(''),[rules,setRules]=useState<Rules|null>(null);
 const [base,setBase]=useState<Anchor|null>(null),[anchor,setAnchor]=useState<Anchor|null>(null),[index,setIndex]=useState('0'),[identity,setIdentity]=useState(''),[typeId,setTypeId]=useState(''),[properties,setProperties]=useState<Record<string,string>>({}),[objects,setObjects]=useState<Draft[]>([]);
 const [editing,setEditing]=useState(''),[original,setOriginal]=useState('[]'),[originalRef,setOriginalRef]=useState('');
 const [formOpen,setFormOpen]=useState(false),[search,setSearch]=useState(''),[typeFilter,setTypeFilter]=useState(''),[removing,setRemoving]=useState<Draft|null>(null),[location,setLocation]=useState<Draft|null>(null);
 const [selected,setSelected]=useState(''),[focus,setFocus]=useState<GeometryFocus>();
 const workArea=useRef<HTMLDivElement>(null);
 const current=objects.find(o=>o.object_id===selected);
 const markers=useMemo(()=>objects.map(o=>({id:o.object_id,label:o.properties.name||o.object_id,position:o.anchor_m})),[objects]);
 function selectObject(obj:Draft,scroll=false){setSelected(obj.object_id);setFocus({position:obj.anchor_m});if(scroll)workArea.current?.scrollIntoView({block:'nearest'});}
 const [dependencies,setDependencies]=useState<{relations:{source_id:string;target_id:string}[];business:string[]}>({relations:[],business:[]});
 const changed=JSON.stringify(objects)!==original||refKey!==originalRef;
 function startObject(obj?:Draft){if(obj)selectObject(obj);else{setSelected('');setFocus(undefined);}setEditing(obj?.object_id||'');setIdentity(obj?.object_id||'object-'+crypto.randomUUID().slice(0,8));setTypeId(obj?.type_id||'');setProperties(obj?{...obj.properties}:{});setIndex(String(obj?.point_index||0));setAnchor(null);setCreated(null);setFormOpen(true);workArea.current?.scrollIntoView({block:'nearest'});if(obj)void readAnchor(obj.point_index);}
 function startExampleObject(item:{id:string;name:string;type:string}){
  if(!rules?.types[item.type]||!rules.types[item.type].properties.name)return;
  startObject();setIdentity('example-'+item.id);setTypeId(item.type);setProperties({name:item.name});
 }
 function closeForm(){setEditing('');setIdentity('');setProperties({});setAnchor(null);setFormOpen(false);}

 const generation=useRef(0),anchorRequest=useRef<AbortController|null>(null),saving=useRef(false);
 useEffect(()=>()=>{generation.current++;anchorRequest.current?.abort();},[]);
 const [busy,setBusy]=useState(false),[reading,setReading]=useState(false),[error,setError]=useState(''),[created,setCreated]=useState<{id:string;candidate_url:string}|null>(null);
 useUnsavedNavigation(!!base&&!created&&(changed||!!identity||!!editing),'对象标注',{discard:()=>{setObjects(JSON.parse(original));setIdentity('');setEditing('');setAnchor(null);setProperties({});setRefKey(originalRef);setFormOpen(false);}});
 useEffect(()=>{
  if(!target.space)return;const controller=new AbortController();setError('');
  (async()=>{
   if(embedded){const response=await fetch(`${endpoint}/api/ontologies`,{signal:controller.signal});if(!response.ok)throw Error('本体规则暂时无法读取。');const o=await response.json();if(!controller.signal.aborted){setVersions(o.ontologies);setBaseId(target.job);}return;}
   const responses=await Promise.all([fetch(`${endpoint}/api/builds?space_id=${target.space}`,{signal:controller.signal}),fetch(`${endpoint}/api/ontologies`,{signal:controller.signal}),fetch(`${endpoint}/api/selection?space_id=${target.space}`,{signal:controller.signal})]);
   if(responses.some(r=>!r.ok))throw Error('对象工作面读取失败，请检查空间、候选和本体规则库。');
   const [j,o,selected]=await Promise.all(responses.map(r=>r.json()));if(controller.signal.aborted)return;
   const available=j.jobs.filter((job:{state:string})=>job.state==='succeeded');setJobs(available);setVersions(o.ontologies);setBaseId(available.some((job:{id:string})=>job.id===target.job)?target.job:selected.candidate_id||'');
  })().catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[target.space,target.job,embedded]);
 useEffect(()=>{
  const controller=new AbortController();generation.current++;anchorRequest.current?.abort();setBase(null);setAnchor(null);setObjects([]);setOriginal('[]');setOriginalRef('');setFormOpen(false);setDependencies({relations:[],business:[]});setSelected('');setFocus(undefined);setCreated(null);setIndex('0');setIdentity('');setEditing('');setError('');
  if(!baseId){setReading(false);return()=>controller.abort();}setReading(true);
  fetch(`${endpoint}/candidates/${baseId}/api/anchor?point_index=0`,{signal:controller.signal}).then(async a=>{
   if(!a.ok)throw Error('模型锚点读取失败。');const info=await a.json();if(controller.signal.aborted)return;
   if(info.candidate_id!==baseId||info.space_id!==target.space)throw Error('基础候选响应不一致。');setBase(info);
   if(info.has_semantic_objects){const o=await fetch(`${endpoint}/candidates/${baseId}/api/objects`,{signal:controller.signal});if(!o.ok)throw Error('已有对象快照无法读取。');const existing=await o.json();if(controller.signal.aborted)return;if(existing.model_id!==baseId||existing.space_id!==target.space||existing.frame_id!==info.frame_id||existing.source_model_sha256!==info.source_model_sha256)throw Error('对象锚点与当前模型不一致。');setRefKey(key(existing.ontology_ref));setOriginalRef(key(existing.ontology_ref));setDependencies({relations:existing.relations||[],business:existing.objects.filter((obj:{business_links?:unknown[]})=>obj.business_links?.length).map((obj:{object_id:string})=>obj.object_id)});const saved=existing.objects.map((obj:{object_id:string;type_id:string;properties:Record<string,string>;anchor_m:XYZ;evidence:{point_index:number}})=>({object_id:obj.object_id,type_id:obj.type_id,properties:obj.properties,point_index:obj.evidence.point_index,anchor_m:obj.anchor_m}));setObjects(saved);setOriginal(JSON.stringify(saved));}
  }).catch(e=>{if(!controller.signal.aborted){setBase(null);setError(e.message);}}).finally(()=>{if(!controller.signal.aborted)setReading(false);});return()=>controller.abort();
 },[baseId,target.space]);
 useEffect(()=>{
  const controller=new AbortController();setRules(null);setTypeId('');setProperties({});
  const ref=versions.find(v=>key(v)===refKey);if(!ref)return()=>controller.abort();
  fetch(`${endpoint}/api/ontologies/${ref.ontology_id}/${ref.version}?sha256=${ref.sha256}`,{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('固定本体规则无法读取。');return r.json();}).then(body=>{if(!controller.signal.aborted)setRules(body.definition);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[refKey,versions]);
 async function readAnchor(selected=Number(index)){
  if(!base||!Number.isSafeInteger(selected)||selected<0||selected>=base.point_count)return;
  const run=generation.current,controller=new AbortController();anchorRequest.current?.abort();anchorRequest.current=controller;
  setIndex(String(selected));setReading(true);setError('');setAnchor(null);
  try{const r=await fetch(`${endpoint}/candidates/${baseId}/api/anchor?point_index=${selected}`,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('点索引超出模型范围或候选不可读。');const value=await r.json();if(value.candidate_id!==baseId||value.space_id!==target.space||value.source_model_sha256!==base.source_model_sha256||value.point_index!==selected||value.frame_id!==base.frame_id||value.model_manifest_sha256!==base.model_manifest_sha256)throw Error('基础模型已变化，请重新选择候选。');if(run===generation.current&&!controller.signal.aborted)setAnchor(value);}catch(e){if(run===generation.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'锚点读取失败');}finally{if(run===generation.current&&!controller.signal.aborted)setReading(false);}
 }
 function add(e:React.FormEvent){
  e.preventDefault();if(!anchor||!rules||!typeId)return;setError('');setCreated(null);
  if(objects.some(o=>o.object_id===identity.trim()&&o.object_id!==editing)){setError('本次标注中对象ID已存在，请使用稳定且唯一的ID。');return;}
  const values=Object.fromEntries(Object.entries(properties).filter(([,value])=>value!==''));
  const draft={object_id:identity.trim(),type_id:typeId,properties:values,point_index:anchor.point_index,anchor_m:anchor.anchor_m};
  selectObject(draft);
  setObjects(current=>editing?current.map(obj=>obj.object_id===editing?draft:obj):[...current,draft]);setIdentity('');setEditing('');setAnchor(null);setFormOpen(false);
 }
 async function save(){
  const ref=versions.find(v=>key(v)===refKey);if(!ref||!base||!objects.length||saving.current)return;const run=generation.current;saving.current=true;setBusy(true);setError('');setCreated(null);
  try{const r=await fetch(`${endpoint}/api/semantic-candidates`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:target.space,base_candidate_id:baseId,base_manifest_sha256:base.model_manifest_sha256,ontology_ref:{ontology_id:ref.ontology_id,version:ref.version,sha256:ref.sha256},objects:objects.map(({object_id,type_id,properties,point_index})=>({object_id,type_id,properties,point_index}))})});const body=await r.json();if(!r.ok){const detail=body.detail;if(detail?.issues)throw Error(detail.issues.map((issue:{object_id:string;path:string;message:string})=>`${issue.object_id} ${issue.path}：${issue.message}`).join('；'));throw Error(`生成失败：${typeof detail==='string'?detail:'请检查字段、锚点和固定引用。'}`);}if(run===generation.current)setCreated(body);}catch(e){if(run===generation.current)setError(e instanceof Error?e.message:'生成失败');}finally{saving.current=false;if(run===generation.current)setBusy(false);}
 }
 if(!target.space)return <p className="text-body-small text-muted-foreground">选择工程空间后可建立对象标注候选。</p>;
 return <Card className={`module-surface ${embedded?'association-editor':''}`} aria-label="对象标注工作面">{!embedded&&<CardHeader><CardTitle>对象标注</CardTitle></CardHeader>}<CardContent className="flex flex-col gap-lg">

  {!embedded&&<><label htmlFor="annotation-base" className="text-body-small">基础候选</label><NativeSelect id="annotation-base" aria-label="标注基础候选" value={baseId} onChange={e=>{const value=e.target.value;e.target.value=baseId;void runGuarded(()=>setBaseId(value));}} disabled={busy||reading}><option value="">请选择已有候选</option>{jobs.map(job=><option key={job.id} value={job.id}>{job.id}</option>)}</NativeSelect></>}
  <label htmlFor="annotation-ontology" className="text-body-small">固定本体版本</label><NativeSelect id="annotation-ontology" aria-label="标注本体版本" value={refKey} onChange={e=>{const value=e.target.value;e.target.value=refKey;void runGuarded(()=>{setRefKey(value);setCreated(null);setEditing('');setIdentity('');setAnchor(null);});}} disabled={busy}><option value="">请选择规则版本</option>{versions.map(v=><option key={key(v)} value={key(v)}>{v.title} · {v.version_code||v.version}</option>)}</NativeSelect>
  {example&&<section className="association-example-queue" aria-label="示例待标注对象"><div className="association-toolbar"><strong>模板设备 · {example.name}</strong><span className="text-label-small text-muted-foreground">需逐个确认类型与模型点位</span></div>{example.objects.map(item=>{const present=objects.some(obj=>obj.object_id==='example-'+item.id);const supported=!!rules?.types[item.type]?.properties.name;return <div className="association-toolbar" key={item.id}><span>{item.name}</span><span className="flex items-center gap-sm"><small className="text-muted-foreground">{present?'已加入草稿':!rules?'先选择本体规则':supported?rules.types[item.type].title:'规则缺少类型 '+item.type}</small><Button size="sm" variant="ghost" disabled={present||!supported||!base||busy||reading||formOpen} onClick={()=>startExampleObject(item)}>选择位置</Button></span></div>;})}{rules&&example.objects.some(item=>!rules.types[item.type]?.properties.name)&&<p className="text-label-small text-muted-foreground">请在语义本体维护缺少的类型并固定新版本；模板不会替换为其他设备类型。</p>}</section>}
  {example&&!rules&&<Button asChild size="sm" variant="ghost" className="self-start"><a href={recordLink('ontology',{})} target="_blank" rel="noopener noreferrer">维护本体规则</a></Button>}
  {base&&<details><summary>模型坐标与来源依据</summary><p className="break-all text-label-small text-muted-foreground">{base.frame_id} · 米 · {base.point_count.toLocaleString()} 个模型点 · 摘要 {base.model_manifest_sha256}</p></details>}
  <section aria-label="对象清单" className="flex min-w-0 flex-col gap-lg"><div className="association-toolbar"><div><Input aria-label="搜索对象" placeholder="搜索名称或对象 ID" value={search} onChange={e=>setSearch(e.target.value)}/><NativeSelect aria-label="筛选对象类型" value={typeFilter} onChange={e=>setTypeFilter(e.target.value)}><option value="">全部类型</option>{Array.from(new Set(objects.map(o=>o.type_id))).map(id=><option key={id} value={id}>{rules?.types[id]?.title||id}</option>)}</NativeSelect><span className="text-label-small text-muted-foreground">{objects.length} 个对象{changed?' · 未保存':''}</span></div><Button size="sm" disabled={!base||!rules||busy||reading||formOpen} onClick={()=>startObject()}><Plus size={16}/>添加对象</Button></div>
  {objects.length?<div className="association-table-scroll"><Table><TableHeader><TableRow><TableHead>序号</TableHead><TableHead>对象名称</TableHead><TableHead>类型</TableHead><TableHead>位置</TableHead><TableHead>状态</TableHead><TableHead>操作</TableHead></TableRow></TableHeader><TableBody>{objects.filter(obj=>(!typeFilter||obj.type_id===typeFilter)&&`${obj.properties.name||''} ${obj.object_id}`.toLowerCase().includes(search.toLowerCase())).map((obj,i)=><TableRow key={obj.object_id} data-selected={selected===obj.object_id}><TableCell>{i+1}</TableCell><TableCell className="association-name-cell"><button type="button" className="association-object-name" aria-pressed={selected===obj.object_id} onClick={()=>selectObject(obj,true)} disabled={formOpen}>{obj.properties.name||obj.object_id}</button><small className="block text-muted-foreground">{obj.object_id}</small></TableCell><TableCell>{rules?.types[obj.type_id]?.title||obj.type_id}</TableCell><TableCell>模型点锚</TableCell><TableCell><StatusBadge tone="neutral">待核实</StatusBadge></TableCell><TableCell><div className="association-row-actions"><Button size="sm" variant="ghost" onClick={()=>selectObject(obj,true)} disabled={formOpen}><MapPin size={16}/>定位</Button><DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="association-more" aria-label={`${obj.properties.name||obj.object_id}更多操作`} disabled={busy||formOpen}><DotsThreeVertical size={24}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={()=>setLocation(obj)}>位置证据</DropdownMenuItem><DropdownMenuItem onSelect={()=>startObject(obj)}><PencilSimple size={16}/>编辑对象</DropdownMenuItem><DropdownMenuItem onSelect={()=>setRemoving(obj)}><Trash size={16}/>移除对象</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div></TableCell></TableRow>)}</TableBody></Table></div>:<div className="association-empty-list"><Selection size={24} className="mx-auto mb-sm"/>尚无对象。选用本体规则后，添加对象并在模型中选择位置。</div>}
  </section>
  {base&&<div ref={workArea} className="association-object-workspace">
   <div className="association-object-model">{active&&<AnchorPicker endpoint={endpoint} space={target.space} candidate={baseId} manifest={base.model_manifest_sha256} onPick={i=>void readAnchor(i)} disabled={!formOpen||busy||reading} markers={markers} selected={selected} onSelect={formOpen?undefined:id=>setSelected(id)} focus={focus} editing={formOpen} anchor={formOpen?anchor?.anchor_m:undefined}/>}</div>
   {rules&&formOpen?<form onSubmit={add} className="association-form-panel">
   <div className="association-toolbar"><strong>{editing?'编辑对象':'添加对象'}</strong><Button type="button" variant="ghost" size="sm" onClick={closeForm}><X size={16}/>取消编辑</Button></div>
   <div className="grid grid-cols-1 gap-md"><div className="flex flex-col gap-sm"><label htmlFor="object-id">对象ID</label><Input id="object-id" aria-label="标注对象ID" value={identity} onChange={e=>setIdentity(e.target.value)} placeholder="object-001" maxLength={160} pattern="[a-zA-Z0-9][a-zA-Z0-9_.:\-]*" required disabled={busy||Boolean(editing)}/></div><div className="flex flex-col gap-sm"><label htmlFor="object-type">类型</label><NativeSelect id="object-type" aria-label="标注对象类型" value={typeId} onChange={e=>{setTypeId(e.target.value);setProperties({});}} required disabled={busy}><option value="">请选择本体类型</option>{Object.entries(rules.types).map(([id,type])=><option key={id} value={id}>{type.title} · {id}</option>)}</NativeSelect></div></div>
   {Object.entries(rules.types[typeId]?.properties||{}).map(([name,rule])=><div key={name} className="flex flex-col gap-sm"><label htmlFor={`object-property-${name}`}>{rule.title}{rule.required?'（必填）':'（选填）'}</label><Input id={`object-property-${name}`} aria-label={`标注属性 ${name}`} value={properties[name]||''} onChange={e=>setProperties({...properties,[name]:e.target.value})} required={rule.required} minLength={rule.min_length} maxLength={rule.max_length} disabled={busy}/></div>)}
   <details><summary>按模型索引选择（备用）</summary><div className="flex flex-wrap items-end gap-sm"><div className="flex flex-col gap-sm"><label htmlFor="object-point-index">模型点索引</label><Input id="object-point-index" aria-label="标注模型点索引" type="number" step="1" min="0" max={base.point_count-1} value={index} onChange={e=>{setIndex(e.target.value);setAnchor(null);}} disabled={busy||reading}/></div><Button type="button" variant="secondary" onClick={()=>void readAnchor()} disabled={busy||reading||index===''}>读取锚点</Button><Button asChild type="button" variant="ghost"><a href={candidateScreenHref(target.space,baseId)} target="_blank" rel="noopener noreferrer">查看基础模型</a></Button></div></details>
   {anchor&&<p className="text-body-small text-muted-foreground">锚点 [{anchor.anchor_m.map(v=>v.toFixed(4)).join(', ')}] 米 · 证据：spatial.npz 第 {anchor.point_index} 点 · 语义待核实</p>}
   <Button type="submit" className="self-start" variant="secondary" disabled={busy||reading||!anchor||!typeId||(!editing&&objects.length>=100)}>{editing?'应用到草稿':'加入对象清单'}</Button>
  </form>:<section aria-label="对象属性" className="association-object-properties">
    <div className="association-toolbar"><h4>对象属性</h4>{current&&<Button size="sm" variant="ghost" disabled={busy||!rules} onClick={()=>startObject(current)}><PencilSimple size={16}/>编辑</Button>}</div>
    {current?<><strong>{current.properties.name||current.object_id}</strong><dl><div><dt>类型</dt><dd>{rules?.types[current.type_id]?.title||current.type_id}</dd></div>{Object.entries(current.properties).filter(([key])=>key!=='name').map(([key,value])=><div key={key}><dt>{rules?.types[current.type_id]?.properties[key]?.title||key}</dt><dd>{value}</dd></div>)}<div><dt>模型坐标（米）</dt><dd>{current.anchor_m.map(v=>v.toFixed(4)).join(', ')}</dd></div></dl><div className="association-toolbar"><StatusBadge tone="neutral">待核实</StatusBadge><Button size="sm" variant="ghost" onClick={()=>setLocation(current)}>位置证据</Button></div></>:<p className="text-muted-foreground">从模型或清单选择一个对象。添加对象后可在模型中选取位置。</p>}
   </section>}
  </div>}

  {error&&<p role="alert" className="whitespace-pre-wrap text-body-small">{error}</p>}
  <Button className="self-start" disabled={busy||reading||!base||!rules||!objects.length||formOpen||!changed} onClick={save}>{busy?'保存中…':'保存对象候选'}</Button>
  {created&&<div role="status" className="flex flex-wrap items-center gap-sm"><StatusBadge tone="success">标注候选已保存</StatusBadge><span className="text-label-small">{created.id}</span><Button asChild size="sm" variant="secondary"><a href={recordLink('association',{job:created.id,tab:'relations'})}>继续关联</a></Button><Button asChild size="sm" variant="secondary"><a href={candidateScreenHref(target.space,created.id)} target="_blank" rel="noopener noreferrer">查看对象与双视图</a></Button><Button asChild size="sm"><a href={recordLink('build',{job:created.id})}>前往构建中心核对</a></Button><p className="w-full text-label-small text-muted-foreground">尚未选择或发布；几何未重新估计，所有对象保留待核实状态。</p></div>}
 <Dialog open={!!removing} onOpenChange={open=>{if(!open)setRemoving(null);}}><DialogContent><DialogHeader><DialogTitle>移除对象</DialogTitle><DialogDescription>从本次草稿移除 {removing?.properties.name||removing?.object_id}。保存后生成新候选，原快照和已有发布保持固定。</DialogDescription></DialogHeader>{removing&&<p className="text-body-small">关联影响：{dependencies.relations.filter(r=>r.source_id===removing.object_id||r.target_id===removing.object_id).length} 项空间关系、{dependencies.business.includes(removing.object_id)?1:0} 项业务绑定将在新候选中一并解除。</p>}<DialogFooter><Button variant="ghost" onClick={()=>setRemoving(null)}>取消</Button><Button variant="secondary" onClick={()=>{setObjects(items=>items.filter(o=>o.object_id!==removing?.object_id));setCreated(null);setRemoving(null);}}>确认移除</Button></DialogFooter></DialogContent></Dialog>
 <Dialog open={!!location} onOpenChange={open=>{if(!open)setLocation(null);}}><DialogContent><DialogHeader><DialogTitle>{location?.properties.name||location?.object_id} · 位置证据</DialogTitle><DialogDescription>位置来自当前固定模型，不代表对象轮廓或现场精度验收。</DialogDescription></DialogHeader><dl className="flex flex-col gap-md text-body-small"><div><dt>模型坐标系</dt><dd>{base?.frame_id} · 米</dd></div><div><dt>位置依据</dt><dd>spatial.npz · 点索引 {location?.point_index}</dd></div><div><dt>锚点（米）</dt><dd>{location?.anchor_m.map(v=>v.toFixed(4)).join(', ')}</dd></div><div><dt>来源快照</dt><dd className="break-all">{baseId}</dd></div></dl></DialogContent></Dialog>
 </CardContent></Card>;
}
