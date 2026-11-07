import type {ModuleRoute} from './product-navigation';

// Explicit business handoffs may carry record IDs. Ordinary module navigation
// carries only the scene (a filter/return context for shared support modules).
export function recordLinkFromHash(route:ModuleRoute|'settings',values:Record<string,string>,hash:string){
 const space=new URLSearchParams(hash.split('?')[1]||'').get('space');
 return `#${route}?${new URLSearchParams({...space?{space}:{},...values})}`;
}

export function moduleLinkFromHash(route:ModuleRoute,hash:string){
 return recordLinkFromHash(route,{},hash);
}

// Scene changes keep only a valid capability view; record IDs never cross scenes.
export function sceneLinkFromHash(route:ModuleRoute,space:string,hash:string){
 const views:Partial<Record<ModuleRoute,string[]>>={build:['flow','tasks','candidate'],association:['objects','ifc','business','relations'],data:['inputs','references','pointcloud','batches','versions','lineage']};
 const tab=new URLSearchParams(hash.split('?')[1]||'').get('tab')||'';
 return recordLinkFromHash(route,{space,...(views[route]?.includes(tab)?{tab}:{})},hash);
}
