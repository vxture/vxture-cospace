import {useUnsavedNavigation} from './unsaved-navigation';
import React,{useEffect,useRef,useState} from 'react';
import {InputCoordinates} from './input-coordinates';
import {Button,Field,FieldLabel,Input,Textarea} from '@vxture/design-system';

export type InputPresentation={display_name:string;description:string;intended_use:string;revision:number};
type Description=InputPresentation&{profile:string;space_id:string;input_id:string;original_name:string;history:{revision:number;actor:string;changed_at:string;reason:string;before:InputPresentation;after:InputPresentation}[]};
type Fact={value:unknown;status:string;basis:string;evidence_ref:{member:string;field:string}};
type Facts={profile:string;space_id:string;input_id:string;read_at:string;fields:Record<string,Fact>;roles:{role:string;use:string}[];limitations:string[]};
const factNames:Record<string,string>={unit:'单位',frame_id:'局部坐标基准',recorded_window_ns:'日志记录窗口（ns）',sensor_header_ns:'首帧传感器时刻（ns）',image_window_us:'深度图像时段（μs）',source_clock:'来源时钟说明',scene_alignment:'现场坐标关系',utc_sync:'UTC与同步依据',epsg:'EPSG',scope:'局部范围',axes:'轴语义',point_count:'声明点数',source_basis:'来源依据',original_name:'原文件名',source_description:'来源声明',composition_sources:'组合来源（按优先顺序）',matched_points:'范围内来源点数',retained_points:'派生成果点数',bounds_local:'选定局部范围',voxel_size:'派生体素步长（声明单位）',composition_unit_basis:'组合坐标单位依据'};
const printable=(value:unknown):string=>value==='user_declared_file'?'用户文件声明（未独立核验）':value===null?'未确认':Array.isArray(value)?value.join(' / '):typeof value==='object'?Object.entries(value as Record<string,unknown>).map(([k,v])=>`${k}: ${v}`).join(' · '):String(value);
export function InputDescription({endpoint,space,identity,onSaved,onCoordinatesSaved}:{endpoint:string;space:string;identity:string;onSaved:(value:InputPresentation)=>void;onCoordinatesSaved?:()=>void}){
 const [data,setData]=useState<Description|null>(null),[facts,setFacts]=useState<Facts|null>(null),[editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[factsError,setFactsError]=useState(''),[notice,setNotice]=useState(''),[refresh,setRefresh]=useState(0);
 const [name,setName]=useState(''),[description,setDescription]=useState(''),[use,setUse]=useState(''),[reason,setReason]=useState('');
 const generation=useRef(0);
 useUnsavedNavigation(!!data&&editing&&(name!==data.display_name||description!==data.description||use!==data.intended_use||!!reason),'资料说明');
 useEffect(()=>{
  const run=++generation.current,controller=new AbortController();setData(null);setFacts(null);setError('');setFactsError('');setNotice('');setEditing(false);setBusy(false);setLoading(true);
  const read=async(kind:string)=>{const r=await fetch(`${endpoint}/api/inputs/${identity}/${kind}?`+new URLSearchParams({space_id:space}),{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error(r.status===403?'没有此资料的管理权限。':kind==='facts'?'来源证据暂不可读或已变化，请重新核对资料。':'资料说明暂不可读，请重试。');const body=await r.json();if(body.input_id!==identity||body.space_id!==space||body.profile!==`cospace.input-${kind==='facts'?'facts':'description'}/0.1`)throw Error('返回资料与当前场景不一致。');return body;};
  read('description').then(value=>{if(run===generation.current)setData(value);}).catch(e=>{if(!controller.signal.aborted&&run===generation.current)setError(e.message);}).finally(()=>{if(run===generation.current)setLoading(false);});
  read('facts').then(value=>{if(run===generation.current)setFacts(value);}).catch(e=>{if(!controller.signal.aborted&&run===generation.current)setFactsError(e.message);});
  return()=>{controller.abort();generation.current++;};
 },[endpoint,space,identity,refresh]);
 function edit(){if(!data)return;setName(data.display_name);setDescription(data.description);setUse(data.intended_use);setReason('');setError('');setNotice('');setEditing(true);}
 async function save(event:React.FormEvent){event.preventDefault();if(!data||busy)return;const run=generation.current;setBusy(true);setError('');setNotice('');
  try{const r=await fetch(`${endpoint}/api/inputs/${identity}/description`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:space,expected_revision:data.revision,display_name:name.trim(),description:description.trim(),intended_use:use.trim(),reason:reason.trim()})});
   if(!r.ok)throw Error(r.status===409?'说明已被其他人修改，请重新读取后核对。':r.status===422?'请检查名称、字数及修改原因。':r.status===403?'当前没有保存权限。':'保存未确认，请重新读取核对后再操作。');
   const value:Description=await r.json();if(value.input_id!==identity||value.space_id!==space||value.profile!=='cospace.input-description/0.1')throw Error('返回资料与当前场景不一致。');
   if(run===generation.current){setData(value);setEditing(false);setNotice('说明已保存');onSaved(value);}
  }catch(e){if(run===generation.current)setError(e instanceof Error?e.message:'保存失败');}finally{if(run===generation.current)setBusy(false);}
 }
 return <section className="data-detail-section input-description" aria-label="资料说明与来源信息">
  <InputCoordinates endpoint={endpoint} space={space} identity={identity} onSaved={()=>{setRefresh(v=>v+1);onCoordinatesSaved?.();}}/>
  <div className="flex items-center justify-between gap-sm"><h3>资料说明</h3>{data&&!editing&&<Button size="sm" variant="ghost" onClick={edit}>编辑说明</Button>}</div>
  {loading&&<p role="status">正在读取说明…</p>}{error&&<p role="alert" className="text-destructive">{error}</p>}{notice&&<p role="status" className="text-primary">{notice}</p>}
  {editing&&data?<form onSubmit={save} className="flex flex-col gap-md" aria-label="编辑资料说明">
   <Field><FieldLabel htmlFor="input-display-name">资料名称</FieldLabel><Input id="input-display-name" required maxLength={100} value={name} disabled={busy} onChange={e=>setName(e.target.value)}/></Field>
   <Field><FieldLabel htmlFor="input-description">备注</FieldLabel><Textarea id="input-description" maxLength={500} value={description} disabled={busy} onChange={e=>setDescription(e.target.value)}/></Field>
   <Field><FieldLabel htmlFor="input-intended-use">用途说明</FieldLabel><Textarea id="input-intended-use" maxLength={500} value={use} disabled={busy} onChange={e=>setUse(e.target.value)}/></Field>
   <Field><FieldLabel htmlFor="input-description-reason">修改原因</FieldLabel><Input id="input-description-reason" required maxLength={500} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></Field>
   <div className="flex flex-wrap justify-end gap-sm"><Button size="sm" variant="ghost" disabled={busy} onClick={()=>{setEditing(false);setError('');}}>取消</Button><Button size="sm" type="submit" disabled={busy||!name.trim()||!reason.trim()}>{busy?'保存中…':'保存说明'}</Button></div>
  </form>:data&&<dl className="data-detail-facts"><div><dt>备注</dt><dd className="whitespace-pre-wrap break-words">{data.description||'未填写'}</dd></div><div><dt>用途说明</dt><dd className="whitespace-pre-wrap break-words">{data.intended_use||'未填写'}</dd></div></dl>}
  <Button size="sm" variant="ghost" disabled={busy||loading} onClick={()=>setRefresh(v=>v+1)}>重新读取资料说明</Button>
  {data&&<details className="data-technical-details"><summary>说明修改历史 · {data.revision}</summary><p>原始登记名：{data.original_name}</p>{!data.history.length?<p>暂无修改记录。</p>:data.history.slice().reverse().map(item=><article key={item.revision} className="input-description-event"><p>修订 {item.revision} · {item.actor}</p><time>{new Date(item.changed_at).toLocaleString('zh-CN',{hour12:false})}</time><p>{item.reason}</p>{(['display_name','description','intended_use'] as const).map(k=><p key={k}>{k==='display_name'?'名称':k==='description'?'备注':'用途'}：{item.before[k]||'（空）'} → {item.after[k]||'（空）'}</p>)}</article>)}</details>}
  <h3 className="mt-md">坐标与时间</h3>{factsError&&<p role="alert" className="text-destructive">{factsError}</p>}
  {facts&&<><dl className="data-detail-facts">{Object.entries(facts.fields).map(([key,f])=><div key={key}><dt>{factNames[key]||key}</dt><dd>{printable(f.value)}</dd></div>)}</dl><details className="data-technical-details"><summary>配套资料与证据依据</summary>{facts.roles.map(r=><p key={r.role}><strong>{r.role}</strong> · {r.use}</p>)}{Object.entries(facts.fields).map(([key,f])=><p key={key}>{factNames[key]||key}：{f.evidence_ref.member} · {f.evidence_ref.field}{f.basis==='adapter_interpretation'?'（适配器解释）':''}</p>)}</details><p className="text-label-small text-muted-foreground">{facts.limitations.join('；')}。</p></>}
 </section>;
}
