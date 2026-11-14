import React,{createContext,useContext,useEffect,useMemo,useRef,useSyncExternalStore} from 'react';
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
export function useWorkspaceQuery<T>(key:string,load:()=>Promise<T>,refreshToken=0){
 const store=useContext(Queries);
 if(!store)throw new Error('workspace_query_provider_required');
 const subscribe=useMemo(()=>(fn:()=>void)=>store.subscribe(key,fn),[store,key]);
 const snapshot=useSyncExternalStore(subscribe,()=>store.snapshot<T>(key));
 const previous=useRef({store,key,refreshToken});
 useEffect(()=>{
  const old=previous.current;previous.current={store,key,refreshToken};
  if(old.store===store&&old.key===key&&old.refreshToken!==refreshToken)store.invalidate(key);
 },[store,key,refreshToken]);
 useEffect(()=>{void store.read(key,load);},[store,key,load,snapshot.revision]);
 return snapshot;
}
