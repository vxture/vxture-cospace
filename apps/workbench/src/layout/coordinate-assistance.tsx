import React,{useEffect,useRef,useState} from 'react';
import {Button,Textarea,StatusBadge} from '@vxture/design-system';
import {validateCoordinateSuggestion,suggestionReason,type CoordinateSuggestion} from './coordinate-assistance-contract';

const names:Record<string,string>={right:'右',left:'左',forward:'前',backward:'后',up:'上',down:'下',east:'东',west:'西',north:'北',south:'南'};
const messages:Record<string,string>={coordinate_ai_route_unavailable:'当前解析入口不可用，或容量不足以处理这段说明。请联系管理员核对模型路由；也可以继续手动填写。',coordinate_ai_unconfigured:'智能解析暂未启用，可直接按来源资料填写。',coordinate_ai_identity_unavailable:'模型服务身份暂不可确认，请稍后重试。',coordinate_ai_busy:'当前解析任务较多，请稍后再试。',coordinate_ai_rate_limited:'模型服务繁忙，请稍后重试。',coordinate_ai_access_denied:'当前工作区暂不能使用这项模型能力，请联系管理员。',coordinate_ai_invalid_response:'模型没有返回带有效原文依据的建议，请补充说明后重试。',coordinate_revision_changed:'资料修订已变化，请重新读取坐标说明。'};
export function CoordinateAssistance({endpoint,space,input=null,revision=null,contextKey,onApply,onEvidenceChange}:{endpoint:string;space:string;input?:string|null;revision?:number|null;contextKey:string;onApply:(axes:string[],reason:string)=>void;onEvidenceChange?:(dirty:boolean)=>void}){
 const [available,setAvailable]=useState<boolean|null>(null),[capError,setCapError]=useState(''),[reload,setReload]=useState(0),[open,setOpen]=useState(false),[text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<CoordinateSuggestion|null>(null);
 const generation=useRef(0),pending=useRef<AbortController|null>(null),gate=useRef(false);
 useEffect(()=>{const controller=new AbortController();setAvailable(null);setCapError('');fetch(endpoint+'/api/coordinate-assistance?'+new URLSearchParams({space_id:space}),{signal:controller.signal,cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('智能解析能力暂不可读。');const value=await r.json();if(value.profile!=='cospace.coordinate-assistance-capability/0.1'||value.space_id!==space||typeof value.available!=='boolean')throw Error('智能解析能力与当前场景不一致。');if(!controller.signal.aborted)setAvailable(value.available);}).catch(e=>{if(!controller.signal.aborted)setCapError(e.message);});return()=>controller.abort();},[endpoint,space,reload]);
 useEffect(()=>{generation.current++;pending.current?.abort();gate.current=false;setBusy(false);setResult(null);setError('');setText('');setOpen(false);return()=>{generation.current++;pending.current?.abort();};},[endpoint,space,input,revision,contextKey]);
 useEffect(()=>{onEvidenceChange?.(!!text.trim());return()=>onEvidenceChange?.(false);},[text,onEvidenceChange]);
 async function parse(){
  if(!available||gate.current||!text.trim())return;gate.current=true;const run=++generation.current,controller=new AbortController(),request=crypto.randomUUID().replaceAll('-',''),evidence=text;pending.current=controller;setBusy(true);setError('');setResult(null);
  try{const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(evidence)))).map(v=>v.toString(16).padStart(2,'0')).join('');
   const response=await fetch(endpoint+'/api/coordinate-assistance',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.any([controller.signal,AbortSignal.timeout(65000)]),body:JSON.stringify({space_id:space,...(input?{input_id:input,expected_revision:revision}:{}),request_id:request,evidence_text:evidence})});const value=await response.json();if(!response.ok)throw Error(messages[value.detail]||'智能解析暂未完成，可继续手动填写或稍后重试。');
   const suggestion=validateCoordinateSuggestion(value,{space,input,revision,task:'cospace-coordinate-'+request,sha256:sha,evidence});if(run===generation.current)setResult(suggestion);
  }catch(e){if(run===generation.current&&!controller.signal.aborted)setError(e instanceof Error&&e.name==='TimeoutError'?'解析超时，可保留说明后重试。':e instanceof Error?e.message:'解析未完成。');}finally{if(run===generation.current){gate.current=false;setBusy(false);}}
 }
 return <section className="flex min-w-0 flex-col gap-sm rounded-md border border-border p-md" aria-label="坐标来源智能解析">
  <div className="flex flex-wrap items-center justify-between gap-sm"><strong className="text-body-small">智能解析来源说明</strong>{available&&<Button type="button" size="sm" variant="ghost" onClick={()=>setOpen(v=>!v)}>{open?'收起':'打开解析'}</Button>}</div>
  {available===false&&<p className="text-label-small text-muted-foreground">智能解析暂未启用，可直接按来源资料填写。</p>}{available===null&&!capError&&<output>正在读取智能解析能力…</output>}
  {capError&&<div className="flex flex-wrap items-center gap-sm"><p role="alert">{capError}</p><Button type="button" size="sm" variant="outline" onClick={()=>setReload(n=>n+1)}>重试读取</Button></div>}
  {available&&open&&<><label className="flex flex-col gap-sm text-body-small">来源说明或坐标元数据<Textarea aria-label="待解析的坐标来源说明" placeholder="粘贴导出说明、坐标约定或 JSON 元数据原文，保留单位和三轴方向。" value={text} maxLength={12000} disabled={busy} onChange={e=>{setText(e.target.value);setResult(null);setError('');}}/></label><p className="text-label-small text-muted-foreground">本段文字将交由平台模型网关解析，仅生成建议。请逐项核对原文依据，再填入表单保存。</p>
   <div className="flex flex-wrap gap-sm"><Button type="button" size="sm" variant="outline" disabled={busy||!text.trim()} onClick={parse}>{busy?'正在解析…':'解析来源说明'}</Button>{busy&&<Button type="button" size="sm" variant="ghost" onClick={()=>{generation.current++;pending.current?.abort();gate.current=false;setBusy(false);setError('已停止等待本次解析。');}}>停止等待</Button>}</div>
   {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
   {result&&<div className="flex min-w-0 flex-col gap-md" aria-label="待确认的坐标建议"><StatusBadge tone={result.can_apply_axes?'info':'warning'}>待核对建议</StatusBadge><dl className="flex flex-col gap-sm text-body-small">{result.proposal.axes.map((axis,i)=><div key={i} className="flex flex-col gap-xs"><dt>{'XYZ'[i]}轴 · {axis.direction?names[axis.direction]:'待补充'}</dt><dd className="break-words text-muted-foreground">{axis.evidence_quote?`原文：${axis.evidence_quote}`:'原文中未找到明确依据'}</dd></div>)}<div><dt>单位 · {result.proposal.unit||'待核对'}</dt>{result.proposal.unit_evidence_quote&&<dd className="break-words text-muted-foreground">原文：{result.proposal.unit_evidence_quote}</dd>}</div></dl>
    {result.proposal.unresolved.map((item,i)=><p className="text-body-small" key={i}>{item}</p>)}{result.proposal.unit&&result.proposal.unit!=='m'&&<p className="text-body-small">来源单位需要先转换为米，当前表单不能仅修改声明换算点坐标。</p>}
    {!result.can_apply_axes&&<p className="text-label-small text-muted-foreground">建议仍有缺项或轴向冲突，请补充来源说明；也可以继续手动核对。</p>}
    <Button type="button" size="sm" className="self-start" disabled={!result.can_apply_axes} onClick={()=>{onApply(result.proposal.axes.map(a=>a.direction!),suggestionReason(result));setResult(null);}}>核对并填入轴向建议</Button>
   </div>}
  </>}
 </section>;
}
