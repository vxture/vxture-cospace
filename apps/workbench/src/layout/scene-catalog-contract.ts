import type {ScenePublication,SceneSpace} from './scene-directory';

export const scenePhases={
 published:{label:'已发布',tone:'brand'},
 building:{label:'构建中',tone:'info'},
 review:{label:'待验证',tone:'warning'},
 unavailable:{label:'不可用',tone:'danger'},
 paused:{label:'已暂停',tone:'neutral'},
 archived:{label:'已归档',tone:'neutral'},
} as const;
export type ScenePhase=keyof typeof scenePhases;
export function sceneTimestamp(scene:SceneSpace){
 const dates=[scene.updated_at,scene.created_at,...(scene.publications||[]).map(p=>p.created_at)]
  .map(value=>value?Date.parse(value):NaN).filter(Number.isFinite);
 return dates.length?Math.max(...dates):0;
}
export const sceneHref=(route:string,id:string)=>`/${route}?${new URLSearchParams({space:id})}`;
export const sceneDestinations=(scene:SceneSpace)=>[
 {key:'data',label:'数据管理',capability:'data.manage'},
 {key:'build',label:'构建中心',capability:'build.run'},
 {key:'delivery',label:'服务发布',capability:'space.preview'},
 {key:'settings',label:'基本信息',capability:'space.preview'},
].map(item=>({...item,href:item.key==='settings'?sceneHref('build',scene.id)+'&tab=info':sceneHref(item.key,scene.id),enabled:!!scene.capabilities?.includes(item.capability)}));
export function scenePhase(scene:SceneSpace):ScenePhase{
 const latest=scene.publications?.[0];
 if(latest?.lifecycle_state==='retired')return 'archived';
 if(scene.state==='distribution_paused'||latest?.lifecycle_state==='paused')return 'paused';
 if(scene.state==='preview_published'&&scene.publication_id)return 'published';
 if(scene.state==='no_publication')return 'building';
 return 'unavailable';
}
export function filterScenes(spaces:SceneSpace[],query:string,phase:string,sort:string){
 const match=query.trim().toLocaleLowerCase(),order=Object.keys(scenePhases);
 return spaces.filter(s=>(phase==='all'||scenePhase(s)===phase)&&`${s.name} ${s.project_name||''} ${s.description||''} ${s.address||''}`.toLocaleLowerCase().includes(match))
  .sort((a,b)=>(sort==='time'?sceneTimestamp(b)-sceneTimestamp(a):sort==='name'?0:order.indexOf(scenePhase(a))-order.indexOf(scenePhase(b)))||a.name.localeCompare(b.name,'zh-CN'));
}
// A legacy scene-only bookmark opens details; entry uses only the explicitly current release.
export const sceneWorkspaceHref=(id:string)=>'/space?'+new URLSearchParams({space:id});

export const publicationAvailable=(release:ScenePublication)=>release.lifecycle_state==='active';
export const publicationLabel=(release:ScenePublication)=>release.display_code||release.version_code||release.id;
export const currentRelease=(scene:SceneSpace)=>scene.publications?.find(p=>p.id===scene.publication_id&&publicationAvailable(p));
export function sceneEntryHref(scene:SceneSpace){
 const release=currentRelease(scene);
 return release?`/space?screen=space&preview=1&space=${encodeURIComponent(scene.id)}&publication=${encodeURIComponent(release.id)}`:sceneWorkspaceHref(scene.id);
}
