import {createContext,useContext,useSyncExternalStore} from 'react';
import {recordLinkFromHash,moduleLinkFromHash} from './navigation-contract';
import type {ModuleRoute} from './product-navigation';

const subscribe=(update:()=>void)=>{window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);};
const snapshot=()=>location.hash;
type Navigation={tab:string;batch:string;space:string;input:string;job:string;publication:string;from:string;artifact:string};
const NavigationScope=createContext<Navigation|null>(null);
export const RecordNavigationProvider=NavigationScope.Provider;

export function recordLink(route:'space'|'data'|'build'|'delivery'|'association'|'ontology'|'settings', values:Record<string,string>){
 return recordLinkFromHash(route,values,location.hash);
}
export function moduleLink(route:ModuleRoute){return moduleLinkFromHash(route,location.hash);}
export function useRecordNavigation(){
 const scope=useContext(NavigationScope);
 // All modules read one synchronous URL snapshot. Independent state/effect copies
 // could briefly combine an old authorized scene with a newly requested record.
 const hash=useSyncExternalStore(subscribe,snapshot);
 const params=new URLSearchParams(hash.split('?')[1]||'');
 return scope||{tab:params.get('tab')||'',batch:params.get('batch')||'',space:params.get('space')||'',input:params.get('input')||'',job:params.get('job')||'',publication:params.get('publication')||'',from:params.get('from')||'',artifact:params.get('artifact')||''};
}
