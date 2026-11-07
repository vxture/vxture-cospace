import {useUnsavedNavigation} from './unsaved-navigation';
import React,{useEffect,useState} from 'react';
import {Button,Checkbox,Field,FieldLabel,Input,StatusBadge} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {inputFormat} from './input-format';
type Source={id:string;label:string;format:string;enabled:boolean;needs_confirmation:boolean};
type Change={revision:number;actor:string;reason:string;changed_at:string;before:string[];after:string[]};
type Settings={space_id:string;revision:number;catalog_sha256:string;can_manage:boolean;catalog:Source[];sources:Source[];unavailable_source_ids:string[];history:Change[]};
export function SourceSettings({spaceId,onSaved,onImport}:{spaceId:string;onSaved?:()=>void;onImport?:()=>void}){
 const [data,setData]=useState<Settings|null>(null),[chosen,setChosen]=useState<string[]>([]),[reason,setReason]=useState('');
 const [loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[refresh,setRefresh]=useState(0);
 useEffect(()=>{let active=true;setData(null);setError('');setNotice('');setReason('');setLoading(false);
  if(!spaceId)return;setLoading(true);
  fetch(`${endpoint}/api/source-settings?`+new URLSearchParams({space_id:spaceId}),{cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'无权查看此空间的资料来源。':'来源配置暂不可用，请重新读取。');
   const value:Settings=await r.json();if(active){setData(value);setChosen(value.sources.map(s=>s.id));}
  }).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};
 },[spaceId,refresh]);
 async function save(e:React.FormEvent){e.preventDefault();if(!data||busy)return;setBusy(true);setError('');setNotice('');
  try{const r=await fetch(`${endpoint}/api/source-settings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:spaceId,expected_revision:data.revision,catalog_sha256:data.catalog_sha256,enabled_source_ids:chosen,reason:reason.trim()})});
   if(!r.ok)throw Error(r.status===409?'配置或来源清单已更新，请重新读取后核对。':r.status===403?'当前无来源配置权限，未保存。':'保存失败，请重新读取确认。');
   const value:Settings=await r.json();setData(value);setChosen(value.sources.map(s=>s.id));setReason('');setNotice('来源配置已保存，可继续导入资料。');onSaved?.();
  }catch(e){setError(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
 }
 const dirty=!!data&&(JSON.stringify([...chosen].sort())!==JSON.stringify(data.sources.map(s=>s.id).sort())||data.unavailable_source_ids.length>0);
 useUnsavedNavigation(!!data&&JSON.stringify([...chosen].sort())!==JSON.stringify(data.sources.map(s=>s.id).sort()),'来源配置');
 return <section aria-label="空间资料来源配置" className="flex min-w-0 flex-col gap-lg">
  <div className="flex flex-wrap items-start justify-between gap-md"><div><h2 className="text-heading-2">资料来源</h2><p className="mt-sm text-body-small text-muted-foreground">为空间选择可登记的封存资料。登记后再预检、构建。</p></div><Button variant="outline" disabled={busy||loading||!spaceId} onClick={()=>setRefresh(v=>v+1)}>重新读取来源</Button></div>
  {!spaceId&&<p className="text-body-small text-muted-foreground">请先选择空间。</p>}
  {loading&&<p role="status">正在读取来源配置…</p>}{error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}{notice&&<p role="status" className="text-body-small text-primary">{notice}</p>}
  {data&&<><div className="flex flex-wrap items-center gap-md"><StatusBadge tone={data.can_manage?'info':'neutral'}>{data.can_manage?'可配置':'只读'}</StatusBadge><span className="text-label-small text-muted-foreground">修订 {data.revision} · 已启用 {data.sources.length} 项</span></div>
   {data.can_manage?<form onSubmit={save} className="flex flex-col gap-lg">
    <div className="flex flex-col divide-y divide-border">{data.catalog.map(source=><label key={source.id} className="flex cursor-pointer items-start gap-md py-lg"><Checkbox aria-label={`启用来源 ${source.label}`} className="mt-xs shrink-0" checked={chosen.includes(source.id)} disabled={busy} onCheckedChange={checked=>setChosen(old=>checked===true?[...old,source.id]:old.filter(id=>id!==source.id))}/><span className="min-w-0"><span className="text-body-small font-medium">{source.label}</span><span className="mt-xs block text-label-small text-muted-foreground break-words">{inputFormat(source.format)} · {source.id}</span>{source.needs_confirmation&&<span className="mt-xs block text-label-small text-destructive">来源已调整，需重新确认后启用。</span>}</span></label>)}</div>
    {!data.catalog.length&&<p className="text-body-small text-muted-foreground">服务端尚未配置可选来源，请联系部署管理员。</p>}
    {data.unavailable_source_ids.length>0&&<p className="text-body-small text-destructive">部分原来源已移除或调整，目前不能登记。请核对本次选择后保存。</p>}
    <Field><FieldLabel htmlFor="source-change-reason">来源修改原因</FieldLabel><Input id="source-change-reason" value={reason} maxLength={500} required disabled={busy} placeholder="说明启用或停用来源的原因" onChange={e=>setReason(e.target.value)}/></Field>
    <div className="flex justify-end"><Button type="submit" disabled={busy||!dirty||!reason.trim()}>{busy?'保存中…':'保存来源配置'}</Button></div>
   </form>:<div className="flex flex-col gap-md">{data.sources.map(source=><div key={source.id}><p className="text-body-small">{source.label}</p><p className="text-label-small text-muted-foreground">{inputFormat(source.format)}</p></div>)}{!data.sources.length&&<p className="text-body-small text-muted-foreground">当前空间暂无启用的来源，请联系空间管理员配置。</p>}</div>}
   {onImport&&<div className="flex flex-wrap items-center justify-between gap-md border-t border-border pt-lg"><p className="text-body-small text-muted-foreground">保存来源后，继续为当前场景导入资料。</p><Button disabled={busy||dirty||!data.sources.length} onClick={onImport}>继续导入资料</Button></div>}
   <p className="text-label-small text-muted-foreground">停用来源会阻止新的登记。已有资料和构建成果的使用状态在各自目录管理；登记时仍完整核验文件。</p>
   {data.can_manage&&<section aria-label="来源配置修改历史" className="flex flex-col gap-md border-t border-border pt-lg"><h3 className="text-body-small font-medium">修改历史</h3>{!data.history.length&&<p className="text-label-small text-muted-foreground">暂无修改记录。</p>}{data.history.slice().reverse().map(event=><article key={event.revision} className="rounded-md border border-border p-lg text-body-small"><div className="flex flex-wrap justify-between gap-sm"><span>修订 {event.revision} · {event.actor}</span><time className="text-label-small text-muted-foreground" dateTime={event.changed_at}>{new Date(event.changed_at).toLocaleString('zh-CN',{hour12:false})}</time></div><p className="mt-sm break-words">{event.reason}</p><p className="mt-sm break-words text-label-small text-muted-foreground">启用来源：{event.before.join('、')||'无'} → {event.after.join('、')||'无'}</p></article>)}</section>}
  </>}
 </section>;
}
