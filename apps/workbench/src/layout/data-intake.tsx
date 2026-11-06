import React,{useEffect,useState} from 'react';
import {Button,StatusBadge} from '@vxture/design-system';
import {ArrowRight,CheckCircle} from '@phosphor-icons/react';
import {businessEndpoint as endpoint} from './business-endpoint';
import {recordLink} from './record-navigation';
import {InputRoute} from './input-format';

export type IntakeInput={input_id:string;label:string;lifecycle_state:string;check_status:string;checked_at:string|null;route?:InputRoute;batch?:{status:string;issue:string|null;can_submit:boolean;choices:{id:string;name:string;state:string;available:boolean}[]}};
export type Preparation={selected_input_id:string|null;selected_batch_id?:string|null;can_submit?:boolean;detail:string;enabled_source_count:number;source_revision:number;inputs:IntakeInput[];next_action:{allowed?:boolean;module:'data'|'build';label:string;intent?:string;values:Record<string,string>}};
export function useDataIntake(space:string,input:string,revision:number|string,enabled:boolean,batch=''){
 const [saved,setSaved]=useState<{space:string;input:string;batch:string;data:Preparation}|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();setSaved(null);setError('');setLoading(false);
  if(!space||!enabled)return;
  setLoading(true);
  fetch(`${endpoint}/api/workflow?${new URLSearchParams({space_id:space,...(input?{input_id:input}:{}),...(batch?{batch_id:batch}:{})})}`,{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error('准备状态暂不可用，请刷新数据重试。');
   const value=await r.json();
   if(value.space_id!==space||!value.preparation||value.preparation.selected_input_id!==(input||null)||(value.preparation.selected_batch_id||'')!==batch)throw Error('准备状态与当前场景、资料或批次不一致。');
   if(!controller.signal.aborted)setSaved({space,input,batch,data:value.preparation});
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[space,input,revision,enabled,batch]);
 return {data:saved?.space===space&&saved.input===input&&saved.batch===batch?saved.data:null,error,loading};
}
export function InputCheckStatus({item}:{item?:IntakeInput}){
 if(!item)return <span className="data-cell-note">预检记录待读取</span>;
 const text:Record<string,string>={passed:'上次预检通过',failed:'上次预检失败',not_checked:'待预检',registration_changed:'登记变化，需重检'};
 return <span className="data-cell-note"><StatusBadge tone={item.check_status==='passed'?'success':item.check_status==='not_checked'?'neutral':'warning'}>{text[item.check_status]||'预检状态未知'}</StatusBadge></span>;
}
export function DataIntake({space,data,error,loading,onSources,onImport,onInspect,onChoose,batchId}:{space:string;data:Preparation|null;error:string;loading:boolean;onSources:()=>void;onImport:()=>void;onInspect:()=>void;onChoose:()=>void;batchId?:string}){
 if(loading)return <div className="data-intake" role="status">正在读取构建准备状态…</div>;
 if(error)return <div className="data-intake" role="alert">{error}</div>;
 if(!data)return null;
 const selected=data.inputs.find(i=>i.input_id===data.selected_input_id);
 const ready=data.can_submit===true;
 const stage=ready?2:data.inputs.length?1:0;
 const stages=[{label:'导入资料',detail:`${data.inputs.length} 项登记`},{label:'检查整理',detail:selected?selected.check_status==='passed'?'已有预检记录':'核对资料与批次':'选择本次资料'},{label:'用于构建',detail:ready?'提交时重检':'明确资料与批次'}];
 const allowed=data.next_action.allowed!==false;
 const action=data.next_action;
 const label=action.label;
 return <section className="data-intake" aria-label="资料到构建准备">
  <div><ol>{stages.map((s,i)=><li key={s.label} aria-current={i===stage?'step':undefined} data-current={i===stage||undefined}><span className="data-intake-step">{i<stage?<CheckCircle size={15}/>:i+1}</span><span>{s.label}<small>{s.detail}</small></span>{i<2&&<ArrowRight className="data-intake-arrow" size={12}/>}</li>)}</ol><p className="text-label-small text-muted-foreground mt-sm">{data.detail}</p></div>
  <div className="data-intake-next">{allowed&&(action.module==='build'||action.values.tab==='batches')?<Button asChild size="sm"><a href={recordLink(action.module,{...action.values})}>{label}<ArrowRight size={13}/></a></Button>:<Button size="sm" variant="outline" disabled={!allowed} onClick={action.intent==='import'?onImport:action.values.tab==='sources'?onSources:selected?onInspect:onChoose}>{label}</Button>}</div>
 </section>;
}
