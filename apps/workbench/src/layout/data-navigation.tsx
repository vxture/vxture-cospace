import {ShellSidebarNav} from './shell-navigation';
import React,{useEffect,useState} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {Button,ShellSidebarFrame,Drawer,useMediaQuery,type ShellNavSection} from '@vxture/design-system';
import {SidebarSimple} from '@phosphor-icons/react';
import {dataResourceNavigation,dataCatalogHref} from './data-catalog-contract';

const DataLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=><Link {...props} ref={ref} to={href}/>);
DataLink.displayName='DataLink';
export function DataNavigation({category,view}:{category?:string;view?:string}){
 const narrow=useMediaQuery('(max-width:639px)');
 const [collapsed,setCollapsed]=useState(false),[open,setOpen]=useState(false);
 const location=useLocation();
 useEffect(()=>setOpen(false),[location.pathname,location.search]);
 const params=new URLSearchParams(location.search);
 const context=Object.fromEntries(['project','filter_space'].filter(key=>params.has(key)).map(key=>[key,params.get(key)!]));
 const sections:ShellNavSection[]=dataResourceNavigation.map(section=>({title:section.title,
  items:section.items.map(({category,label,icon})=>({href:dataCatalogHref({...context,category}),label,icon}))}));
 const navigation=(compact:boolean,toggle:()=>void)=><ShellSidebarNav domainName="数据管理" sections={sections} collapsed={compact} onToggleCollapsed={toggle} isActive={href=>!view&&new URLSearchParams(href.split('?')[1]).get('category')===(category||'all')} storageKeyPrefix="cospace.data.navigation" linkComponent={DataLink} labels={{expandNav:'展开数据管理导航',collapseNav:'收起数据管理导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
 return <>{narrow?<><Button className="data-navigation-open" variant="ghost" size="icon-sm" aria-label="展开数据管理导航" onClick={()=>setOpen(true)}><SidebarSimple size={16}/></Button><Drawer open={open} onClose={()=>setOpen(false)} side="left" width="sm" title="数据管理导航" closeLabel="关闭数据管理导航">{navigation(false,()=>setOpen(false))}</Drawer></>:<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}>{navigation(collapsed,()=>setCollapsed(v=>!v))}</ShellSidebarFrame>}</>;
}
