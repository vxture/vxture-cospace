export type ManagementPage='settings'|'account';
export const managementPages={
 settings:{label:'概览',description:'管理 CoSpace 产品角色、成员场景授权与业务配置。'},
 account:{label:'个人信息',description:'查看基本身份与当前工作区内的产品角色。'},
} as const;
export function managementPage(route:string):ManagementPage{return route==='identity'||route==='account'?'account':'settings';}
export function managementHref(route:string,space='',section=route==='members'?'members':'overview'){
 const page=managementPage(route);
 const params=new URLSearchParams();
 if(page==='settings'){if(space)params.set('space',space);if(section!=='overview')params.set('section',managementSection(section));}
 return '/'+page+(params.size?'?'+params:'');
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

export const managementSections={
 overview:{label:'概览',description:'管理 CoSpace 产品角色、成员场景授权与业务配置。',icon:'app-grid'},
 members:{label:'成员管理',description:'搜索本产品已记录成员，查看角色并分配场景权限。',icon:'users'},
 roles:{label:'角色管理',description:'查看固定产品角色及其能力边界，按实际场景范围分配。',icon:'user'},
 permissions:{label:'权限管理',description:'查看产品操作权限及拥有这些权限的角色。',icon:'shield-check'},
 scenes:{label:'场景管理',description:'管理成员可见的场景数据范围，与功能权限独立生效。',icon:'cube'},
 advanced:{label:'高级配置',description:'维护现有业务规则与场景配置，按实际授权范围操作。',icon:'shield-check'},
} as const;
export type ManagementSection=keyof typeof managementSections;
export function managementSection(value:string|null):ManagementSection{return value&&Object.hasOwn(managementSections,value)?value as ManagementSection:'overview';}
export const productRoleDefinitions=[
 {role:'所有者',scene:'全部场景操作',advanced:'系统高级配置',members:'本工作区全部场景授权',scope:'由平台工作区所有权确定'},
 {role:'管理者',scene:'全部场景操作',advanced:'系统高级配置',members:'对应管理范围内授权',scope:'按已授权场景生效'},
 {role:'工程师',scene:'新建、编辑、管理、构建、发布与导出',advanced:'无系统高级配置权限',members:'无人员授权权限',scope:'按已授权场景生效'},
 {role:'查看者',scene:'查看、预览与查询',advanced:'无系统高级配置权限',members:'无人员授权权限',scope:'默认查看者 · 受数据范围限制'},
] as const;
