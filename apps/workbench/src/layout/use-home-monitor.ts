import {useEffect,useState} from 'react';
import {businessEndpoint} from './business-endpoint';
import type {SceneSpace} from './scene-directory';
import {usePlatformSession} from './platform-auth';
import {sessionScopeKey} from './session-continuity';

type Monitor={space:string;requests:number;failed:number;rejected:number;totals:{requests:number;failed:number;rejected:number};partial:boolean;configuration:string;generatedAt:string|null};
// Bound concurrency; no artifact loading and no client-side cross-workspace cache.
export function useHomeMonitor(spaces:SceneSpace[],revision:number){
 const scope=sessionScopeKey(usePlatformSession())||'engineering';
 const ids=spaces.filter(scene=>scene.capabilities?.includes('publication.manage')).map(scene=>scene.id).sort((a,b)=>a.localeCompare(b));
 const key=JSON.stringify([scope,ids]);
 const [saved,setSaved]=useState<{key:string;rows:Monitor[];errors:number;done:boolean}|null>(null);
 useEffect(()=>{
  const controller=new AbortController(),rows:Monitor[]=[];let cursor=0,errors=0;
  setSaved({key,rows:[],errors:0,done:false});
  async function worker(){
   while(cursor<ids.length&&!controller.signal.aborted){
    const space=ids[cursor++];
    try{
     const response=await fetch(businessEndpoint+'/api/service-monitor?'+new URLSearchParams({space_id:space}),{cache:'no-store',signal:controller.signal});
     if(!response.ok)throw new Error('invalid_service_monitor_report');
     const report=await response.json();
     if(report.space_id!==space||![report.totals?.requests,report.totals?.failed,report.totals?.rejected,report.request_count,report.counts?.failed,report.counts?.rejected].every(value=>Number.isSafeInteger(value)&&value>=0)||typeof report.totals?.partial!=='boolean'||!['configured','not_configured','not_granted','unavailable'].includes(report.configuration?.state))throw new Error('invalid_service_monitor_report');
     rows.push({space,requests:report.request_count,failed:report.counts.failed,rejected:report.counts.rejected,totals:report.totals,partial:report.totals.partial,configuration:report.configuration.state,generatedAt:typeof report.generated_at==='string'&&Number.isFinite(Date.parse(report.generated_at))?report.generated_at:null});
    }catch{if(!controller.signal.aborted)errors++;}
   }
  }
  void Promise.all(Array.from({length:Math.min(3,ids.length)},worker)).then(()=>{if(!controller.signal.aborted)setSaved({key,rows,errors,done:true});});
  return()=>controller.abort();
 },[key,revision]);
 const current=saved?.key===key?saved:null;
 return {rows:current?.rows||[],errors:current?.errors||0,loading:!current?.done,total:ids.length};
}
