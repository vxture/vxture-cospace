import {subscribeAppLocation,appLocation} from './app-router';
import {createContext,useContext,useSyncExternalStore} from 'react';
import {recordLinkFromUrl,moduleLinkFromUrl} from './navigation-contract';
import type {ModuleRoute} from './product-navigation';
import {useSelectedScene} from './scene-selection';

const subscribe=subscribeAppLocation;
const snapshot=()=>appLocation();
type Navigation={tab:string;batch:string;space:string;input:string;job:string;publication:string;from:string;artifact:string};
const NavigationScope=createContext<Navigation|null>(null);
export const RecordNavigationProvider=NavigationScope.Provider;

export function recordLink(route:'space'|'data'|'build'|'delivery'|'association'|'ontology'|'settings', values:Record<string,string>){
 return recordLinkFromUrl(route,values,appLocation());
}
export function moduleLink(route:ModuleRoute,space?:string){return space?recordLinkFromUrl(route,{space},appLocation()):moduleLinkFromUrl(route,appLocation());}
export function useRecordNavigation(){
 const scope=useContext(NavigationScope);
 const remembered=useSelectedScene();
 // All modules read one synchronous URL snapshot. Independent state/effect copies
 // could briefly combine an old authorized scene with a newly requested record.
 const hash=useSyncExternalStore(subscribe,snapshot);
 const params=new URLSearchParams(hash.split('?')[1]||'');
 return scope||{tab:params.get('tab')||'',batch:params.get('batch')||'',space:params.has('space')?params.get('space')||'':remembered,input:params.get('input')||'',job:params.get('job')||'',publication:params.get('publication')||'',from:params.get('from')||'',artifact:params.get('artifact')||''};
}
