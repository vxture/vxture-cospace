import {ShellSidebarNav} from './shell-navigation';
import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,Drawer,ShellSidebarFrame,useMediaQuery,type ShellNavSection} from '@vxture/design-system';
import {SidebarSimple,Users,IdentificationCard} from '@phosphor-icons/react';
import {WorkspaceHeading} from './workspace-frame';
import {useRecordNavigation} from './record-navigation';
import {appLocation,appNavigate} from './app-router';
import {managementPages,managementPage,managementHref} from './management-contract';
import './scene-catalog.css';
import './spatial-services.css';
import './management-frame.css';

const pages={
 settings:{...managementPages.settings,icon:'users',heading:Users},
 account:{...managementPages.account,icon:'user',heading:IdentificationCard},
} as const;
const ManagementLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=><Link {...props} aria-label={pages[href.split('?')[0].slice(1) as keyof typeof pages]?.label} ref={ref} to={href}/>);
ManagementLink.displayName='ManagementLink';

export function ManagementFrame({route,children}:Readonly<{route:'settings'|'members'|'identity'|'account';children:React.ReactNode}>){
 const {space}=useRecordNavigation();
 const current=managementPage(route),href=managementHref(route,space),location=appLocation();
 useEffect(()=>{if(location!==href)appNavigate(href,true);},[href,location]);
 const [collapsed,setCollapsed]=useState(false),[open,setOpen]=useState(false);
 const narrow=useMediaQuery('(max-width:639px)');
 useEffect(()=>setOpen(false),[route]);
 const sections:ShellNavSection[]=[{title:'功能导航',items:Object.entries(pages).map(([key,page])=>({href:managementHref(key,space),label:page.label,icon:page.icon}))}];
 const navigation=(compact:boolean,toggle:()=>void)=><ShellSidebarNav domainName="配置与管理" sections={sections} collapsed={compact} onToggleCollapsed={toggle} isActive={href=>href.split('?')[0]===`/${current}`} storageKeyPrefix="cospace.management.navigation" linkComponent={ManagementLink} labels={{expandNav:'展开功能导航',collapseNav:'收起功能导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
 const page=pages[current];
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
