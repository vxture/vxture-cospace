import {MemberManagement,RoleManagement} from './member-management';
import {useSearchParams} from 'react-router-dom';
import {ManagementOverview,AdvancedConfiguration} from './management-overview';
import React,{useEffect,useState} from 'react';
import {ShieldCheck,UserCircle} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {managementPage,managementSection} from './management-contract';
import {organizationContext} from './account-profile';
import {ScenePermissionsPanel} from './scene-permissions';
import {businessEndpoint} from './business-endpoint';
import {displayText} from './display-text';

function Information({items}:{readonly items:readonly (readonly [string,string|undefined])[]}){
 return <dl className="management-information">{items.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{displayText(value,'未提供')}</dd></div>)}</dl>;
}
function WorkspaceAccess(){
 return <section className="management-card" aria-label="场景权限管理"><h2><ShieldCheck size={20}/>场景权限</h2><ScenePermissionsPanel/></section>;
}
function AccountSummary(){
 const session=usePlatformSession(),user=session?.user,context=organizationContext(user);
 const [roles,setRoles]=useState<string[]>([]),[status,setStatus]=useState('正在读取角色…');
 useEffect(()=>{const controller=new AbortController();setRoles([]);setStatus('正在读取角色…');
  fetch(businessEndpoint+'/api/scene-permissions?summary=true',{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error('role_unavailable');
   const value=await response.json();
   if(value.workspace_id!==user?.workspace_id||!Array.isArray(value.self_roles))throw Error('role_unavailable');
   if(!controller.signal.aborted){setRoles(value.self_roles);setStatus('');}
  }).catch(()=>{if(!controller.signal.aborted)setStatus('角色暂不可读');});
  return()=>controller.abort();
 },[user?.subject,user?.org_id,user?.workspace_id]);
 const labels:Record<string,string>={owner:'所有者',manager:'管理者',engineer:'工程师',viewer:'查看者'};
 const roleText=roles.map(role=>labels[role]).filter(Boolean).join('、');
 return <section className="management-card"><h2><UserCircle size={20}/>个人信息</h2><Information items={[
  ['姓名',user?.display_name],['用户名',user?.username],['邮箱',user?.email],['电话',user?.phone],['组织',context.fullName],['工作区',context.workspaceName],['工作区内产品角色',roleText||status||'暂无额外角色'],
 ]}/><p className="text-body-small text-muted-foreground">产品角色以实际授权范围生效。</p></section>;
}
export function ManagementWorkspace({route}:{readonly route:string;readonly onLogout:()=>void|Promise<void>}){
 const [params]=useSearchParams();
 const section=managementSection(params.get('section'));
 if(managementPage(route)==='account')return <AccountSummary/>;
 if(section==='permissions')return <WorkspaceAccess/>;
 if(section==='members')return <MemberManagement/>;
 if(section==='roles')return <RoleManagement/>;
 if(section==='advanced')return <AdvancedConfiguration/>;
 return <ManagementOverview/>;
}
