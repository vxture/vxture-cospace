import {businessEndpoint} from './business-endpoint';
export type BusinessProject={id:string;name:string;description:string;status:'active'|'archived';scene_count:number;created_at:string;legacy_project_id?:string|null};
export type ProjectScene={space_id:string;name:string;project_id:string|null;project_name:string|null;origin_project_id:string;can_manage:boolean};
export type ProjectPage<T>={profile:'cospace.business-projects/0.1';workspace_id:string;view:string;items:T[];revision:number;total:number;next_offset:number|null;can_manage:boolean};
const errors:Record<string,string>={project_revision_changed:'项目记录已变化，请重新读取后操作。',resource_revision_changed:'资源登记已变化，请重新读取。',resource_source_changed:'来源版本已变化，请重新打开后核对。',resource_owner_transfer_not_supported:'已登记的管理归属不能在此转移。',active_project_required:'请选择当前工作区内的有效项目。',project_has_scene_associations:'项目仍有关联场景，请先处理关联。',project_has_managed_resources:'项目仍管理数据资源，暂不能归档。',technical_project_requires_explicit_association:'这是技术目录，请新建业务项目并关联场景。'};
export async function dataRequest(path:string,signal:AbortSignal,body?:Record<string,unknown>){
 const response=await fetch(businessEndpoint+path,{signal,cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const value=await response.json().catch(()=>{throw Error('数据服务响应无效，请刷新重试。');});
 if(!response.ok)throw Error(errors[value.detail]||(response.status===403?'当前身份无权访问或操作所选数据。':response.status===401?'请登录后继续。':'数据服务暂不可用，请刷新重试。'));
 return value;
}
export async function loadProjects<T=BusinessProject>(query:Record<string,string>,signal:AbortSignal,workspace=''):Promise<ProjectPage<T>>{
 const value=await dataRequest('/api/data-projects?'+new URLSearchParams(query),signal);
 if(value.profile!=='cospace.business-projects/0.1'||workspace&&value.workspace_id!==workspace||!Array.isArray(value.items)||value.view!==(query.view||'projects'))throw Error('项目目录响应无效。');
 return value;
}
