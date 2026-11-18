import type {ServiceSection} from './spatial-service-contract';

export const sceneServiceTabs={overview:'服务概况',online:'在线服务',offline:'离线交付',feedback:'态势反馈',recipients:'智能设备'} as const;
export type SceneServiceTab=keyof typeof sceneServiceTabs;
export type ServiceListFilter={query?:string;state?:string};
export const deviceTabs={overview:'设备信息',spaces:'关联场景',integration:'接入配置',records:'使用记录'} as const;
export type DeviceTab=keyof typeof deviceTabs;
export function devicePageHref(device:string,tab:DeviceTab='overview',context='/services?section=recipients'){
 const params=new URLSearchParams(context.split('?')[1]);
 if(!params.has('section'))params.set('section','recipients');
 if(params.has('space'))params.set('tab','recipients');
 params.set('device',device);params.set('deviceTab',tab);
 return '/services?'+params;
}
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

export type ServiceViewMode='cards'|'list';
export type ServicePresentation=Readonly<{view:ServiceViewMode;onView:(view:ServiceViewMode)=>void}>;
export const serviceViewPreferenceKey='cospace.spatial-services.view';
export function readServiceView(storage:Pick<Storage,'getItem'>){
 try{return storage.getItem(serviceViewPreferenceKey)==='list'?'list':'cards';}
 catch{return 'cards';}
}
