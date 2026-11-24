import {validUse,type ResourceUse} from './data-sharing-contract.ts';
export const dataResourceNavigation=[
 {title:'数据资源',items:[
  {category:'all',label:'全部数据',icon:'database'},
  {category:'base',label:'基础数据',icon:'stack'},
  {category:'acquisition',label:'采集资料',icon:'file'},
  {category:'reference',label:'参考资料',icon:'link'},
  {category:'result',label:'空间成果',icon:'cube'},
 ]},
 {title:'业务记录',items:[{category:'uses',label:'引用记录',icon:'link'},{category:'process',label:'处理记录',icon:'archive'}]},
] as const;
export const dataCategoryLabels:Record<string,string>=Object.fromEntries(dataResourceNavigation.flatMap(s=>s.items.map(i=>[i.category,i.label])));
export function dataCatalogHref(values:Record<string,string>={}){
 const params=new URLSearchParams({scope:'all',category:'all',...values});
 for(const [key,value] of [...params])if(!value)params.delete(key);
 return '/data?'+params;
}
export type DataVersion={version_id:string;reference_kind:'source_metadata';created_at:string|null;format?:string|null;bytes?:number|null};
export type ResourceItem={key:string;record_id:string;space_id:string|null;space_name:string|null;kind:string;label:string;state:string;href:string|null;resource_id:string|null;resource_type:string;source_version:DataVersion|null;project_id:string|null;owner_kind?:'project'|'workspace'|'unassigned';owner_project_id:string|null;owner_project_name:string|null;registered:boolean;is_base:boolean;revision:number;version_count:number;version_registered?:boolean;can_manage:boolean;external?:boolean;uses?:ResourceUse[];is_shared?:boolean;lifecycle_state?:'active'|'archived'|'disabled'|null};
export function resourceOwnerLabel(item:Pick<ResourceItem,'owner_kind'|'owner_project_name'>){return item.owner_kind==='workspace'?'工作区共用':item.owner_project_name||'待登记管理项目';}
export function resourceFileDownload(item:ResourceItem){return '/api/data-files/download?'+new URLSearchParams({resource_id:item.resource_id!,version_id:item.source_version!.version_id});}
export type ResourceReport={profile:'cospace.data-resources/0.1';workspace_id:string;category:string;project_id:string|null;space_id:string|null;placement?:string;ownership?:string;lifecycle?:string;items:ResourceItem[];total:number;spaces:{id:string;name:string;project_id:string|null}[];can_manage:boolean;status:'ready'|'partial';offset:number;limit:number;next_offset:number|null;observed_at:string;source_files_rechecked:false};
type ResourceScope={workspace:string;project:string;space:string;category:string;placement?:string;ownership?:string;lifecycle?:string};
function validateFileOwner(item:ResourceItem){
 if(item.owner_kind==='project')return /^project-[a-f0-9]{16}$/.test(item.owner_project_id||'');
 return item.owner_kind==='workspace'&&item.owner_project_id===null;
}
function validateFileResource(item:ResourceItem,scope:ResourceScope){
 const identity=/^resource-[a-f0-9]{32}$/.test(item.resource_id||'')&&item.key===item.resource_id&&item.record_id===item.resource_id;
 const version=!!item.source_version&&/^[a-f0-9]{64}$/.test(item.source_version.version_id)&&item.source_version.reference_kind==='source_metadata';
 const registration=item.registered&&item.version_registered&&Number.isInteger(item.version_count)&&item.version_count>=1&&item.version_count<=1000&&Number.isInteger(item.revision)&&item.revision>=1;
 const placement=item.href===null&&item.space_id===null&&item.space_name===null&&!item.external&&item.project_id===item.owner_project_id;
 if(!identity||!version||!registration||!placement||!validateFileOwner(item)||item.resource_type!=='reference'||typeof item.label!=='string'||scope.category==='process'||scope.space||scope.project&&item.owner_project_id!==scope.project)throw new Error('项目级资料引用无效。');
}
function validateExternalResource(item:ResourceItem,scope:ResourceScope){
 if(item.href!==null||item.space_id!==null||item.space_name!==null||item.can_manage!==false||!item.registered||!item.resource_id||item.record_id!==item.resource_id||item.key!==item.resource_id||!Array.isArray(item.uses)||!item.uses.length||item.uses.some(u=>!validUse(u)||u.resource_id!==item.resource_id||u.status!=='active'||scope.project&&u.project_id!==scope.project||scope.space&&u.space_id!==scope.space)||scope.category==='process')throw new Error('外部引用无效。');
}
function validateSceneResource(item:ResourceItem,report:ResourceReport){
 if(typeof item.href!=='string')throw new Error('数据来源引用缺失。');
 const href=new URL(item.href,'https://cospace.test');
 const process=['job','batch','preflight'].includes(item.kind);
 if(!/^#(?:data|build)\?/.test(item.href)||href.hash.split('?')[0]!==('#'+(item.kind==='job'?'build':'data'))||new URLSearchParams(item.href.split('?')[1]).get('space')!==item.space_id||!report.spaces.some(s=>s.id===item.space_id)||typeof item.label!=='string'||process!==(report.category==='process')||process&&(item.resource_id!==null||item.source_version!==null)||!process&&(!/^resource-[a-f0-9]{32}$/.test(item.resource_id||'')||!item.source_version)||item.source_version&&(!/^[a-f0-9]{64}$/.test(item.source_version.version_id)||item.source_version.reference_kind!=='source_metadata'))throw new Error('数据资源引用无效。');
}
export function parseResourceReport(value:unknown,scope:ResourceScope):ResourceReport{
 const v=value as ResourceReport;
 if(v?.profile!=='cospace.data-resources/0.1'||scope.workspace&&v.workspace_id!==scope.workspace||(v.project_id||'')!==scope.project||(v.space_id||'')!==scope.space||v.category!==scope.category||!Array.isArray(v.items)||!Array.isArray(v.spaces)||!Number.isInteger(v.total)||v.total<0||!['ready','partial'].includes(v.status)||v.source_files_rechecked!==false)throw new Error('数据目录响应与当前范围不一致。');
 if((v.placement||'all')!==(scope.placement||'all')||(v.ownership||'all')!==(scope.ownership||'all')||(v.lifecycle||'all')!==(scope.lifecycle||'all'))throw new Error('数据筛选响应与当前范围不一致。');
 for(const item of v.items){
  if(item.lifecycle_state!=null&&!['active','archived','disabled'].includes(item.lifecycle_state)||item.external&&item.lifecycle_state!=null||scope.lifecycle&&scope.lifecycle!=='all'&&item.lifecycle_state!==scope.lifecycle)throw new Error('数据使用状态无效。');
  if(item.external)validateExternalResource(item,scope);
  else if(item.kind==='resource_file')validateFileResource(item,scope);
  else validateSceneResource(item,v);
 }
 return v;
}
export function resourceScopeLabel(item:ResourceItem){
 if(item.space_name)return item.space_name;
 if(item.external)return '项目级引用';
 return item.owner_kind==='workspace'?'工作区共用资料':'项目级资料';
}
