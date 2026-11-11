import {useUnsavedNavigation,runGuarded} from './unsaved-navigation';
import React,{useEffect,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent,Input,NativeSelect,StatusBadge,Switch,Table,TableHeader,TableBody,TableRow,TableHead,TableCell} from '@vxture/design-system';
import {IdentificationCard,Plus} from '@phosphor-icons/react';
import {recordLink,useRecordNavigation} from './record-navigation';
import {previewEndpoint as endpoint} from './real-space-data';
type Ref={record_id:string;sha256:string};
type Ledger={ref:Ref;record:{record_id:string;space_id:string;title:string;source_system:string;external_id:string;version:string;fields:Record<string,string>}};
type ObjectInfo={object_id:string;properties:Record<string,string>;business_links?:Ledger[]};
const empty={source_system:'',external_id:'',version:'',title:'',asset_code:'',manufacturer:'',model:'',serial_number:''};

export function BusinessAssociations({embedded=false}:{embedded?:boolean}={}){
 const target=useRecordNavigation();
 const [records,setRecords]=useState<Ledger[]>([]),[jobs,setJobs]=useState<{id:string;state:string}[]>([]),[base,setBase]=useState(''),[hash,setHash]=useState(''),[objects,setObjects]=useState<ObjectInfo[]>([]),[bindings,setBindings]=useState<Record<string,Ref>>({});
 const [draft,setDraft]=useState(empty),[loading,setLoading]=useState(false),[reading,setReading]=useState(false),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[ack,setAck]=useState(false),[created,setCreated]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{
  if(!target.space)return;const request=new AbortController();setLoading(true);setError('');setNotice('');setDraft(empty);setRecords([]);setJobs([]);setBase('');
  (async()=>{
   const response=await fetch(`${endpoint}/api/ledger?space_id=${target.space}`,{signal:request.signal});if(!response.ok)throw Error('台账目录暂时无法读取。');const l=await response.json();if(request.signal.aborted)return;if(l.space_id!==target.space)throw Error('台账目录空间绑定不一致。');setRecords(l.records);
   if(embedded){setBase(target.job);return;}
   const responses=await Promise.all([fetch(`${endpoint}/api/builds?space_id=${target.space}`,{signal:request.signal}),fetch(`${endpoint}/api/selection?space_id=${target.space}`,{signal:request.signal})]);
   if(responses.some(r=>!r.ok))throw Error('台账关联工作面无法读取。');const [j,selected]=await Promise.all(responses.map(r=>r.json()));if(request.signal.aborted)return;const available=j.jobs.filter((job:{state:string})=>job.state==='succeeded');setJobs(available);setBase(available.some((job:{id:string})=>job.id===target.job)?target.job:selected.candidate_id||'');
  })().catch(e=>{if(!request.signal.aborted)setError(e.message);}).finally(()=>{if(!request.signal.aborted)setLoading(false);});return()=>request.abort();
 },[target.space,target.job,revision,embedded]);
 useEffect(()=>{
  const request=new AbortController();setHash('');setObjects([]);setBindings({});setAck(false);setCreated('');
  if(!base){setReading(false);return()=>request.abort();}setReading(true);setError('');
  Promise.all([fetch(`${endpoint}/candidates/${base}/api/anchor?point_index=0`,{signal:request.signal}),fetch(`${endpoint}/candidates/${base}/api/objects`,{signal:request.signal})]).then(async ([a,o])=>{
   if(!a.ok||!o.ok)throw Error('该候选尚无对象标注或快照不可用，请先完成对象标注。');
   const [anchor,body]=await Promise.all([a.json(),o.json()]);if(request.signal.aborted)return;
   if(anchor.candidate_id!==base||body.model_id!==base||body.space_id!==target.space)throw Error('候选对象空间绑定不一致。');
   setHash(anchor.model_manifest_sha256);setObjects(body.objects);setBindings(Object.fromEntries(body.objects.filter((obj:ObjectInfo)=>obj.business_links?.length).map((obj:ObjectInfo)=>[obj.object_id,obj.business_links![0].ref])));
  }).catch(e=>{if(!request.signal.aborted)setError(e.message);}).finally(()=>{if(!request.signal.aborted)setReading(false);});return()=>request.abort();
 },[base]);
 async function register(e:React.FormEvent){
  e.preventDefault();setSaving(true);setError('');setNotice('');
  try{
   const {asset_code,manufacturer,model,serial_number,...values}=draft;
   const response=await fetch(`${endpoint}/api/ledger`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...values,space_id:target.space,fields:{asset_code,manufacturer,model,serial_number}})});
   const result=await response.json();if(!response.ok)throw Error(result.detail==='ledger_version_conflict'?'同一系统、标识和版本已有不同内容，请使用新版本。':`台账登记失败：${typeof result.detail==='string'?result.detail:'请检查字段。'}`);
   if(result.record?.space_id!==target.space)throw Error('台账登记响应空间不一致。');
   setRecords(current=>[...current.filter(item=>item.ref.record_id!==result.ref.record_id),result]);setNotice(result.created?'台账版本已登记，尚未绑定或发布。':'相同台账版本已存在，已保留原记录。');setDraft(empty);
  }catch(e){setError(e instanceof Error?e.message:'台账登记失败');}finally{setSaving(false);}
 }
 async function save(){
  if(!hash||!ack)return;setBusy(true);setError('');setCreated('');
  try{
   const response=await fetch(`${endpoint}/api/business-candidates`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:target.space,base_candidate_id:base,base_manifest_sha256:hash,bindings:Object.entries(bindings).map(([object_id,ledger_ref])=>({object_id,ledger_ref}))})});
   const body=await response.json();if(!response.ok)throw Error(`关联候选生成失败：${typeof body.detail==='string'?body.detail:'请核对台账版本和对象。'}`);
   if(body.space_id!==target.space||body.base_candidate_id!==base)throw Error('关联候选响应绑定不一致。');setCreated(body.id);setAck(false);
  }catch(e){setError(e instanceof Error?e.message:'生成失败');}finally{setBusy(false);}
 }
 const available=new Map(records.map(r=>[r.ref.record_id,r]));for(const obj of objects)for(const link of obj.business_links||[])if(available.get(link.ref.record_id)?.ref.sha256!==link.ref.sha256)available.set(link.ref.record_id,link);
 const initial=JSON.stringify(objects.flatMap(obj=>(obj.business_links||[]).map(link=>[obj.object_id,link.ref])).sort());
 const changed=initial!==JSON.stringify(Object.entries(bindings).sort());
 useUnsavedNavigation((!!hash&&changed&&!created)||Object.values(draft).some(Boolean),'台账与对象绑定',{discard:()=>{setDraft(empty);setBindings(Object.fromEntries(objects.filter(obj=>obj.business_links?.length).map(obj=>[obj.object_id,obj.business_links![0].ref])));setAck(false);}});
 if(!target.space)return <p className="text-body-small text-muted-foreground">选择工程空间后可登记台账并建立对象绑定。</p>;
 return <Card className={`module-surface ${embedded?'association-editor':''}`} aria-label="对象与业务台账">{!embedded&&<CardHeader><div className="flex flex-wrap items-center justify-between gap-sm"><CardTitle>对象与业务台账</CardTitle><Button size="sm" variant="secondary" disabled={busy||saving||loading||reading} onClick={()=>void runGuarded(()=>setRevision(v=>v+1))}>重新读取</Button></div></CardHeader>}<CardContent className="flex flex-col gap-lg">
 <p className="text-body-small text-muted-foreground">对象引用固定台账版本，生成新候选后仍需人工核对与发布。当前为本机设备台账登记，未对接外部系统。</p>

 {notice&&<p role="status" className="text-body-small">{notice}</p>}
 {!embedded&&<><label className="flex flex-col gap-sm text-body-small">关联基础候选<NativeSelect aria-label="业务关联基础候选" value={base} disabled={busy||saving||loading} onChange={e=>{const value=e.target.value;e.target.value=base;void runGuarded(()=>setBase(value));}}><option value="">请选择已有对象标注的候选</option>{jobs.map(job=><option key={job.id} value={job.id}>{job.id}</option>)}</NativeSelect></label></>}
 {(reading||loading)&&<p role="status" className="text-body-small">正在读取对象与固定台账…</p>}
 {!!records.length&&<details><summary className="cursor-pointer text-body-small">已登记台账 · {records.length} 个版本</summary><div className="mt-md flex flex-col gap-md">{records.map(item=><div key={item.ref.record_id} className="border-b border-border pb-sm"><p className="text-body-small break-all">{item.record.title} · {item.record.source_system}/{item.record.external_id} · V{item.record.version}</p><p className="text-label-small text-muted-foreground break-all">{item.ref.record_id} · {item.ref.sha256}</p><p className="text-label-small text-muted-foreground break-all">{Object.entries(item.record.fields).filter(([,v])=>v).map(([k,v])=>`${k}: ${v}`).join(' · ')||'无补充设备字段'} · 待核实</p></div>)}</div></details>}
 {!loading&&!error&&!records.length&&<p className="text-body-small text-muted-foreground">本空间尚无登记台账；先登记一个固定版本，再选择对象建立绑定。</p>}
 {objects.length>0&&<section aria-label="对象业务绑定清单" className="flex min-w-0 flex-col gap-lg"><div className="association-toolbar"><strong className="text-body-small">对象业务绑定</strong><span className="text-label-small text-muted-foreground">{Object.keys(bindings).length} 个对象已关联{changed?' · 未保存':''}</span></div><div className="association-table-scroll"><Table><TableHeader><TableRow><TableHead>序号</TableHead><TableHead>对象名称</TableHead><TableHead>固定台账版本</TableHead><TableHead>来源系统</TableHead><TableHead>操作</TableHead></TableRow></TableHeader><TableBody>{objects.map((obj,i)=>{const selected=bindings[obj.object_id],item=selected?available.get(selected.record_id):null;return <TableRow key={obj.object_id}><TableCell>{i+1}</TableCell><TableCell className="association-name-cell"><strong>{obj.properties.name||obj.object_id}</strong><small className="block text-muted-foreground">{obj.object_id}</small></TableCell><TableCell><NativeSelect aria-label={`业务绑定 ${obj.object_id}`} value={selected?.record_id||''} disabled={busy||saving} onChange={e=>{const value=available.get(e.target.value);setBindings(current=>{const next={...current};if(value)next[obj.object_id]=value.ref;else delete next[obj.object_id];return next;});setAck(false);setCreated('');}}><option value="">未关联台账</option>{Array.from(available.values()).map(record=><option key={record.ref.record_id} value={record.ref.record_id}>{record.record.title} · {record.record.version}</option>)}</NativeSelect>{item&&<small className="block text-muted-foreground">{records.some(r=>r.ref.record_id===item.ref.record_id&&r.ref.sha256===item.ref.sha256)?'固定版本 · 待核实':'来自候选保存快照'}</small>}</TableCell><TableCell>{item?.record.source_system||'—'}</TableCell><TableCell><Button variant="ghost" size="sm" disabled={!selected||busy||saving} onClick={()=>{setBindings(current=>{const next={...current};delete next[obj.object_id];return next;});setAck(false);setCreated('');}}>解除关联</Button></TableCell></TableRow>;})}</TableBody></Table></div></section>}
 {!loading&&!reading&&!error&&!objects.length&&<p className="association-empty-list"><IdentificationCard size={24} className="mx-auto mb-sm"/>当前来源尚无对象。请先在对象管理中添加对象，保存后继续关联。</p>}

 <details><summary className="cursor-pointer text-body-small font-medium">登记设备台账版本</summary><form onSubmit={register} className="mt-lg flex flex-col gap-md"><div className="grid grid-cols-1 gap-md sm:grid-cols-2">{(['source_system','external_id','version','title'] as const).map(key=><label className="flex flex-col gap-sm text-body-small" key={key}>{{source_system:'来源系统',external_id:'业务标识',version:'台账版本',title:'台账名称'}[key]}<Input aria-label={`台账 ${key}`} value={draft[key]} onChange={e=>setDraft({...draft,[key]:e.target.value})} maxLength={key==='source_system'?80:key==='version'?40:100} required disabled={saving||busy}/></label>)}</div><div className="grid grid-cols-1 gap-md sm:grid-cols-2">{(['asset_code','manufacturer','model','serial_number'] as const).map(key=><label className="flex flex-col gap-sm text-body-small" key={key}>{{asset_code:'资产编码',manufacturer:'制造商',model:'型号',serial_number:'序列号'}[key]}<Input aria-label={`台账 ${key}`} value={draft[key]} onChange={e=>setDraft({...draft,[key]:e.target.value})} maxLength={100} disabled={saving||busy}/></label>)}</div><Button type="submit" className="self-start" disabled={saving||busy}>{saving?'登记中…':'登记固定台账版本'}</Button><p className="text-label-small text-muted-foreground">同一来源系统、业务标识和版本内容不可覆盖；更新请登记新版本。登记不代表台账已核实。</p></form></details>
 {error&&<div role="alert" className="publication-message"><span>{error}</span><Button variant="ghost" size="sm" disabled={busy||saving||loading||reading} onClick={()=>{if(!hash)setRevision(v=>v+1);else void runGuarded(()=>setRevision(v=>v+1));}}>重新读取</Button></div>}
 <label className="flex items-center gap-sm text-body-small"><Switch aria-label="确认完整业务绑定集" checked={ack} onCheckedChange={setAck} disabled={!hash||!changed||busy||saving}/>确认本次完整绑定集；取消选择会在新候选中解除绑定，现场含义仍待核实</label>
 <Button className="self-start" disabled={busy||saving||reading||!hash||!changed||!ack} onClick={save}>{busy?'保存中…':'保存业务候选'}</Button>
 {created&&<div role="status" className="flex flex-wrap gap-sm"><StatusBadge tone="success">业务关联候选已保存</StatusBadge><span className="text-label-small break-all">{created}</span><Button asChild size="sm" variant="secondary"><a href={recordLink('association',{job:created,tab:'overview'})}>继续关联</a></Button><Button asChild size="sm"><a href={recordLink('build',{job:created})}>前往构建中心核对</a></Button><p className="w-full text-label-small text-muted-foreground">尚未选择或发布；原候选、几何和既有发布保持固定。</p></div>}
 </CardContent></Card>;
}
