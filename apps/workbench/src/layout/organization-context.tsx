import React,{useState} from 'react';
import {Button,Popover,PopoverTrigger,ShellPanelContent,ShellPanelRow} from '@vxture/design-system';
import {Buildings,User,Cube,CaretDown} from '@phosphor-icons/react';
import defaultLogo from '@vxture/design-system/assets/icons/tenant-default.png';
import {organizationContext} from './account-profile';
import {usePlatformSession} from './platform-auth';

export function OrganizationContext(){
 const session=usePlatformSession(),user=session?.user;
 const context=organizationContext(user),[failed,setFailed]=useState<string|null>(null);
 const source=user?.org_logo_url||defaultLogo;
 const TypeIcon=user?.org_type==='personal'||user?.org_type==='individual'?User:Buildings;
 return <Popover><PopoverTrigger asChild><Button variant="ghost" size="sm" className="header-organization-trigger" aria-label={`当前组织与工作区：${context.label}`} title={context.label}>
  <Buildings size={16}/><span className="header-organization-name">{context.shortName}</span><span aria-hidden="true">·</span><span className="header-workspace-name">{context.workspaceName}</span><CaretDown size={12}/>
 </Button></PopoverTrigger><ShellPanelContent align="start" sideOffset={8} className="header-organization-panel" aria-label="组织与工作区信息">
  <div className="header-organization-summary"><div className="header-organization-logo">{failed===source?<TypeIcon size={36}/>:<img src={source} alt="组织 Logo" referrerPolicy="no-referrer" onError={()=>setFailed(source)}/>}</div>
   <div className="header-organization-details"><div className="header-organization-title"><strong>{context.fullName}</strong><span className="header-organization-type">{context.typeLabel}</span></div><p><Cube size={14}/><span>{context.workspaceName}</span></p></div>
  </div>
  <div className="header-organization-links"><ShellPanelRow icon="app-grid" label="应用中心" description="访问全部智能体应用，进入个人门户" href="https://ruyin.work/" newTab trailingIcon="external-link" className="header-organization-link"/><ShellPanelRow icon="building" label="组织信息" description="查看组织与空间信息，前往控制台管理" href="https://console.vxture.com/" newTab trailingIcon="external-link" className="header-organization-link"/></div>
 </ShellPanelContent></Popover>;
}
