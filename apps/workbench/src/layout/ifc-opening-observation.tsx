import React,{useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';

import {checked,stateLabels,valueLabels,type State} from './ifc-observation-contract';

export function IfcOpeningObservation({space,pin,element}:{readonly space:string;readonly pin:string;readonly element:string}){
 const [data,setData]=useState<State|null>(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setData(null);setError('');
  fetch(`${businessEndpoint}/api/scene-ifc/opening-observation?${new URLSearchParams({space_id:space,catalog_sha256:pin,element_id:element})}`,{signal:controller.signal,cache:'no-store'})
   .then(async response=>{if(!response.ok){throw new Error('观测摘要暂不可用。');}return checked(await response.json(),space,pin,element);})
   .then(value=>{if(!controller.signal.aborted)setData(value);})
   .catch(reason=>{if(!controller.signal.aborted)setError(reason.message);});
  return()=>controller.abort();
 },[space,pin,element,revision]);
 let label='—';
 if(data)label=data.configured?stateLabels[data.status]:'尚未配置上报来源';
 if(data?.value)label=`来源报告：${valueLabels[data.value]}`;
 return <section aria-label="门状态观测" aria-busy={!data&&!error} className="flex flex-col gap-sm border-t pt-md">
  <header className="flex items-center justify-between gap-md"><h4 className="text-title-small">状态观测</h4><Button variant="ghost" size="sm" onClick={()=>setRevision(v=>v+1)}>刷新</Button></header>
  <p className="text-body-small">{error||label}</p>
  <p className="text-label-small text-muted-foreground">{data?.reported_at?`最后上报：${new Date(data.reported_at).toLocaleString()}`:'最后上报：—'}</p>
  {data?.configured&&<p className="text-label-small text-muted-foreground">来源报告待核验，与 IFC 设计姿态分开记录。</p>}
 </section>;
}
