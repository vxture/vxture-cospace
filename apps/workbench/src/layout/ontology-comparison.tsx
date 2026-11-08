import React,{useEffect,useState} from 'react';
import {Button,NativeSelect} from '@vxture/design-system';
import {OntologyUsage} from './ontology-usage';
import {compareDefinitions} from './ontology-diff';
type Version={ontology_id:string;version:string;sha256:string;title:string};
type Loaded={record:Version;definition:Record<string,unknown>;integrity:string};
const key=(v:Version)=>`${v.ontology_id}/${v.version}/${v.sha256}`;
export function OntologyComparison({endpoint,current,versions}:{endpoint:string;current:Loaded;versions:Version[]}){
 const [selected,setSelected]=useState(''),[state,setState]=useState<{key:string;loaded?:Loaded;error?:string}|null>(null),[revision,setRevision]=useState(0);
 const requestKey=JSON.stringify([key(current.record),selected,revision]);
 const stateNow=state?.key===requestKey?state:null;
 useEffect(()=>{
  const controller=new AbortController();setState(null);
  const chosen=versions.find(v=>key(v)===selected&&v.ontology_id===current.record.ontology_id&&key(v)!==key(current.record));
  if(!chosen)return()=>controller.abort();
  fetch(`${endpoint}/api/ontologies/${encodeURIComponent(chosen.ontology_id)}/${encodeURIComponent(chosen.version)}?${new URLSearchParams({sha256:chosen.sha256})}`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error('目标规则不可读，请核对权限及固定版本；不会使用其他版本替代。');
   const loaded:Loaded=await r.json();
   if(key(loaded.record)!==selected||loaded.integrity!=='verified'||loaded.definition.ontology_id!==chosen.ontology_id||loaded.definition.version!==chosen.version)throw Error('目标规则与固定引用不一致。');
   if(!controller.signal.aborted)setState({key:requestKey,loaded});
  }).catch(e=>{if(!controller.signal.aborted)setState({key:requestKey,error:e.message});});
  return()=>controller.abort();
 },[requestKey]);
 const other=versions.filter(v=>v.ontology_id===current.record.ontology_id&&key(v)!==key(current.record));
 const changeLabel=(kind:string)=>{if(kind==='added')return '新增';if(kind==='removed')return '删除';return '修改';};
 const diff=stateNow?.loaded?compareDefinitions(current.definition,stateNow.loaded.definition):null;
 return <section aria-label="固定规则版本比较" className="flex min-w-0 flex-col gap-md border border-border rounded-md p-md"><h2>固定规则版本比较</h2><p>比较方向：当前查看 V{current.record.version} → 所选目标版本。版本号不同不等于规则内容不同。</p><NativeSelect aria-label="选择比较目标版本" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">请选择同一本体的另一固定版本</option>{other.map(v=><option key={key(v)} value={key(v)}>V{v.version} · {v.title}</option>)}</NativeSelect>{!other.length&&<p>暂无同一本体的其他授权固定版本。</p>}{selected&&<Button size="sm" variant="outline" onClick={()=>setRevision(v=>v+1)}>重新读取目标版本</Button>}{stateNow?.error&&<p role="alert">{stateNow.error}</p>}{selected&&!stateNow&&<output>正在核对比较版本…</output>}{diff&&<><p>{diff.total===0?'规则内容一致（不比较版本号）。':`发现 ${diff.total} 项内容差异。`}</p><p className="break-all">目标 SHA-256：{stateNow!.loaded!.record.sha256}</p><ol className="flex flex-col gap-md">{diff.items.map(item=><li key={item.path} className="break-all border-b border-border pb-md"><strong>{changeLabel(item.kind)} · {item.path}</strong><p>原值：{item.before}</p><p>目标：{item.after}</p><p>{item.review?'需人工评估约束及实例影响。':'说明文字变化。'}</p></li>)}</ol>{diff.truncated&&<p role="alert">仅展示前200项差异；比较结论不完整，请核对完整规则JSON。</p>}</>}<p>内容差异未核验实例兼容性，不表示可以安全迁移。比较不修改规则、场景、候选或发布。</p>{stateNow?.loaded&&<OntologyUsage key={selected} endpoint={endpoint} reference={stateNow.loaded.record} chooseScene={false}/>}</section>;
}
