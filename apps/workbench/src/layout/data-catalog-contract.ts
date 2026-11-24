export const dataResourceNavigation=[
 {title:'数据资源',items:[
  {category:'all',label:'全部数据',icon:'database'},
  {category:'base',label:'基础数据',icon:'stack'},
  {category:'acquisition',label:'采集资料',icon:'file'},
  {category:'reference',label:'参考资料',icon:'link'},
  {category:'result',label:'空间成果',icon:'cube'},
 ]},
 {title:'业务记录',items:[{category:'process',label:'处理记录',icon:'archive'}]},
] as const;
export const dataCategoryLabels:Record<string,string>=Object.fromEntries(dataResourceNavigation.flatMap(s=>s.items.map(i=>[i.category,i.label])));
export function dataCatalogHref(values:Record<string,string>={}){
 const params=new URLSearchParams({scope:'all',category:'all',...values});
 for(const [key,value] of [...params])if(!value)params.delete(key);
 return '/data?'+params;
}
export type DataVersion={version_id:string;reference_kind:'source_metadata';created_at:string|null;format?:string|null;bytes?:number|null};
export type ResourceItem={key:string;record_id:string;space_id:string;space_name:string;kind:string;label:string;state:string;href:string;resource_id:string|null;resource_type:string;source_version:DataVersion|null;project_id:string|null;owner_project_id:string|null;owner_project_name:string|null;registered:boolean;is_base:boolean;revision:number;version_count:number;version_registered?:boolean;can_manage:boolean};
export type ResourceReport={profile:'cospace.data-resources/0.1';workspace_id:string;category:string;project_id:string|null;space_id:string|null;items:ResourceItem[];total:number;spaces:{id:string;name:string;project_id:string|null}[];can_manage:boolean;status:'ready'|'partial';offset:number;limit:number;next_offset:number|null;observed_at:string;source_files_rechecked:false};
export function parseResourceReport(value:unknown,scope:{workspace:string;project:string;space:string;category:string}):ResourceReport{
 const v=value as ResourceReport;
 if(!v||v.profile!=='cospace.data-resources/0.1'||scope.workspace&&v.workspace_id!==scope.workspace||(v.project_id||'')!==scope.project||(v.space_id||'')!==scope.space||v.category!==scope.category||!Array.isArray(v.items)||!Array.isArray(v.spaces)||!Number.isInteger(v.total)||v.total<0||!['ready','partial'].includes(v.status)||v.source_files_rechecked!==false)throw Error('数据目录响应与当前范围不一致。');
 for(const item of v.items){
  const href=new URL(item.href,'https://cospace.test');
  const process=['job','batch','preflight'].includes(item.kind);
  if(!/^#(?:data|build)\?/.test(item.href)||href.hash.split('?')[0]!==('#'+(item.kind==='job'?'build':'data'))||new URLSearchParams(item.href.split('?')[1]).get('space')!==item.space_id||!v.spaces.some(s=>s.id===item.space_id)||typeof item.label!=='string'||process!==(v.category==='process')||process&&(item.resource_id!==null||item.source_version!==null)||!process&&(!/^resource-[a-f0-9]{32}$/.test(item.resource_id||'')||!item.source_version)||item.source_version&&(!/^[a-f0-9]{64}$/.test(item.source_version.version_id)||item.source_version.reference_kind!=='source_metadata'))throw Error('数据资源引用无效。');
 }
 return v;
}
