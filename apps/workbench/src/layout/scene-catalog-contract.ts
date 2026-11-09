import type {SceneSpace} from './scene-directory';

export const scenePhases={
 published:{label:'已发布',tone:'brand'},
 building:{label:'构建中',tone:'info'},
 review:{label:'待验证',tone:'warning'},
 unavailable:{label:'不可用',tone:'danger'},
 paused:{label:'已暂停',tone:'neutral'},
 archived:{label:'已归档',tone:'neutral'},
} as const;
export type ScenePhase=keyof typeof scenePhases;
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
  .sort((a,b)=>(sort==='name'?0:order.indexOf(scenePhase(a))-order.indexOf(scenePhase(b)))||a.name.localeCompare(b.name,'zh-CN'));
}
// Entering a scene selects its workflow; opening a fixed release is a separate action.
export const sceneWorkspaceHref=(id:string)=>'/space?'+new URLSearchParams({space:id});
