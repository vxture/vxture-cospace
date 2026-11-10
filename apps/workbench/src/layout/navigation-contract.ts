import type {ModuleRoute} from './product-navigation';

// Explicit business handoffs may carry record IDs. Ordinary module navigation
// carries only the scene (a filter/return context for shared support modules).
export function recordLinkFromUrl(route:ModuleRoute|'settings',values:Record<string,string>,url:string){
 const space=new URLSearchParams(url.split('?')[1]||'').get('space');
 return `/${route}?${new URLSearchParams({...space?{space}:{},...values})}`;
}

export function moduleLinkFromUrl(route:ModuleRoute,url:string){
 return recordLinkFromUrl(route,{},url);
}

// Scene changes keep only a valid capability view; record IDs never cross scenes.
export function sceneLinkFromUrl(route:ModuleRoute,space:string,url:string){
 const views:Partial<Record<ModuleRoute,string[]>>={build:['flow','tasks','candidate'],association:['objects','ifc','business','relations'],data:['inputs','references','pointcloud','batches','versions','lineage']};
 const tab=new URLSearchParams(url.split('?')[1]||'').get('tab')||'';
 return recordLinkFromUrl(route,{space,...(views[route]?.includes(tab)?{tab}:{})},url);
}

// The global picker also serves the service directory. Never transfer record IDs
// from the previous scene; retain only the current service navigation section.
export function headerSceneLinkFromUrl(space:string,url:string){
 const [path,search='']=url.split('?');
 const route=path.slice(1) as ModuleRoute;
 if(['space','data','build','delivery','association','ontology'].includes(route))return sceneLinkFromUrl(route,space,url);
 const params=new URLSearchParams({space});
 const section=new URLSearchParams(search).get('section');
 if(path==='/services'&&section&&['directory','offline','online','feedback','recipients'].includes(section))params.set('section',section);
 return `${path}?${params}`;
}
