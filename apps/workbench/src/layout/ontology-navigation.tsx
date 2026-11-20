import {ShellSidebarNav} from './shell-navigation';
import React,{useEffect,useState} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {Button,ShellSidebarFrame,Drawer,useMediaQuery,type ShellNavSection} from '@vxture/design-system';
import {SidebarSimple} from '@phosphor-icons/react';
import type {LibrarySelection} from '@vxture/ontology-ui';
import './ontology-navigation.css';

export function ontologySelectionHref(s:LibrarySelection,category='all'){return '/ontology?'+new URLSearchParams({tab:'library',category,...(s.moduleId?{module:s.moduleId}:{}),...(s.kind?{kind:s.kind,term:s.term||''}:{})});}
const OntologyLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=><Link {...props} ref={ref} to={href}/>);
OntologyLink.displayName='OntologyLink';
export function OntologyNavigation({category,view}:{category:string;view:string}){
 const narrow=useMediaQuery('(max-width:639px)'),[collapsed,setCollapsed]=useState(false),[open,setOpen]=useState(false),location=useLocation();
 useEffect(()=>setOpen(false),[location.pathname,location.search]);
 const sections:ShellNavSection[]=[{title:'本体资源',items:[
  {href:ontologySelectionHref({moduleId:''},'all'),label:'全部本体',icon:'database'},
  {href:ontologySelectionHref({moduleId:''},'core'),label:'通用核心',icon:'cube'},
  {href:ontologySelectionHref({moduleId:''},'domain'),label:'领域本体',icon:'tree-structure'}
 ]}];
 const navigation=(compact:boolean,toggle:()=>void)=><ShellSidebarNav domainName="语义本体" sections={sections} collapsed={compact} onToggleCollapsed={toggle} isActive={href=>view==='library'&&new URLSearchParams(href.split('?')[1]).get('category')===category} storageKeyPrefix="cospace.ontology.navigation" linkComponent={OntologyLink} labels={{expandNav:'展开本体导航',collapseNav:'收起本体导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
 return narrow?<><Button className="data-navigation-open" variant="ghost" size="icon-sm" aria-label="展开本体导航" onClick={()=>setOpen(true)}><SidebarSimple size={16}/></Button><Drawer open={open} onClose={()=>setOpen(false)} side="left" width="sm" title="本体导航" closeLabel="关闭本体导航">{navigation(false,()=>setOpen(false))}</Drawer></>:<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}>{navigation(collapsed,()=>setCollapsed(v=>!v))}</ShellSidebarFrame>;
}
