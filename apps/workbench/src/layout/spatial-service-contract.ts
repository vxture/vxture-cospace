import type {SceneSpace,ScenePublication} from './scene-directory';

export const serviceKinds={preview:{label:'态势预览',capability:'space.preview'},query:{label:'空间查询',capability:'space.query'},offline:{label:'离线交付',capability:'space.export'}} as const;
export type ServiceKind=keyof typeof serviceKinds;
export type SpatialService={id:string;scene:SceneSpace;release:ScenePublication;kind:ServiceKind;available:boolean;state:'active'|'paused'|'retired'|'unknown'};
// Directory records have already been scoped by the server. Never invent an
// ungranted operation, or treat missing lifecycle metadata as an active release.
export function spatialServices(spaces:SceneSpace[]):SpatialService[]{
 return spaces.flatMap(scene=>(scene.publications||[]).flatMap(release=>{
  const state=release.lifecycle_state==='active'?'active':release.lifecycle_state==='paused'?'paused':release.lifecycle_state==='retired'?'retired':'unknown';
  return (Object.keys(serviceKinds) as ServiceKind[]).filter(kind=>scene.capabilities?.includes(serviceKinds[kind].capability)).map(kind=>({id:`${scene.id}:${release.id}:${kind}`,scene,release,kind,state,available:state==='active'}));
 }));
}
export function filterSpatialServices(items:SpatialService[],query:string,kind:string,state:string){
 const match=query.trim().toLocaleLowerCase();
 return items.filter(item=>(kind==='all'||kind===item.kind)&&(state==='all'||(state==='available'?item.available:!item.available))&&`${item.scene.name} ${item.scene.project_name||''} ${item.scene.description||''} ${item.release.id} ${item.release.version_code||''} ${serviceKinds[item.kind].label}`.toLocaleLowerCase().includes(match))
  .sort((a,b)=>(Date.parse(b.release.created_at)||0)-(Date.parse(a.release.created_at)||0)||a.id.localeCompare(b.id));
}
export const serviceResourcePath=(item:SpatialService)=>`/publications/${encodeURIComponent(item.release.id)}/${item.kind==='query'?'api/query-range':item.kind==='offline'?'offline.zip':'api/preview'}`;

// A space is listed once. Every operation remains bound to an explicit publication.
export type ServiceVersion={release:ScenePublication;services:SpatialService[];available:boolean;state:SpatialService['state']};
export type ServiceSpace={scene:SceneSpace;versions:ServiceVersion[]};
export function serviceSpaces(items:SpatialService[]):ServiceSpace[]{
 const spaces=new Map<string,ServiceSpace>();
 for(const item of items){
  let group=spaces.get(item.scene.id);
  if(!group){group={scene:item.scene,versions:[]};spaces.set(item.scene.id,group);}
  let version=group.versions.find(v=>v.release.id===item.release.id);
  if(!version){version={release:item.release,services:[],available:item.available,state:item.state};group.versions.push(version);}
  version.services.push(item);
 }
 return [...spaces.values()].map(group=>({...group,versions:group.versions.sort((a,b)=>(Date.parse(b.release.created_at)||0)-(Date.parse(a.release.created_at)||0)||a.release.id.localeCompare(b.release.id))}));
}
export function selectedServiceVersion(group:ServiceSpace,publication?:string):ServiceVersion|undefined{
 if(publication!==undefined)return group.versions.find(v=>v.release.id===publication);
 return group.versions.find(v=>v.available)||group.versions[0];
}
export const serviceSections={directory:'服务目录',offline:'离线交付',online:'在线服务',feedback:'态势反馈',recipients:'服务对象'} as const;
export type ServiceSection=keyof typeof serviceSections;
export function sectionServices(version:ServiceVersion,section:ServiceSection){
 return version.services.filter(item=>section==='directory'||section==='offline'&&item.kind==='offline'||section==='online'&&item.kind==='query');
}
