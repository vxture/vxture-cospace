export type ManagementPage='settings'|'account';
export const managementPages={
 settings:{label:'工作区与授权',description:'查看当前组织、工作区与场景访问权限。'},
 account:{label:'账户与登录',description:'查看当前账户与登录状态，前往账号中心维护资料。'},
} as const;
export function managementPage(route:string):ManagementPage{return route==='identity'||route==='account'?'account':'settings';}
export function managementHref(route:string,space=''){
 const page=managementPage(route);
 return '/'+page+(page==='settings'&&space?'?'+new URLSearchParams({space}):'');
}
export function sceneInformationHref(space:string){return '/build?'+new URLSearchParams({space,tab:'info'});}
export function canOpenSceneWorkspace(route:string,tab:string,capabilities:readonly string[]){
 if(route==='build'&&tab==='info')return capabilities.includes('space.preview');
 const required:Record<string,string>={build:'build.run',data:'data.manage',association:'association.edit'};
 return !required[route]||capabilities.includes(required[route]);
}
export const capabilityNames:Record<string,string>={
 'space.preview':'空间浏览','space.query':'空间查询','space.export':'成果导出','data.manage':'数据管理',
 'build.run':'模型构建','association.edit':'空间关联','publication.manage':'服务发布','space.manage':'基本信息管理',
};
