import React from 'react';
import {Link} from 'react-router-dom';
import {ShellSidebarNav,type ShellNavSection} from '@vxture/design-system';
import {serviceSections,type ServiceSection} from './spatial-service-contract';

const ServiceLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=>{const key=new URLSearchParams(href.split('?')[1]).get('section') as ServiceSection;return <Link {...props} aria-label={serviceSections[key]} ref={ref} to={href}/>;});
ServiceLink.displayName='ServiceLink';
const sections:ShellNavSection[]=[{title:'功能导航',items:[
 {href:'/services?section=directory',label:'服务目录',icon:'cube'},
 {href:'/services?section=offline',label:'离线交付',icon:'download'},
 {href:'/services?section=online',label:'在线服务',icon:'cloud'},
 {href:'/services?section=feedback',label:'态势反馈',icon:'upload'},
 {href:'/services?section=recipients',label:'服务对象',icon:'users'}
]}];
export function ServiceNavigation({section,collapsed,onToggle}:{section:ServiceSection;collapsed:boolean;onToggle:()=>void}){
 return <ShellSidebarNav domainName="空间服务" sections={sections} collapsed={collapsed} onToggleCollapsed={onToggle} isActive={href=>href===`/services?section=${section}`} storageKeyPrefix="cospace.services.navigation" linkComponent={ServiceLink} labels={{expandNav:'展开功能导航',collapseNav:'收起功能导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
}
