import React,{useEffect,useRef,useState} from 'react';
import {Books,DotsThreeVertical,LinkSimple,Eye,LinkBreak} from '@phosphor-icons/react';
import {Button,Input,NativeSelect,Drawer,Table,TableHeader,TableBody,TableRow,TableHead,TableCell,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {useUnsavedNavigation} from './unsaved-navigation';

type Reference={module_id:string;version:string;sha256:string};
type Concept={concept_id:string;title:string;definition:string};
type Option={reference:Reference;title:string;maturity:string;published_at:string;concepts:Concept[]};
type Link={object_id:string;reference:Reference;concept_id:string;linked_at:string;definition:{title:string;definition:string;effective_properties:Record<string,{title:string;data_type:string;required:boolean}>}};
type ObjectItem={object_id:string;name:string};
type State={space_id:string;candidate_id:string;revision:number;source_sha256:string;objects:ObjectItem[];links:Link[];options:Option[];can_edit:boolean};
type Mode='edit'|'view'|'remove';
const refKey=(ref:Reference)=>`${ref.module_id}@${ref.version}/${ref.sha256}`;
const endpoint=businessEndpoint+'/api/scene-ontology-links';
const messages:Record<string,string>={link_source_inactive:'当前模型来源已归档，仍可查看引用；请恢复来源后再修改。',link_revision_changed:'引用已被其他人修改，请关闭面板并重新读取后继续。',link_source_changed:'模型来源已变化，请重新打开当前来源。',release_not_found:'所选本体版本尚未发布或不可用，请重新读取。',link_request_conflict:'请求内容已变化，请关闭面板后重新操作。',object_not_found:'当前模型快照中没有此对象。'};
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
 const request=useRef<Record<string,unknown>|null>(null),gate=useRef(false),mounted=useRef(true);
 const current=data?.links.find(link=>link.object_id===editing?.object_id);
 const option=data?.options.find(item=>refKey(item.reference)===selected);
 const chosen=option?.concepts.find(item=>item.concept_id===concept);
 const dirty=mode==='edit'&&!!editing&&(selected!==(current?refKey(current.reference):'')||concept!==(current?.concept_id||''));
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
 }
 function close(){if(!gate.current){setEditing(null);request.current=null;setError('');}}
 async function save(){
  if(gate.current||!editing||!data||mode==='view'||mode==='edit'&&(!option||!chosen))return;
  gate.current=true;setBusy(true);setError('');
  if(!request.current){
   request.current={space_id:spaceId,candidate_id:candidateId,source_sha256:data.source_sha256,object_id:editing.object_id,expected_revision:data.revision,request_id:crypto.randomUUID().replaceAll('-',''),action:mode==='remove'?'remove':'set'};
   if(mode==='edit')Object.assign(request.current,{reference:option!.reference,concept_id:concept});
  }
  try{
   await responseValue(await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request.current)}));
   const value=await read();
   if(mounted.current){setData(value);setEditing(null);request.current=null;setNotice(mode==='remove'?'已解除当前对象的本体引用。':'已保存固定本体引用，实例属性尚未校验。');}
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:'本体引用暂不可用。');}
  finally{gate.current=false;if(mounted.current)setBusy(false);}
 }
 const filtered=(data?.objects||[]).filter(item=>!query||`${item.name} ${item.object_id}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
 return <section className="association-semantic-links" aria-label="对象本体引用">
  <header className="workspace-section-heading"><div><h3><Books size={20}/>对象本体引用</h3><p>引用已发布的固定定义；对象属性校验与纳入服务发布另行处理。</p></div></header>
  <div className="association-semantic-toolbar"><span>共 {data?.objects.length??'—'} 项，已引用 {data?.links.length??'—'} 项</span><Input aria-label="搜索引用对象" placeholder="搜索对象名称或标识" value={query} maxLength={160} onChange={event=>setQuery(event.target.value)}/><Button variant="outline" disabled={loading||!!editing} onClick={()=>setRefresh(value=>value+1)}>刷新</Button></div>
  {loading&&<output>正在读取对象本体引用…</output>}
  {error&&!editing&&<p role="alert">{error}</p>}{notice&&<output>{notice}</output>}
  {data&&!loading&&!error&&<>
   {!data.options.length&&<p className="text-muted-foreground">暂无已发布的本体版本，请先在公共资源的语义本体中完成定义审批与发布。</p>}
   <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead className="association-semantic-index">序号</TableHead><TableHead>对象名称 / 标识</TableHead><TableHead>引用概念</TableHead><TableHead>本体版本</TableHead><TableHead>引用状态</TableHead><TableHead className="association-semantic-actions">操作</TableHead></TableRow></TableHeader><TableBody>{filtered.map((object,index)=>{
    const link=data.links.find(item=>item.object_id===object.object_id);
    return <TableRow key={object.object_id}><TableCell className="association-semantic-index">{index+1}</TableCell><TableCell><span>{object.name}</span><small className="block text-muted-foreground">{object.object_id}</small></TableCell><TableCell>{link?.definition.title||'—'}</TableCell><TableCell>{link?<><span>{link.reference.module_id} · {link.reference.version}</span><small className="block text-muted-foreground">{new Date(link.linked_at).toLocaleDateString('zh-CN')}</small></>:'—'}</TableCell><TableCell>{link?'已引用 · 待实例校验':'未引用'}</TableCell><TableCell className="association-semantic-actions"><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="association-semantic-more" aria-label={object.name+'本体引用操作'} disabled={!link&&!data.can_edit}><DotsThreeVertical size={24}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end">{link&&<DropdownMenuItem onSelect={()=>open(object,'view')}><Eye size={16}/>查看定义</DropdownMenuItem>}{data.can_edit&&<><DropdownMenuItem disabled={!data.options.length} onSelect={()=>open(object,'edit')}><LinkSimple size={16}/>{link?'调整引用':'引用本体'}</DropdownMenuItem>{link&&<><DropdownMenuSeparator/><DropdownMenuItem onSelect={()=>open(object,'remove')}><LinkBreak size={16}/>解除引用</DropdownMenuItem></>}</>}</DropdownMenuContent></DropdownMenu></TableCell></TableRow>;
   })}</TableBody></Table></div>
   {!filtered.length&&<p>{data.objects.length?'没有匹配的对象。':'当前模型没有已保存对象，请先在对象管理中添加并保存。'}</p>}
  </>}
  <Drawer open={!!editing} onClose={close} side="right" width="md" title={mode==='view'?'对象引用定义':mode==='remove'?'解除本体引用':'引用固定本体'} description={editing?.name} closeLabel="关闭本体引用" footer={<div className="association-semantic-footer"><Button variant="outline" disabled={busy} onClick={close}>{mode==='view'?'关闭':'取消'}</Button>{mode!=='view'&&<Button disabled={busy||mode==='edit'&&(!dirty||!chosen)} onClick={()=>void save()}>{busy?'保存中…':mode==='remove'?'确认解除':'保存引用'}</Button>}</div>}>
   <div className="association-semantic-form">
    {mode==='edit'?<fieldset disabled={busy}><label>本体版本<NativeSelect aria-label="本体版本" value={selected} onChange={event=>{request.current=null;setSelected(event.target.value);setConcept('');}}><option value="">选择已发布版本</option>{data?.options.map(item=><option key={refKey(item.reference)} value={refKey(item.reference)}>{item.title} · {item.reference.version}</option>)}</NativeSelect></label><label>概念<NativeSelect aria-label="引用概念" value={concept} disabled={!option} onChange={event=>{request.current=null;setConcept(event.target.value);}}><option value="">选择概念</option>{option?.concepts.map(item=><option key={item.concept_id} value={item.concept_id}>{item.title}</option>)}</NativeSelect></label>{chosen&&<p>{chosen.definition}</p>}<p className="text-muted-foreground">保存后固定此版本，后续本体升级不会自动替换。候选定义的专业成熟度保持原状。</p></fieldset>:current&&<><h4>{current.definition.title}</h4><p>{current.definition.definition}</p><p>{current.reference.module_id} · {current.reference.version}</p>{mode==='remove'?<p>解除当前模型对象的引用，保留原对象、几何和既有服务发布。</p>:<dl>{Object.entries(current.definition.effective_properties).map(([id,property])=><div key={id}><dt>{property.title} <small>{id}</small></dt><dd>{property.data_type} · {property.required?'必填':'选填'}</dd></div>)}</dl>}</>}
    {error&&<p role="alert">{error}</p>}
   </div>
  </Drawer>
 </section>;
}
