import React,{useState} from 'react';
import {Popover,PopoverTrigger,ShellScopeButton,ShellPanelContent,ShellPanelHeader,ShellPanelSection,ShellPanelRow,StatusBadge} from '@vxture/design-system';
import {Buildings,BuildingOffice} from '@phosphor-icons/react';
import defaultLogo from '@vxture/design-system/assets/icons/tenant-default.png';
import {organizationContext} from './account-profile';
import {usePlatformSession} from './platform-auth';

export function OrganizationContext(){
 const session=usePlatformSession(),user=session?.user;
 const context=organizationContext(user),[open,setOpen]=useState(false);
 const TypeIcon=user?.org_type==='personal'||user?.org_type==='individual'?BuildingOffice:Buildings;
 return <Popover open={open} onOpenChange={setOpen}><PopoverTrigger asChild><ShellScopeButton className="header-organization-trigger" icon="buildings" ariaLabel={`当前组织与工作区：${context.label}`} active={open} caret label={
  <span className="flex min-w-0 items-center gap-2xs whitespace-nowrap"><span className="header-organization-name text-sm font-normal text-foreground">{context.shortName}</span><span aria-hidden="true" className="text-xs text-muted-foreground">·</span><span className="header-workspace-name text-xs font-normal text-muted-foreground">{context.workspaceName}</span></span>
 }/></PopoverTrigger><ShellPanelContent align="start" className="header-organization-panel gap-lg" aria-label="组织与工作区信息">
  <ShellPanelHeader lead="avatar" avatarSrc={user?.org_logo_url||defaultLogo} avatarAlt={context.fullName} avatarFallback={<TypeIcon size={16}/>} className="[&>span]:rounded-md [&>span>span]:rounded-md" title={context.fullName} titleAside={<StatusBadge size="xs" tone="neutral" icon={false}>{context.typeLabel}</StatusBadge>} metaRows={[{key:'workspace',icon:'workspace',content:context.workspaceName}]}/>
  <ShellPanelSection className="gap-md"><ShellPanelRow icon="squares-four" label="应用中心" description="访问全部智能体应用，进入个人门户" href="https://ruyin.work/" newTab trailingIcon="external-link"/><ShellPanelRow icon="buildings" label="组织信息" description="查看组织与空间信息，前往控制台管理" href="https://console.vxture.com/" newTab trailingIcon="external-link"/></ShellPanelSection>
 </ShellPanelContent></Popover>;
}
