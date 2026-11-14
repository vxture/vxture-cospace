import React,{createContext,useContext,useEffect,useMemo,useSyncExternalStore} from 'react';
import {WorkspaceQueryStore} from './workspace-query-store';
import {usePlatformSession} from './platform-auth';
import {sessionScopeKey} from './session-continuity';
const Queries=createContext<WorkspaceQueryStore|null>(null);
export function WorkspaceQueries({children}:{children:React.ReactNode}){
 const session=usePlatformSession(),scope=sessionScopeKey(session)+'|'+(session?.csrf||'preview');
 const store=useMemo(()=>new WorkspaceQueryStore(),[scope]);
 useEffect(()=>{
  const invalidate=()=>store.invalidate();
  const events=['cospace:scope-reset','cospace:access-invalidated','cospace:records-changed','cospace:scene-information-saved','cospace:session-confirmed'];
  events.forEach(name=>window.addEventListener(name,invalidate));
  return()=>events.forEach(name=>window.removeEventListener(name,invalidate));
 },[store]);
 return <Queries.Provider value={store}>{children}</Queries.Provider>;
}
export function useWorkspaceQuery<T>(key:string,load:()=>Promise<T>){
 const store=useContext(Queries);
 if(!store)throw new Error('workspace_query_provider_required');
 const subscribe=useMemo(()=>(fn:()=>void)=>store.subscribe(key,fn),[store,key]);
 const snapshot=useSyncExternalStore(subscribe,()=>store.snapshot<T>(key));
 useEffect(()=>{void store.read(key,load);},[store,key,load,snapshot.revision]);
 return snapshot;
}
