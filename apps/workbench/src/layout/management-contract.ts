export type ManagementPage='settings'|'account';
export const managementPages={
 settings:{label:'工作区与授权',description:'管理场景操作角色、成员授权及调整记录。'},
 account:{label:'个人信息',description:'查看基本身份与当前工作区内的产品角色。'},
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
 'build.run':'模型构建','association.edit':'空间关联','publication.manage':'服务发布','space.manage':'名称与描述管理','space.location.edit':'空间位置编辑',
};
