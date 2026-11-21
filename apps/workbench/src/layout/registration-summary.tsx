import React,{useEffect,useState} from 'react';
import {ArrowRight,Compass} from '@phosphor-icons/react';
import {Button} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {recordLink} from './record-navigation';
import './registration-summary.css';

type Summary={profile:string;space_id:string;candidate_id:string;review_status:'empty'|'draft'|'submitted'|'approved'|'rejected';revision:number;adopted_revision:number|null;report:{calculation_status:string}|null};
const labels={empty:'未录入',draft:'草稿',submitted:'待审核',approved:'已核准',rejected:'已退回'};
export function RegistrationSummary({spaceId,candidateId,active=true}:{spaceId:string;candidateId:string;active?:boolean}){
 const [summary,setSummary]=useState<Summary|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  if(!active)return;
  const abort=new AbortController();setSummary(null);setError('');
  fetch(businessEndpoint+'/api/scene-registrations?'+new URLSearchParams({space_id:spaceId,candidate_id:candidateId}),{signal:abort.signal,cache:'no-store'}).then(async response=>{
   if(!response.ok)throw Error('空间基准状态暂不可读');
   const result:Summary=await response.json();
   if(result.profile!=='cospace.scene-registration/0.1'||result.space_id!==spaceId||result.candidate_id!==candidateId||!Object.hasOwn(labels,result.review_status))throw Error('空间基准状态暂不可读');
   if(!abort.signal.aborted)setSummary(result);
  }).catch(reason=>{if(!abort.signal.aborted)setError(reason.message);});
  return()=>abort.abort();
 },[spaceId,candidateId,active]);
 return <section className="registration-summary" aria-label="空间基准摘要"><header><Compass size={20}/><h4>空间基准</h4><Button asChild size="sm" variant="ghost"><a href={recordLink('registration',{space:spaceId,job:candidateId})}>查看空间基准<ArrowRight size={16}/></a></Button></header>
  {error?<p role="status">{error}</p>:!summary?<output>正在读取空间基准状态…</output>:<dl>
   <div><dt>资料状态</dt><dd>{labels[summary.review_status]}{summary.revision?` · 修订 ${summary.revision}`:''}</dd></div>
   <div><dt>当前采用</dt><dd>{summary.adopted_revision?`核准修订 ${summary.adopted_revision}`:'尚未采用'}</dd></div>
   <div><dt>当前资料检查</dt><dd>{!summary.report?'尚未核对':summary.report.calculation_status==='checks_passed'?'参数检查通过':'参数检查未通过'}</dd></div>
  </dl>}
 </section>;
}
