import React,{useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {Batch} from './acquisition-batches';
import {recordLink} from './record-navigation';

export type HistoryJob={space_id:string;id:string;input_id?:string;batch_ref?:{batch_id:string;admitted_revision:number};state:string};
export function useSceneHistory(space:string,revision:number,versions:boolean){
 const [saved,setSaved]=useState<{space:string;batches:Batch[];jobs:HistoryJob[]}|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();setSaved(null);setError('');setLoading(false);
  if(!space)return;
  setLoading(true);
  const query='?'+new URLSearchParams({space_id:space});
  const read=async(path:string)=>{const r=await fetch(endpoint+path+query,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('批次或版本来源暂不可用，请刷新数据重试。');return r.json();};
  Promise.all([read('/api/batches'),versions?read('/api/builds'):Promise.resolve({jobs:[]})]).then(([listing,jobs])=>{
   if(listing.space_id!==space||!Array.isArray(listing.batches)||!Array.isArray(jobs.jobs)||listing.batches.some((b:Batch)=>b.space_id!==space)||jobs.jobs.some((j:HistoryJob)=>j.space_id!==space))throw Error('历史记录与当前场景不一致。');
   if(!controller.signal.aborted)setSaved({space,batches:listing.batches,jobs:jobs.jobs});
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[space,revision,versions]);
 return {batches:saved?.space===space?saved.batches:[],jobs:saved?.space===space?saved.jobs:[],loading,error};
}
export function InputBatchLinks({space,input,batches,available=true}:{space:string;input:string;batches:Batch[];available?:boolean}){
 const members=batches.filter(b=>b.members.some(m=>m.input_id===input));
 return <section className="data-detail-section" aria-label="资料所属批次"><h3>采集批次</h3>
  {members.map(b=><Button key={b.id} asChild size="sm" variant="link"><a href={recordLink('data',{space,tab:'batches',batch:b.id})}>{b.name} · {{draft:'整理中',sealed:'已封存',disabled:'已停用'}[b.state]}</a></Button>)}
  {!available?<p>批次归属暂时无法确认，请刷新数据。</p>:!members.length&&<p>尚未纳入批次，可按采集轮次或导入轮次整理。</p>}
  <Button asChild size="sm" variant="outline"><a href={recordLink('data',{space,tab:'batches',input})}>整理到批次</a></Button>
 </section>;
}
export function VersionSource({space,job,batches,inputs,available=true}:{space:string;job?:HistoryJob;batches:Batch[];inputs:{id:string;label:string}[];available?:boolean}){
 if(!available)return <span className="data-cell-note">来源记录暂不可用</span>;
 const batch=batches.find(b=>b.id===job?.batch_ref?.batch_id),input=inputs.find(i=>i.id===job?.input_id);
 return <div className="data-version-source">{job?.batch_ref?<><a href={recordLink('data',{space,tab:'batches',batch:job.batch_ref.batch_id})} onClick={e=>e.stopPropagation()}>{batch?.name||job.batch_ref.batch_id}</a><small>提交修订 {job.batch_ref.admitted_revision}</small></>:<span className="data-cell-note">未记录批次绑定</span>}{input&&<a href={recordLink('data',{space,tab:'inputs',input:input.id})} onClick={e=>e.stopPropagation()}>{input.label}</a>}</div>;
}
