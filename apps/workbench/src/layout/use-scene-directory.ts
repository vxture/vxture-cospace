import {useCallback} from 'react';
import {businessEndpoint} from './business-endpoint';
import type {SceneSpace} from './scene-directory';
import {useWorkspaceQuery} from './workspace-queries';
// One scope-bound directory shared across modules; mutation/session events invalidate it.
export function useSceneDirectory(revision=0){
 const load=useCallback(async()=>{
  const response=await fetch(`${businessEndpoint}/api/spaces`,{cache:'no-store'});
  if(!response.ok)throw new Error('场景目录暂不可用，请刷新重试。');
  const body=await response.json();
  if(!Array.isArray(body.spaces)||body.spaces.some((s:SceneSpace)=>!s||typeof s.id!=='string'||typeof s.name!=='string'||s.capabilities&&!Array.isArray(s.capabilities)||s.publications&&!Array.isArray(s.publications)))throw new Error('场景目录格式无法识别。');
  return body.spaces as SceneSpace[];
 },[]);
 const query=useWorkspaceQuery<SceneSpace[]>('directory',load,revision);
 return {spaces:query.data||[],loading:query.loading&&!query.data,error:query.error};
}
