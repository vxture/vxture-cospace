import {DotsThreeVertical,PencilSimple,ArrowLineUp,ArrowUp,ArrowDown,ArrowLineDown} from '@phosphor-icons/react';
import React,{useEffect,useRef,useState} from 'react';
import {Button,Input,Textarea,NativeSelect,Table,TableHeader,TableBody,TableRow,TableHead,TableCell,StatusBadge,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator,DropdownMenuGroup} from '@vxture/design-system';

export type OntologyGroup={group_id:string;name:string;description:string;origin:'preset'|'custom';status:'active'|'inactive';sort_order:number;sequence?:{group_id:string;name:string}[]};
export type GroupConfiguration={profile:'vxture.ontology-group-configuration/0.1';revision:number;can_manage:boolean;groups:OntologyGroup[];history:{revision:number;actor:string;reason:string;changed_at:string;before:OntologyGroup|null;after:OntologyGroup}[];history_limit:number};
export type GroupMove={request_id:string;expected_revision:number;group_id:string;move:'top'|'up'|'down'|'bottom';reason:string};
export type GroupChange={request_id:string;expected_revision:number;group_id:string|null;name:string;description:string;status:'active'|'inactive';sort_order:number;reason:string};
export type GroupConfigurationClient={load:(signal:AbortSignal)=>Promise<GroupConfiguration>;save:(change:GroupChange|GroupMove,signal:AbortSignal)=>Promise<GroupConfiguration>};
export function parseGroupConfiguration(value:unknown):GroupConfiguration{
 const v=value as GroupConfiguration;
 const validGroup=(g:OntologyGroup)=>g&&typeof g.group_id==='string'&&typeof g.name==='string'&&typeof g.description==='string'&&['preset','custom'].includes(g.origin)&&['active','inactive'].includes(g.status)&&Number.isInteger(g.sort_order);
 if(!v||v.profile!=='vxture.ontology-group-configuration/0.1'||!Number.isInteger(v.revision)||v.revision<0||typeof v.can_manage!=='boolean'||!Array.isArray(v.groups)||!v.groups.every(validGroup)||new Set(v.groups.map(g=>g.group_id)).size!==v.groups.length||!Array.isArray(v.history)||!v.history.every(h=>Number.isInteger(h.revision)&&typeof h.actor==='string'&&typeof h.reason==='string'&&typeof h.changed_at==='string'&&validGroup(h.after)&&(h.before===null||validGroup(h.before))))throw Error('分组配置响应无效。');
 return v;
}
const empty=()=>({group_id:null as string|null,name:'',description:'',status:'active' as 'active'|'inactive',sort_order:100,reason:''});
export function OntologyGroupConfiguration({client,onDirtyChange}:{client:GroupConfigurationClient;onDirtyChange?:(dirty:boolean)=>void}){
 const [data,setData]=useState<GroupConfiguration|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0),[query,setQuery]=useState(''),[status,setStatus]=useState(''),[form,setForm]=useState<ReturnType<typeof empty>|null>(null),[dirty,setDirty]=useState(false);
 const moveRequest=useRef<GroupMove|null>(null);
 const requestId=useRef(''),saving=useRef<AbortController|null>(null),gate=useRef(false);
 useEffect(()=>()=>saving.current?.abort(),[]);
 useEffect(()=>{onDirtyChange?.(dirty);return()=>onDirtyChange?.(false);},[dirty,onDirtyChange]);
 useEffect(()=>{const controller=new AbortController();setData(null);setLoading(true);setError('');client.load(controller.signal).then(parseGroupConfiguration).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[client,refresh]);
 function begin(group?:OntologyGroup){setForm(group?{...group,reason:''}:empty());setDirty(false);setError('');setNotice('');requestId.current='';}
 function update(patch:Partial<ReturnType<typeof empty>>){setForm(f=>f?{...f,...patch}:null);setDirty(true);requestId.current='';setNotice('');}
 async function save(){
  if(!form||!data?.can_manage||gate.current)return;gate.current=true;setBusy(true);setError('');setNotice('');
  if(!requestId.current)requestId.current=crypto.randomUUID().replaceAll('-','');
  const controller=new AbortController();saving.current=controller;
  try{const value=parseGroupConfiguration(await client.save({request_id:requestId.current,expected_revision:data.revision,group_id:form.group_id,name:form.name,description:form.description,status:form.status,sort_order:form.sort_order,reason:form.reason},controller.signal));if(!controller.signal.aborted){setData(value);setForm(null);setDirty(false);setNotice('分组配置已保存。');}}
  catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'保存失败，请重试。');}
  finally{gate.current=false;if(!controller.signal.aborted)setBusy(false);}
 }
 const moveLabels={top:'置顶',up:'上移',down:'下移',bottom:'置底'};
 async function move(group:OntologyGroup,direction:GroupMove['move']){
  if(!data?.can_manage||gate.current||form||query.trim()||status)return;
  gate.current=true;setBusy(true);setError('');setNotice('');
  const previous=moveRequest.current;
  const change:GroupMove=previous&&previous.group_id===group.group_id&&previous.move===direction&&previous.expected_revision===data.revision?previous:{request_id:crypto.randomUUID().replaceAll('-',''),expected_revision:data.revision,group_id:group.group_id,move:direction,reason:'调整分组顺序：'+moveLabels[direction]};
  moveRequest.current=change;const controller=new AbortController();saving.current=controller;
  try{const value=parseGroupConfiguration(await client.save(change,controller.signal));if(!controller.signal.aborted){setData(value);moveRequest.current=null;setNotice(group.name+'已'+moveLabels[direction]+'。');}}
  catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'移动未确认，请重试。');}
  finally{gate.current=false;if(!controller.signal.aborted)setBusy(false);}
 }
 const entries=data?.groups.filter(g=>(!status||g.status===status)&&(!query.trim()||[g.name,g.description,g.group_id].some(v=>v.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))))||[];
 return <section className="ontology-group-configuration" aria-label="本体分组配置"><p className="text-body-small text-muted-foreground">管理预置分组与自建分组。停用保留历史身份；本体归组在资源业务中管理。</p>
 <div className="flex flex-wrap items-end gap-md"><label>搜索分组<Input aria-label="搜索分组" value={query} onChange={e=>setQuery(e.target.value)} placeholder="名称、说明或标识"/></label><label>状态<NativeSelect aria-label="筛选分组状态" value={status} onChange={e=>setStatus(e.target.value)}><option value="">全部状态</option><option value="active">启用</option><option value="inactive">停用</option></NativeSelect></label><Button variant="outline" disabled={loading||busy||!!form} onClick={()=>{setNotice('');setRefresh(v=>v+1);}}>刷新配置</Button><Button disabled={!data?.can_manage||busy||!!form} onClick={()=>begin()}>新建分组</Button>{data&&<span className="text-label-small text-muted-foreground">配置修订 {data.revision} · {entries.length} 个分组</span>}</div>
 {loading&&<p role="status">正在读取分组配置…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {form&&data&&<form className="ontology-group-form" aria-label="编辑分组配置" onSubmit={e=>{e.preventDefault();void save();}}><h2>{form.group_id?'编辑分组':'新建分组'}</h2><fieldset disabled={busy||!data.can_manage} className="flex flex-col gap-md"><label>分组名称<Input aria-label="分组名称" value={form.name} maxLength={60} required disabled={form.group_id?.startsWith('preset-')} onChange={e=>update({name:e.target.value})}/></label>{form.group_id?.startsWith('preset-')&&<p className="text-label-small text-muted-foreground">预置名称保持固定，可调整说明和启停状态；顺序在清单中移动。</p>}<label>说明<Textarea aria-label="分组说明" value={form.description} maxLength={500} onChange={e=>update({description:e.target.value})}/></label><div className="flex flex-wrap gap-md"><label>状态<NativeSelect aria-label="分组状态" value={form.status} onChange={e=>update({status:e.target.value as 'active'|'inactive'})}><option value="active">启用</option><option value="inactive">停用</option></NativeSelect></label></div>{form.status==='inactive'&&<p className="text-body-small">停用后应停止新增归组，已有归组和历史记录保留。</p>}<label>修改原因<Input aria-label="分组修改原因" value={form.reason} maxLength={500} required onChange={e=>update({reason:e.target.value})}/></label></fieldset><div className="flex gap-sm"><Button type="submit" disabled={busy||!data.can_manage||!dirty||!form.name.trim()||!form.reason.trim()}>{busy?'保存中…':'保存配置'}</Button><Button type="button" variant="outline" disabled={busy} onClick={()=>{setForm(null);setDirty(false);setError('');}}>取消编辑</Button></div></form>}
 {(query.trim()||status)&&<p className="text-label-small text-muted-foreground">清除搜索和筛选后可调整完整分组顺序。</p>}
 {data&&<><div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead className="ontology-group-index">序号</TableHead><TableHead>分组名称 / 标识</TableHead><TableHead>说明</TableHead><TableHead>来源</TableHead><TableHead>状态</TableHead><TableHead data-table-actions>操作</TableHead></TableRow></TableHeader><TableBody>{entries.map((g,index)=><TableRow key={g.group_id}><TableCell className="ontology-group-index">{index+1}</TableCell><TableCell>{g.name}<span className="block text-label-small text-muted-foreground">{g.group_id}</span></TableCell><TableCell>{g.description||'—'}</TableCell><TableCell>{g.origin==='preset'?'预置':'自建'}</TableCell><TableCell><StatusBadge tone={g.status==='active'?'success':'neutral'}>{g.status==='active'?'启用':'停用'}</StatusBadge></TableCell><TableCell data-table-actions><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="ontology-group-action-trigger" aria-label={g.name+'更多操作'} title="更多操作" disabled={busy||!!form||!data.can_manage}><DotsThreeVertical size={24} className="size-icon-lg"/></Button></DropdownMenuTrigger><DropdownMenuContent align="end" aria-label={g.name+'操作面板'}><DropdownMenuGroup><DropdownMenuItem onSelect={()=>begin(g)}><PencilSimple size={16}/>编辑</DropdownMenuItem></DropdownMenuGroup><DropdownMenuSeparator/><DropdownMenuGroup>{(['top','up','down','bottom'] as const).map(direction=>{const Icon={top:ArrowLineUp,up:ArrowUp,down:ArrowDown,bottom:ArrowLineDown}[direction];return <DropdownMenuItem key={direction} disabled={!!query.trim()||!!status||(direction==='top'||direction==='up'?data.groups[0].group_id===g.group_id:data.groups[data.groups.length-1].group_id===g.group_id)} onSelect={()=>void move(g,direction)}><Icon size={16}/>{moveLabels[direction]}</DropdownMenuItem>;})}</DropdownMenuGroup></DropdownMenuContent></DropdownMenu></TableCell></TableRow>)}</TableBody></Table></div>{!entries.length&&<p role="status">没有匹配的分组。</p>}</>}
 </section>;
}
