import React,{useEffect,useRef,useState} from 'react';
import {DotsThreeVertical,Eye,FolderSimple} from '@phosphor-icons/react';
import {Button,Input,StatusBadge,NativeSelect,Combobox,Checkbox,Drawer,Table,TableHeader,TableBody,TableRow,TableHead,TableCell,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator} from '@vxture/design-system';
import {OntologyLibrary,type LibrarySelection} from './library';
import {parseLibrary,type Library} from './contract';
import {parseDirectory,type DirectoryClient,type DirectoryPage,type MembershipChange,type ResourceSummary} from './directory-contract';

export function OntologyDirectory({client,category,selection,onSelect,refresh=0,onDirtyChange,onBack,renderDetail}:{client:DirectoryClient;category:string;selection:LibrarySelection;onSelect:(s:LibrarySelection)=>void;refresh?:number;onDirtyChange?:(dirty:boolean)=>void;onBack?:()=>void;renderDetail?:(library:Library)=>React.ReactNode}){
 const [query,setQuery]=useState(''),[group,setGroup]=useState(''),[sort,setSort]=useState('title'),[page,setPage]=useState(1),[generation,setGeneration]=useState(0);
 const [data,setData]=useState<DirectoryPage|null>(null),[library,setLibrary]=useState<Library|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [editing,setEditing]=useState<ResourceSummary|null>(null),[chosen,setChosen]=useState<string[]>([]),[busy,setBusy]=useState(false);
 const snapshot=useRef(''),request=useRef<MembershipChange|null>(null),gate=useRef(false),saving=useRef<AbortController|null>(null);
 const dirty=!!editing&&[...chosen].sort((a,b)=>a.localeCompare(b)).join('|')!==[...editing.group_ids].sort((a,b)=>a.localeCompare(b)).join('|');
 useEffect(()=>{onDirtyChange?.(dirty);return()=>onDirtyChange?.(false);},[dirty,onDirtyChange]);
 useEffect(()=>()=>saving.current?.abort(),[]);
 useEffect(()=>{snapshot.current='';setPage(1);setEditing(null);setNotice('');},[category]);
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');setLibrary(null);
  const load=async()=>{
   if(selection.moduleId){
    const directory=parseDirectory(await client.list({layer:'',q:selection.moduleId,group:'',sort:'id',page:'1',page_size:'50'},controller.signal));
    const ref=directory.items.find(i=>i.reference.module_id===selection.moduleId)?.reference;
    if(!ref)throw Error('本体不存在，请返回清单。');
    const value=parseLibrary(await client.definition(ref,controller.signal));
    if(!controller.signal.aborted)setLibrary(value);
   }else{
    const value=parseDirectory(await client.list({layer:category==='all'?'':category,q:query,group,sort,page:String(page),page_size:'10',...(snapshot.current&&page>1?{snapshot:snapshot.current}:{})},controller.signal));
    if(!controller.signal.aborted){setData(value);snapshot.current=value.snapshot;}
   }
  };
  void load().catch(e=>{if(!controller.signal.aborted){setData(null);setError(e instanceof Error?e.message:'目录读取失败。');}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[client,category,query,group,sort,page,generation,refresh,selection.moduleId]);
 function reset(){snapshot.current='';setPage(1);setGeneration(v=>v+1);}
 async function save(){
  if(!editing||!data?.can_group||!dirty||gate.current)return;
  gate.current=true;setBusy(true);setError('');
  const change=request.current||{request_id:crypto.randomUUID().replaceAll('-',''),module_id:editing.reference.module_id,expected_revision:editing.revision,group_ids:chosen};request.current=change;
  const controller=new AbortController();saving.current=controller;
  try{await client.assign(change,controller.signal);if(!controller.signal.aborted){request.current=null;setEditing(null);setNotice('本体归组已保存。');reset();}}
  catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'归组保存失败，请重试。');}
  finally{gate.current=false;if(!controller.signal.aborted)setBusy(false);}
 }
 const filterChange=(action:()=>void)=>{action();snapshot.current='';setPage(1);setNotice('');};
 if(selection.moduleId)return <>{loading&&<p role="status">正在读取固定版本定义…</p>}{error&&<p role="alert">{error}</p>}{library&&(renderDetail?renderDetail(library):<OntologyLibrary library={library} selection={selection} onSelect={onSelect} completeLibrary={false} onBack={onBack}/>)}</>;
 return <section className="ontology-catalog ontology-resource-directory" aria-label="本体清单">
  <fieldset disabled={!!editing} className="ontology-list-toolbar">
   <span className="ontology-directory-count">共 {data?.groups.length??'—'} 组，{data?.total??'—'} 项</span><label className="ontology-toolbar-search"><span className="sr-only">搜索本体</span><Input aria-label="搜索本体" placeholder="名称、标识、概念或属性" maxLength={160} value={query} onChange={e=>filterChange(()=>setQuery(e.target.value))}/></label>
   <label className="ontology-toolbar-group"><span className="sr-only">分组</span><Combobox value={group||'all'} disabled={!!editing} onValueChange={value=>filterChange(()=>setGroup(value==='all'?'':value))} placeholder="全部分组" searchPlaceholder="搜索分组" emptyText="没有匹配的分组" items={[{value:'all',label:'全部分组'},{value:'ungrouped',label:'未归组'},...(data?.groups||[]).map(g=>({value:g.group_id,label:g.name+(g.status==='inactive'?'（停用）':'')}))]}/></label>
   <label className="ontology-toolbar-sort"><span className="sr-only">排序</span><NativeSelect aria-label="本体排序" value={sort} onChange={e=>filterChange(()=>setSort(e.target.value))}><option value="title">按名称排序</option><option value="id">按标识排序</option></NativeSelect></label>
  </fieldset>
  {error&&!editing&&<p role="alert">{error} <Button variant="link" onClick={reset}>重新读取目录</Button></p>}{notice&&<p role="status">{notice}</p>}{loading&&<p role="status">正在读取本体目录…</p>}
  <Drawer open={!!editing} onClose={()=>{if(!busy){setEditing(null);request.current=null;setError('');}}} side="right" width="md" title="调整分组" description={editing?.title} closeLabel="关闭调整分组" className="ontology-membership-drawer" footer={<div className="ontology-membership-footer"><Button variant="outline" disabled={busy} onClick={()=>{setEditing(null);request.current=null;setError('');}}>取消</Button><Button disabled={!dirty||busy} onClick={()=>void save()}>{busy?'保存中…':'保存归组'}</Button></div>}>
   {editing&&data&&<form id="ontology-membership-form" aria-label="本体归组" onSubmit={e=>{e.preventDefault();void save();}}><p className="ontology-membership-description">选择此本体所属的分组，可选择多个。</p><fieldset disabled={busy} className="ontology-membership-options">{data.groups.map(g=><label key={g.group_id}><Checkbox aria-label={g.name} checked={chosen.includes(g.group_id)} disabled={g.status==='inactive'&&!editing.group_ids.includes(g.group_id)} onCheckedChange={checked=>{request.current=null;setChosen(old=>checked===true?[...old,g.group_id]:old.filter(id=>id!==g.group_id));}}/><span>{g.name}{g.status==='inactive'?'（停用）':''}</span></label>)}</fieldset>{error&&<p role="alert" className="ontology-membership-error">{error}</p>}</form>}
  </Drawer>
  {data&&!loading&&<><div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead className="ontology-catalog-index">序号</TableHead><TableHead>本体名称 / 标识</TableHead><TableHead>分组</TableHead><TableHead>层级</TableHead><TableHead>概念 / 关系</TableHead><TableHead>版本</TableHead><TableHead data-table-actions>操作</TableHead></TableRow></TableHeader><TableBody>{data.items.map((i,index)=><TableRow key={i.reference.module_id}><TableCell className="ontology-catalog-index">{(data.page-1)*data.page_size+index+1}</TableCell><TableCell><div className="ontology-resource-name"><Button className="ontology-resource-title" disabled={!!editing} variant="link" onClick={()=>onSelect({moduleId:i.reference.module_id})}>{i.title}</Button><StatusBadge tone="warning">草案</StatusBadge></div><span className="block ontology-identity">{i.reference.module_id}</span><span className="ontology-resource-description text-muted-foreground" title={i.description}>{i.description}</span></TableCell><TableCell>{i.group_ids.length?i.group_ids.map(id=>{const g=data.groups.find(g=>g.group_id===id)!;return <span key={id} className="ontology-resource-group">{g.name}{g.status==='inactive'?'（停用）':''}</span>;}):'未归组'}</TableCell><TableCell>{i.layer==='core'?'通用核心':'领域本体'}</TableCell><TableCell>{i.concept_count} / {i.relation_count}</TableCell><TableCell><span className="ontology-resource-version">{i.reference.version}</span><span className="ontology-resource-published" title="发布日期">{i.published_at?new Date(i.published_at).toLocaleDateString("zh-CN"):"未发布"}</span></TableCell><TableCell data-table-actions><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="ontology-catalog-action-trigger" aria-label={i.title+'更多操作'} disabled={!!editing}><DotsThreeVertical size={24} className="size-icon-lg"/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={()=>onSelect({moduleId:i.reference.module_id})}><Eye size={16}/>查看本体</DropdownMenuItem>{data.can_group&&<><DropdownMenuSeparator/><DropdownMenuItem onSelect={()=>{request.current=null;setEditing(i);setChosen(i.group_ids);setNotice('');setError('');}}><FolderSimple size={16}/>调整分组</DropdownMenuItem></>}</DropdownMenuContent></DropdownMenu></TableCell></TableRow>)}</TableBody></Table></div>{!data.items.length&&<p role="status">没有匹配的本体，请调整筛选条件。</p>}<footer className="ontology-list-pagination"><span>第 {data.page} / {Math.max(1,Math.ceil(data.total/data.page_size))} 页 · 每页 {data.page_size} 条</span><Button variant="outline" disabled={!!editing||data.page===1} onClick={()=>setPage(data.page-1)}>上一页</Button><Button variant="outline" disabled={!!editing||data.page*data.page_size>=data.total} onClick={()=>setPage(data.page+1)}>下一页</Button></footer></>}
 </section>;
}
