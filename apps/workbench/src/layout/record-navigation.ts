import {createContext,useContext,useSyncExternalStore} from 'react';

const subscribe=(update:()=>void)=>{window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);};
const snapshot=()=>location.hash;
type Navigation={tab:string;batch:string;space:string;input:string;job:string;publication:string;from:string;artifact:string};
const NavigationScope=createContext<Navigation|null>(null);
export const RecordNavigationProvider=NavigationScope.Provider;

export function recordLink(route:'space'|'data'|'build'|'delivery'|'association'|'ontology'|'settings', values:Record<string,string>){
 const space=new URLSearchParams(location.hash.split('?')[1]||'').get('space');
 return `#${route}?${new URLSearchParams({...space?{space}:{},...values})}`;
}
export function useRecordNavigation(){
 const scope=useContext(NavigationScope);
 // All modules read one synchronous URL snapshot. Independent state/effect copies
 // could briefly combine an old authorized scene with a newly requested record.
 const hash=useSyncExternalStore(subscribe,snapshot);
 const params=new URLSearchParams(hash.split('?')[1]||'');
 return scope||{tab:params.get('tab')||'',batch:params.get('batch')||'',space:params.get('space')||'',input:params.get('input')||'',job:params.get('job')||'',publication:params.get('publication')||'',from:params.get('from')||'',artifact:params.get('artifact')||''};
}
