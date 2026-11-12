import type {ServiceSection} from './spatial-service-contract';

export const sceneServiceTabs={overview:'服务概况',online:'在线服务',offline:'离线交付',feedback:'态势反馈',recipients:'服务对象'} as const;
export type SceneServiceTab=keyof typeof sceneServiceTabs;
export type ServiceListFilter={query?:string;state?:string};
export const entryServiceTab=(section:ServiceSection):SceneServiceTab=>section==='directory'?'overview':section;
export function serviceListHref(section:ServiceSection,filter:ServiceListFilter={}){
 const params=new URLSearchParams({section});
 if(filter.query)params.set('q',filter.query);
 if(filter.state&&filter.state!=='all')params.set('status',filter.state);
 return '/services?'+params;
}
// Scene context identifies a detail page, never a filter on a global list.
export function servicePageHref(section:ServiceSection,space:string,publication:string,tab:SceneServiceTab=entryServiceTab(section),filter:ServiceListFilter={}){
 const params=new URLSearchParams(serviceListHref(section,filter).split('?')[1]);
 params.set('space',space);
 if(publication)params.set('publication',publication);
 params.set('tab',tab);
 return '/services?'+params;
}
