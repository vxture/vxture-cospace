import {SceneOntologyObjectView} from './scene-ontology-object-view';
import React,{useEffect,useRef,useState} from 'react';
import {Books,DotsThreeVertical,LinkSimple,Eye,LinkBreak,ListChecks,MapPin} from '@phosphor-icons/react';
import {Button,Input,NativeSelect,Drawer,Table,TableHeader,TableBody,TableRow,TableHead,TableCell,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {useUnsavedNavigation} from './unsaved-navigation';

type Reference={module_id:string;version:string;sha256:string};
type Concept={concept_id:string;title:string;definition:string};
type Option={reference:Reference;title:string;maturity:string;published_at:string;concepts:Concept[]};
type Property={title:string;data_type:string;required:boolean;unit?:string;quantity?:string};
type Claim={value:string|number|boolean;unit?:string;quantity?:string};
type Diagnostic={code:string;path:string;message?:string};
type Link={object_id:string;reference:Reference;concept_id:string;linked_at:string;instance_properties?:Record<string,Claim>;instance_valid_time?:{start:string;end:string|null}|null;evidence_note?:string;definition:{title:string;definition:string;effective_properties:Record<string,Property>}};
type ObjectItem={object_id:string;name:string};
type State={space_id:string;candidate_id:string;revision:number;source_sha256:string;objects:ObjectItem[];links:Link[];options:Option[];can_edit:boolean;instance_report?:{valid:boolean;diagnostics:Diagnostic[];objects:{object_id:string;valid:boolean;diagnostics:Diagnostic[]}[]}};
type Mode='edit'|'view'|'remove'|'properties';
const issueLabels:Record<string,string>={geometry_not_recorded:'未记录几何（不在本次校验范围）',schema_invalid:'格式不符合实例契约',object_validation_incomplete:'其他对象格式有误，本次尚未完成属性校验',required_property:'缺少必填属性',property_type_mismatch:'属性类型不符',unit_mismatch:'单位不符',quantity_mismatch:'物理量不符',empty_property:'属性不能为空',property_below_minimum:'属性低于允许最小值',required_valid_time:'缺少有效时间',invalid_time:'时间格式不合法',invalid_period:'时间区间不合法',definition_version_conflict:'固定定义版本冲突',invalid_valid_time:'有效时间不合法'};
const claimFields=(link?:Link)=>Object.fromEntries(Object.entries(link?.instance_properties||{}).map(([id,claim])=>[id,String(claim.value)]));
const refKey=(ref:Reference)=>`${ref.module_id}@${ref.version}/${ref.sha256}`;
const endpoint=businessEndpoint+'/api/scene-ontology-links';
const messages:Record<string,string>={link_source_inactive:'当前模型来源已归档，仍可查看引用；请恢复来源后再修改。',link_revision_changed:'引用已被其他人修改，请关闭面板并重新读取后继续。',link_source_changed:'模型来源已变化，请重新打开当前来源。',release_not_found:'所选本体版本尚未发布或不可用，请重新读取。',link_request_conflict:'请求内容已变化，请关闭面板后重新操作。',link_relations_present:'此对象已有本体关系映射，请先在空间关系中解除相关映射，再调整或解除概念引用。',link_attributes_present:'当前引用已有实例属性，请明确选择清空后再调整引用。',link_not_found:'请先为当前对象引用本体。',object_not_found:'当前模型快照中没有此对象。'};
async function responseValue(response:Response){
 if(!response.ok){let code='';try{code=(await response.json()).detail;}catch{}
  if(response.status===401)throw new Error('请先登录。');
  if(response.status===403)throw new Error('当前身份无权执行此操作。');
  throw new Error(messages[code]||'本体引用暂不可用，请重试。');
 }
 return response.json();
}

export function SceneOntologyLinksPanel({spaceId,candidateId,active}:{spaceId:string;candidateId:string;active:boolean}){
 const [data,setData]=useState<State|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [query,setQuery]=useState(''),[editing,setEditing]=useState<ObjectItem|null>(null),[mode,setMode]=useState<Mode>('view');
 const [selected,setSelected]=useState(''),[concept,setConcept]=useState(''),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0);
 const [values,setValues]=useState<Record<string,string>>({}),[note,setNote]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState(''),[reset,setReset]=useState(false);
 const [inspecting,setInspecting]=useState<{objectId:string;revision:number;sourceSha:string}|null>(null);
 const request=useRef<Record<string,unknown>|null>(null),gate=useRef(false),mounted=useRef(true);
 const current=data?.links.find(link=>link.object_id===editing?.object_id);
 const option=data?.options.find(item=>refKey(item.reference)===selected);
 const chosen=option?.concepts.find(item=>item.concept_id===concept);
 const referenceChanged=selected!==(current?refKey(current.reference):'')||concept!==(current?.concept_id||'');
 const dirty=!!editing&&(mode==='edit'&&(referenceChanged||reset)||mode==='properties'&&(JSON.stringify(values)!==JSON.stringify(claimFields(current))||note!==(current?.evidence_note||'')||start!==(current?.instance_valid_time?.start||'')||end!==(current?.instance_valid_time?.end||'')));
 const objectReport=data?.instance_report?.objects.find(item=>item.object_id===editing?.object_id);
 const issues=objectReport?.diagnostics.length?objectReport.diagnostics:data?.instance_report?.diagnostics.filter(issue=>!issue.path.startsWith('/entities/'))||[];
 const needsReset=referenceChanged&&current?.instance_properties!==undefined;
 useUnsavedNavigation(dirty||busy,'对象本体引用',{discard:()=>setEditing(null)});
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 async function read(signal?:AbortSignal):Promise<State>{
  const value:State=await responseValue(await fetch(endpoint+'?'+new URLSearchParams({space_id:spaceId,candidate_id:candidateId}),{signal,cache:'no-store'}));
  if(value.space_id!==spaceId||value.candidate_id!==candidateId||!Array.isArray(value.objects)||!Array.isArray(value.links)||!Array.isArray(value.options))throw new Error('本体引用与当前模型来源不一致。');
  return value;
 }
 useEffect(()=>{
  if(!active)return;
  const abort=new AbortController();setLoading(true);setError('');
  read(abort.signal).then(value=>{if(!abort.signal.aborted)setData(value);}).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
  return()=>abort.abort();
 },[spaceId,candidateId,active,refresh]);
 function open(object:ObjectItem,next:Mode){
  const link=data?.links.find(item=>item.object_id===object.object_id);
  request.current=null;setEditing(object);setMode(next);setSelected(link?refKey(link.reference):'');setConcept(link?.concept_id||'');setError('');setNotice('');
  setValues(claimFields(link));setNote(link?.evidence_note||'');setStart(link?.instance_valid_time?.start||'');setEnd(link?.instance_valid_time?.end||'');setReset(false);
 }
 function close(){if(!gate.current){setEditing(null);request.current=null;setError('');}}
 async function save(){
  if(gate.current||!editing||!data?.can_edit||mode==='view'||mode==='edit'&&(!option||!chosen))return;
  let properties:Record<string,Claim>={};
  if(mode==='properties'){
   if(!current||!note.trim()){setError('请填写录入依据。');return;}
   if(end&&!start){setError('填写结束时间时需要开始时间。');return;}
   for(const [id,property] of Object.entries(current.definition.effective_properties)){
    const raw=values[id]??'';if(raw==='')continue;
    let value:string|number|boolean=raw;
    if(property.data_type==='number'||property.data_type==='integer'){
     value=Number(raw);if(!raw.trim()||!Number.isFinite(value)||property.data_type==='integer'&&!Number.isInteger(value)){setError(`${property.title}需要有效${property.data_type==='integer'?'整数':'数字'}。`);return;}
    }else if(property.data_type==='boolean')value=raw==='true';
    properties[id]={value,...(property.unit?{unit:property.unit}:{}),...(property.quantity?{quantity:property.quantity}:{})};
   }
  }
  gate.current=true;setBusy(true);setError('');
  if(!request.current){
   request.current={space_id:spaceId,candidate_id:candidateId,source_sha256:data.source_sha256,object_id:editing.object_id,expected_revision:data.revision,request_id:crypto.randomUUID().replaceAll('-',''),action:mode==='remove'?'remove':mode==='properties'?'properties':'set'};
   if(mode==='edit')Object.assign(request.current,{reference:option!.reference,concept_id:concept,...(reset?{reset_properties:true}:{})});
   if(mode==='properties')Object.assign(request.current,{properties,valid_time:start?{start,end:end||null}:null,evidence_note:note});
  }
  try{
   await responseValue(await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request.current)}));
   const value=await read();
   if(mounted.current){setData(value);setEditing(null);request.current=null;setNotice(mode==='remove'?'已解除引用及其消费侧实例属性。':mode==='properties'?'已保存实例属性并完成局部校验，请查看属性校验状态。':'已保存固定本体引用，请维护实例属性。');}
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:'本体引用暂不可用。');}
  finally{gate.current=false;if(mounted.current)setBusy(false);}
 }
 const filtered=(data?.objects||[]).filter(item=>!query||`${item.name} ${item.object_id}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
 return <section className="association-semantic-links" aria-label="对象本体引用">
  <header className="workspace-section-heading association-stage-heading"><div><h3><Books size={20}/>对象本体引用</h3><p>依据固定定义维护实例属性；校验仅覆盖属性，尚未包含关系、几何与服务发布。</p></div></header>
  <div className="association-semantic-toolbar"><span>共 {data?.objects.length??'—'} 项，已引用 {data?.links.length??'—'} 项</span><Input aria-label="搜索引用对象" placeholder="搜索对象名称或标识" value={query} maxLength={160} onChange={event=>setQuery(event.target.value)}/><Button variant="outline" disabled={loading||!!editing||!!inspecting} onClick={()=>setRefresh(value=>value+1)}>刷新</Button></div>
  {loading&&<output>正在读取对象本体引用…</output>}
  {error&&!editing&&<p role="alert">{error}</p>}{notice&&<output>{notice}</output>}
  {data&&!loading&&!error&&<>
   {!data.options.length&&<p className="text-muted-foreground">暂无已发布的本体版本，请先在公共资源的语义本体中完成定义审批与发布。</p>}
   <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead className="association-semantic-index">序号</TableHead><TableHead>对象名称 / 标识</TableHead><TableHead>引用概念</TableHead><TableHead>本体版本</TableHead><TableHead>引用状态</TableHead><TableHead className="association-semantic-actions">操作</TableHead></TableRow></TableHeader><TableBody>{filtered.map((object,index)=>{
    const link=data.links.find(item=>item.object_id===object.object_id);
    return <TableRow key={object.object_id}><TableCell className="association-semantic-index">{index+1}</TableCell><TableCell><span>{object.name}</span><small className="block text-muted-foreground">{object.object_id}</small></TableCell><TableCell>{link?.definition.title||'—'}</TableCell><TableCell>{link?<><span>{link.reference.module_id} · {link.reference.version}</span><small className="block text-muted-foreground">{new Date(link.linked_at).toLocaleDateString('zh-CN')}</small></>:'—'}</TableCell><TableCell>{link?(data.instance_report?.objects.find(item=>item.object_id===object.object_id)?.valid?'属性校验通过（局部）':'已引用 · 属性待修正'):'未引用'}</TableCell><TableCell className="association-semantic-actions"><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="association-semantic-more" aria-label={object.name+'本体引用操作'} disabled={!!inspecting}><DotsThreeVertical size={24}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={()=>setInspecting({objectId:object.object_id,revision:data.revision,sourceSha:data.source_sha256})}><MapPin size={16}/>联查与模型定位</DropdownMenuItem>{link&&<><DropdownMenuItem onSelect={()=>open(object,'view')}><Eye size={16}/>查看定义</DropdownMenuItem><DropdownMenuItem onSelect={()=>open(object,'properties')}><ListChecks size={16}/>{data.can_edit?'实例属性':'查看实例属性'}</DropdownMenuItem></>}{data.can_edit&&<><DropdownMenuItem disabled={!data.options.length} onSelect={()=>open(object,'edit')}><LinkSimple size={16}/>{link?'调整引用':'引用本体'}</DropdownMenuItem>{link&&<><DropdownMenuSeparator/><DropdownMenuItem onSelect={()=>open(object,'remove')}><LinkBreak size={16}/>解除引用</DropdownMenuItem></>}</>}</DropdownMenuContent></DropdownMenu></TableCell></TableRow>;
   })}</TableBody></Table></div>
   {!filtered.length&&<p>{data.objects.length?'没有匹配的对象。':'当前模型没有已保存对象，请先在对象管理中添加并保存。'}</p>}
  </>}
  {inspecting&&<SceneOntologyObjectView spaceId={spaceId} candidateId={candidateId} objectId={inspecting.objectId} revision={inspecting.revision} sourceSha={inspecting.sourceSha} onClose={()=>setInspecting(null)}/>}
  <Drawer open={!!editing} onClose={close} side="right" width="md" title={mode==='view'?'对象引用定义':mode==='remove'?'解除本体引用':mode==='properties'?'实例属性':'引用固定本体'} description={editing?.name} closeLabel="关闭本体引用" footer={<div className="association-semantic-footer"><Button variant="outline" disabled={busy} onClick={close}>{mode==='view'||!data?.can_edit?'关闭':'取消'}</Button>{mode!=='view'&&data?.can_edit&&<Button disabled={busy||mode==='edit'&&(!dirty||!chosen||!!needsReset&&!reset)||mode==='properties'&&(!dirty||!note.trim())} onClick={()=>void save()}>{busy?'保存中…':mode==='remove'?'确认解除':mode==='properties'?'保存并校验':'保存引用'}</Button>}</div>}>
   <div className="association-semantic-form">
    {mode==='edit'?<fieldset disabled={busy}><label>本体版本<NativeSelect aria-label="本体版本" value={selected} onChange={event=>{request.current=null;setSelected(event.target.value);setConcept('');}}><option value="">选择已发布版本</option>{data?.options.map(item=><option key={refKey(item.reference)} value={refKey(item.reference)}>{item.title} · {item.reference.version}</option>)}</NativeSelect></label><label>概念<NativeSelect aria-label="引用概念" value={concept} disabled={!option} onChange={event=>{request.current=null;setConcept(event.target.value);}}><option value="">选择概念</option>{option?.concepts.map(item=><option key={item.concept_id} value={item.concept_id}>{item.title}</option>)}</NativeSelect></label>{chosen&&<p>{chosen.definition}</p>}{needsReset&&<label className="association-semantic-check"><input type="checkbox" checked={reset} onChange={event=>{request.current=null;setReset(event.target.checked);}}/>清空当前实例属性及录入依据，按新定义重新填写</label>}<p className="text-muted-foreground">保存后固定此版本，后续本体升级不会自动替换。候选定义的专业成熟度保持原状。</p></fieldset>:mode==='properties'&&current?<fieldset disabled={busy||!data?.can_edit}><p>{current.definition.title} · {current.reference.version}</p><p className="text-muted-foreground">按固定定义人工填写，不自动复制原对象属性。保存后返回属性局部校验，不能据此判断现场真实或关系完整。</p>{Object.entries(current.definition.effective_properties).map(([id,property])=><label key={id}>{property.title}{property.required?' *':''}<small className="text-muted-foreground">{id} · {property.data_type}{property.unit?` · ${property.unit}`:''}{property.quantity?` · ${property.quantity}`:''}</small>{property.data_type==='boolean'?<NativeSelect aria-label={property.title} value={values[id]??''} onChange={event=>{request.current=null;setValues({...values,[id]:event.target.value});}}><option value="">未填写</option><option value="true">是</option><option value="false">否</option></NativeSelect>:<Input aria-label={property.title} maxLength={2000} inputMode={property.data_type==='number'||property.data_type==='integer'?'decimal':undefined} value={values[id]??''} onChange={event=>{request.current=null;setValues({...values,[id]:event.target.value});}}/>}</label>)}<label>录入依据 *<Input aria-label="录入依据" maxLength={2000} value={note} onChange={event=>{request.current=null;setNote(event.target.value);}} placeholder="填写资料来源及待核实事项"/></label><label>有效开始时间（可选，UTC）<Input aria-label="有效开始时间" placeholder="2026-11-20T00:00:00Z" maxLength={40} value={start} onChange={event=>{request.current=null;setStart(event.target.value);}}/></label><label>有效结束时间（可选，UTC）<Input aria-label="有效结束时间" placeholder="留空表示持续有效" maxLength={40} value={end} onChange={event=>{request.current=null;setEnd(event.target.value);}}/></label><section aria-label="当前属性校验"><h4>当前已保存属性校验</h4><p>{objectReport?.valid?'属性校验通过（局部）':'待修正'}</p>{issues.length>0&&<ul>{issues.map((issue,index)=><li key={index}>{issueLabels[issue.code]||issue.code} · {issue.path.split('/properties/')[1]||(issue.path.includes('/valid_time')?'有效时间':'当前对象')}</li>)}</ul>}<p className="text-muted-foreground">修改后需保存，才会更新校验结果；关系、几何及专业审核未执行。</p></section></fieldset>:current&&<><h4>{current.definition.title}</h4><p>{current.definition.definition}</p><p>{current.reference.module_id} · {current.reference.version}</p>{mode==='remove'?<p>解除当前对象的引用及其消费侧实例属性、有效时间与录入依据；原对象、几何和既有服务发布不变。</p>:<dl>{Object.entries(current.definition.effective_properties).map(([id,property])=><div key={id}><dt>{property.title} <small>{id}</small></dt><dd>{property.data_type} · {property.required?'必填':'选填'}</dd></div>)}</dl>}</>}
    {error&&<p role="alert">{error}</p>}
   </div>
  </Drawer>
 </section>;
}
