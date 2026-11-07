import {useEffect,useState} from 'react';
import {usePlatformSession} from './platform-auth';
import {businessEndpoint} from './business-endpoint';
import type {SceneSpace} from './scene-directory';
// Same scope/error contract for every scene workspace; URL selection stays explicit.
export function useSceneDirectory(revision=0){
 const platform=usePlatformSession(),workspace=platform?.user?.workspace_id||'engineering';
 const [saved,setSaved]=useState<{workspace:string;spaces:SceneSpace[]}|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();setSaved(null);setLoading(true);setError('');
  fetch(`${businessEndpoint}/api/spaces`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error('场景目录暂不可用，请刷新重试。');const body=await r.json();
   if(!Array.isArray(body.spaces)||body.spaces.some((s:SceneSpace)=>!s||typeof s.id!=='string'||typeof s.name!=='string'||s.capabilities&&!Array.isArray(s.capabilities)||s.publications&&!Array.isArray(s.publications)))throw Error('场景目录格式无法识别。');
   if(!controller.signal.aborted)setSaved({workspace,spaces:body.spaces});
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[workspace,revision]);
 return {spaces:saved?.workspace===workspace?saved.spaces:[],loading,error};
}
