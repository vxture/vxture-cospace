import {servicePageHref,type ServiceListFilter,type SceneServiceTab} from './service-workspace-contract.ts';
import type {ServiceSection,ServiceSpace,ServiceVersion} from './spatial-service-contract';

export function serviceEntryDestinations(group:ServiceSpace,version:ServiceVersion,section:ServiceSection,filter:ServiceListFilter={}){
 const page=(key:SceneServiceTab,label:string)=>({key,label,href:servicePageHref(section,group.scene.id,version.release.id,key,filter)});
 if(section==='online')return version.services.some(item=>item.kind==='query')?[page('online','在线服务')]:[];
 if(section==='offline')return version.services.some(item=>item.kind==='offline')?[page('offline','离线交付')]:[];
 if(section!=='directory')return [];
 return [page('overview','服务概况'),
  ...(version.services.some(item=>item.kind==='query')?[page('online','在线服务')]:[]),
  ...(version.services.some(item=>item.kind==='offline')?[page('offline','离线交付')]:[])];
}
