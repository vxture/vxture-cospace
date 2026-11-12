import {ShellSidebarNav} from './shell-navigation';
import React,{useEffect,useState} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {Button,ShellSidebarFrame,Drawer,useMediaQuery,type ShellNavSection} from '@vxture/design-system';
import {SidebarSimple} from '@phosphor-icons/react';
import {recordLink} from './record-navigation';

const OntologyLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=><Link {...props} ref={ref} to={href}/>);
OntologyLink.displayName='OntologyLink';
export function OntologyNavigation({view,refs}:{view:string;refs:Record<string,string>}){
 const narrow=useMediaQuery('(max-width:1099px)'),[collapsed,setCollapsed]=useState(false),[open,setOpen]=useState(false);
 const location=useLocation();
 useEffect(()=>setOpen(false),[location.pathname,location.search]);
 const sections:ShellNavSection[]=[{title:'本体定义',items:[
  {href:recordLink('ontology',{...refs,tab:'authoring'}),label:'规则编制与封存',icon:'file'},
  {href:recordLink('ontology',{...refs,tab:'rules'}),label:'固定版本与校验',icon:'shield-check'}
 ]}];
 const navigation=(compact:boolean,toggle:()=>void)=><ShellSidebarNav domainName="语义本体" sections={sections} collapsed={compact} onToggleCollapsed={toggle} isActive={href=>new URLSearchParams(href.split('?')[1]).get('tab')===view} storageKeyPrefix="cospace.ontology.navigation" linkComponent={OntologyLink} labels={{expandNav:'展开本体导航',collapseNav:'收起本体导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
 return <>{narrow?<><Button className="data-navigation-open" variant="ghost" size="icon-sm" aria-label="展开本体导航" onClick={()=>setOpen(true)}><SidebarSimple size={16}/></Button><Drawer open={open} onClose={()=>setOpen(false)} side="left" width="sm" title="本体导航" closeLabel="关闭本体导航">{navigation(false,()=>setOpen(false))}</Drawer></>:<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}>{navigation(collapsed,()=>setCollapsed(v=>!v))}</ShellSidebarFrame>}</>;
}
