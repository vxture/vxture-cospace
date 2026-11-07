import {useUnsavedNavigation,runGuarded} from './unsaved-navigation';
import React,{useEffect,useRef,useState} from 'react';
import {Button,Input,NativeSelect} from '@vxture/design-system';
type Coordinates={unit:'m';frame_id:string;axes:string[];scope:'sensor_local'|'scene_local';scene_alignment:'unverified'};
type Revision={revision:number;before:Coordinates;coordinates:Coordinates;actor:string;changed_at:string;reason:string};
type State={profile:string;input_id:string;space_id:string;supported:boolean;revision:number;coordinates:Coordinates;history:Revision[]};
export function InputCoordinates({endpoint,space,identity,onSaved}:{endpoint:string;space:string;identity:string;onSaved:()=>void}){
 const [data,setData]=useState<State|null>(null),[draft,setDraft]=useState<Coordinates|null>(null),[editing,setEditing]=useState(false),[reason,setReason]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[reload,setReload]=useState(0),[impact,setImpact]=useState<Record<string,number>|null>(null);
 useUnsavedNavigation(!!data&&editing&&(JSON.stringify(draft)!==JSON.stringify(data.coordinates)||!!reason),'坐标说明',{discard:()=>{setEditing(false);setDraft(data?.coordinates||null);setReason('');},save:()=>save(),canSave:!busy&&!!impact&&!!reason.trim()});
 const generation=useRef(0),gate=useRef(false),requestId=useRef(''),abort=useRef<AbortController|null>(null);
 useEffect(()=>{const controller=new AbortController(),run=++generation.current;abort.current?.abort();setData(null);setDraft(null);setEditing(false);setBusy(false);setError('');setNotice('');gate.current=false;
  fetch(`${endpoint}/api/inputs/${identity}/coordinates?${new URLSearchParams({space_id:space})}`,{signal:controller.signal,cache:'no-store'}).then(async r=>{if(r.status===404)return null;if(!r.ok)throw Error('坐标说明暂不可读，请重试。');const value:State=await r.json();if(value.profile!=='cospace.input-coordinates/0.1'||value.space_id!==space||value.input_id!==identity||!Number.isInteger(value.revision)||!Array.isArray(value.history))throw Error('坐标说明与当前资料不一致。');return value;}).then(value=>{if(run===generation.current)setData(value);}).catch(e=>{if(!controller.signal.aborted&&run===generation.current)setError(e.message);});
  return()=>{controller.abort();abort.current?.abort();generation.current++;};
 },[endpoint,space,identity,reload]);
 async function edit(){if(!data||!data.supported)return;const run=generation.current,controller=new AbortController();abort.current=controller;setDraft(structuredClone(data.coordinates));setReason('');setError('');setNotice('');setImpact(null);setEditing(true);requestId.current='';
  try{const r=await fetch(`${endpoint}/api/artifact-impact?${new URLSearchParams({space_id:space,artifact:'input:'+identity})}`,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('引用影响无法确认，请重新读取后再编辑。');const value=await r.json();if(value.space_id!==space||value.target?.key!=='input:'+identity||value.issues?.length)throw Error('引用记录存在缺口，请先核查。');if(run===generation.current)setImpact(value.reference_counts);}catch(e){if(run===generation.current&&!controller.signal.aborted)setError((e as Error).message);}
 }
 function update(value:Coordinates){setDraft(value);requestId.current='';setError('');}
 async function save(event?:React.FormEvent){event?.preventDefault();if(!data||!draft||!reason.trim()||!impact||gate.current)return false;gate.current=true;const run=generation.current;setBusy(true);setError('');if(!requestId.current)requestId.current=crypto.randomUUID().replaceAll('-','');
  const controller=new AbortController();abort.current=controller;
  try{const r=await fetch(`${endpoint}/api/inputs/${identity}/coordinates`,{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({space_id:space,expected_revision:data.revision,request_id:requestId.current,coordinates:draft,reason:reason.trim()})});const value=await r.json();if(!r.ok)throw Error(r.status===409?'保存未完成：修订、资料状态或来源发生变化，请重新读取核查。':'保存未确认，可重试相同操作或重新读取核查。');if(value.profile!=='cospace.input-coordinates/0.1'||value.input_id!==identity||value.space_id!==space)throw Error('保存回执与当前资料不一致。');
   if(run===generation.current){setData(value);setEditing(false);setNotice('已保存修改历史。请重新预检；现有任务和发布保留原说明。');onSaved();}
   return true;
  }catch(e){if(run===generation.current&&!controller.signal.aborted)setError((e as Error).message);return false;}finally{gate.current=false;if(run===generation.current)setBusy(false);}
 }
 if(!data?.supported&&!error)return null;
 return <section className="data-detail-section" aria-label="坐标说明编辑与历史"><div className="flex items-center justify-between gap-sm"><h3>坐标说明</h3>{data?.supported&&!editing&&<Button size="sm" variant="ghost" onClick={edit}>编辑坐标说明</Button>}</div>
  {error&&<p role="alert" className="text-destructive">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {editing&&draft&&<form aria-label="编辑坐标说明" onSubmit={save} className="flex min-w-0 flex-col gap-md"><p>修改保存在同一份资料中，原点云数值不变。已有成果需要重新构建并发布新版本才能采用修改。</p>
   {impact&&<p>影响范围：批次 {impact.batch} · 构建 {impact.job} · 候选 {impact.candidate} · 发布 {impact.publication}</p>}
   <fieldset disabled={busy} className="flex min-w-0 flex-col gap-md"><label>局部坐标系<Input aria-label="修改局部坐标系" value={draft.frame_id} required maxLength={100} onChange={e=>update({...draft,frame_id:e.target.value})}/></label>
   <label>局部范围<NativeSelect aria-label="修改局部范围" value={draft.scope} onChange={e=>update({...draft,scope:e.target.value as Coordinates['scope']})}><option value="sensor_local">传感器局部</option><option value="scene_local">场景局部</option></NativeSelect></label>
   {['X','Y','Z'].map((a,i)=><label key={a}>{a}轴语义<Input aria-label={`修改${a}轴语义`} value={draft.axes[i]} required maxLength={40} onChange={e=>update({...draft,axes:draft.axes.map((v,n)=>n===i?e.target.value:v)})}/></label>)}
   <p>单位：米 · 场景对齐：未核验</p><label>修改原因<Input aria-label="坐标修改原因" value={reason} required maxLength={500} onChange={e=>{setReason(e.target.value);requestId.current='';}}/></label></fieldset>
   <div className="flex flex-wrap justify-end gap-sm"><Button type="button" variant="ghost" size="sm" disabled={busy} onClick={()=>{abort.current?.abort();setEditing(false);}}>取消</Button><Button type="submit" size="sm" disabled={busy||!impact||!reason.trim()}>{busy?'保存中…':'保存坐标说明'}</Button></div></form>}
  {!editing&&data?.supported&&<p className="break-words">{data.coordinates.frame_id} · {data.coordinates.axes.join(' / ')} · {data.coordinates.scope==='sensor_local'?'传感器局部':'场景局部'} · 修订 {data.revision}</p>}
  {!!data?.history.length&&<details className="data-technical-details"><summary>坐标说明修改历史（{data.history.length}）</summary>{[...data.history].reverse().map(e=><div key={e.revision} className="break-words"><p>修订 {e.revision} · {new Date(e.changed_at).toLocaleString('zh-CN',{hour12:false})} · {e.actor}</p><p>{e.reason}</p><p>{e.before.frame_id} / {e.before.axes.join(' / ')} / {e.before.scope} → {e.coordinates.frame_id} / {e.coordinates.axes.join(' / ')} / {e.coordinates.scope}</p></div>)}</details>}
  <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={()=>void runGuarded(()=>setReload(v=>v+1))}>重新读取坐标说明</Button>
 </section>;
}
