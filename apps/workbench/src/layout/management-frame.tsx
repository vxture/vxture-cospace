import {ShellSidebarNav} from './shell-navigation';
import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,Drawer,ShellSidebarFrame,useMediaQuery,type ShellNavSection} from '@vxture/design-system';
import {SidebarSimple,Users,IdentificationCard,Gear,SquaresFour} from '@phosphor-icons/react';
import {WorkspaceHeading} from './workspace-frame';
import {useRecordNavigation} from './record-navigation';
import {appLocation,appNavigate} from './app-router';
import {managementPages,managementPage,managementHref,managementSections,managementSection} from './management-contract';
import './scene-catalog.css';
import './spatial-services.css';
import './management-frame.css';

const pages={
 settings:{...managementPages.settings,icon:'users',heading:Users},
 account:{...managementPages.account,icon:'user',heading:IdentificationCard},
} as const;
const ManagementLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=><Link {...props} ref={ref} to={href}/>);
ManagementLink.displayName='ManagementLink';

export function ManagementFrame({route,children}:Readonly<{route:'settings'|'members'|'identity'|'account';children:React.ReactNode}>){
 const {space}=useRecordNavigation();
 const current=managementPage(route),location=appLocation();
 const section=managementSection(new URLSearchParams(location.split('?')[1]||'').get('section')||(route==='members'?'permissions':null));
 const href=managementHref(route,space,section);
 useEffect(()=>{if(location!==href)appNavigate(href,true);},[href,location]);
 const [collapsed,setCollapsed]=useState(false),[open,setOpen]=useState(false);
 const narrow=useMediaQuery('(max-width:639px)');
 useEffect(()=>setOpen(false),[route]);
 const sections:ShellNavSection[]=[
  {title:'配置管理',items:[{href:managementHref('settings',space),label:'配置总览',icon:'app-grid'}]},
  {title:'成员与权限',items:['roles','permissions'].map(key=>({href:managementHref('settings',space,key),label:managementSections[key as 'roles'|'permissions'].label,icon:managementSections[key as 'roles'|'permissions'].icon}))},
  {title:'业务配置',items:[{href:managementHref('settings',space,'advanced'),label:'高级配置',icon:'shield-check'}]},
  {title:'个人',items:[{href:'/account',label:'个人信息',icon:'user'}]},
 ];
 const navigation=(compact:boolean,toggle:()=>void)=><ShellSidebarNav domainName="配置与管理" sections={sections} collapsed={compact} onToggleCollapsed={toggle} isActive={link=>current==='account'?link==='/account':link.startsWith('/settings')&&managementSection(new URLSearchParams(link.split('?')[1]||'').get('section'))===section} storageKeyPrefix="cospace.management.navigation" linkComponent={ManagementLink} labels={{expandNav:'展开功能导航',collapseNav:'收起功能导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
 const page=current==='account'?pages.account:{...managementSections[section],heading:({overview:SquaresFour,roles:IdentificationCard,permissions:Users,advanced:Gear})[section]};
 return <main className="scene-catalog spatial-services management-domain" aria-label="配置与管理">
  {!narrow&&<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}>{navigation(collapsed,()=>setCollapsed(value=>!value))}</ShellSidebarFrame>}
  <div className="spatial-service-content"><div className="scene-catalog-shell">
   {narrow&&<Button variant="ghost" size="sm" onClick={()=>setOpen(true)}><SidebarSimple size={16}/>功能导航</Button>}
   <WorkspaceHeading icon={page.heading} title={page.label} description={page.description}/>
   <div className="management-page-content">{children}</div>
  </div></div>
  <Drawer open={narrow&&open} onClose={()=>setOpen(false)} side="left" width="sm" title="功能导航" closeLabel="关闭功能导航">{navigation(false,()=>setOpen(false))}</Drawer>
 </main>;
}
