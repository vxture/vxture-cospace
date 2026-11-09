import type {SceneSpace,ScenePublication} from './scene-directory';

export const serviceKinds={preview:{label:'空间预览',capability:'space.preview'},query:{label:'空间查询',capability:'space.query'},offline:{label:'离线交付',capability:'space.export'}} as const;
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
 return items.filter(item=>(kind==='all'||kind===item.kind)&&(state==='all'||(state==='available'?item.available:!item.available))&&`${item.scene.name} ${item.scene.project_name||''} ${item.scene.description||''} ${item.release.id} ${serviceKinds[item.kind].label}`.toLocaleLowerCase().includes(match))
  .sort((a,b)=>(Date.parse(b.release.created_at)||0)-(Date.parse(a.release.created_at)||0)||a.id.localeCompare(b.id));
}
export const serviceResourcePath=(item:SpatialService)=>`/publications/${encodeURIComponent(item.release.id)}/${item.kind==='query'?'api/query-range':item.kind==='offline'?'offline.zip':'api/preview'}`;
