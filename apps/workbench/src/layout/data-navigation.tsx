import React,{useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,ShellSidebarFrame,ShellSidebarNav,Drawer,useMediaQuery,type ShellNavSection} from '@vxture/design-system';
import {SidebarSimple} from '@phosphor-icons/react';
import {recordLink,useRecordNavigation} from './record-navigation';

const DataLink=React.forwardRef<HTMLAnchorElement,React.AnchorHTMLAttributes<HTMLAnchorElement>>(({href='',...props},ref)=><Link {...props} ref={ref} to={href}/>);
DataLink.displayName='DataLink';
export function DataNavigation({category,view}:{category?:string;view?:string}){
 const target=useRecordNavigation(),narrow=useMediaQuery('(max-width:1099px)');
 const [collapsed,setCollapsed]=useState(false),[open,setOpen]=useState(false);
 const sections:ShellNavSection[]=[{title:'数据目录',items:[
  {href:recordLink('data',{scope:'all',filter_space:target.space,category:'all'}),label:'全部数据',icon:'database'},
  {href:recordLink('data',{scope:'all',filter_space:target.space,category:'original'}),label:'原始与输入',icon:'file'},
  {href:recordLink('data',{scope:'all',filter_space:target.space,category:'process'}),label:'过程数据',icon:'archive'},
  {href:recordLink('data',{scope:'all',filter_space:target.space,category:'result'}),label:'成果数据',icon:'archive'}
 ]}];
 if(target.space)sections.push({title:'场景数据',items:[
  {href:recordLink('data',{tab:'inputs'}),label:'资料与预检',icon:'file'},
  {href:recordLink('data',{tab:'references'}),label:'配套资料',icon:'link'},
  {href:recordLink('data',{tab:'pointcloud'}),label:'场景点云',icon:'cube'},
  {href:recordLink('data',{tab:'batches'}),label:'采集批次',icon:'archive'},
  {href:recordLink('data',{tab:'versions'}),label:'场景版本',icon:'archive'},
  {href:recordLink('data',{tab:'lineage'}),label:'来源追溯',icon:'git-branch'}
 ]});
 const navigation=(compact:boolean,toggle:()=>void)=><ShellSidebarNav domainName="数据管理" sections={sections} collapsed={compact} onToggleCollapsed={toggle} isActive={href=>{const p=new URLSearchParams(href.split('?')[1]);return view?p.get('tab')===view:!p.has('tab')&&p.get('category')===(category||'all');}} storageKeyPrefix="cospace.data.navigation" linkComponent={DataLink} labels={{expandNav:'展开数据管理导航',collapseNav:'收起数据管理导航',expandAllGroups:'展开导航分组',collapseAllGroups:'收起导航分组'}}/>;
 return <>{narrow?<><Button className="data-navigation-open" variant="ghost" size="icon-sm" aria-label="展开数据管理导航" onClick={()=>setOpen(true)}><SidebarSimple size={16}/></Button><Drawer open={open} onClose={()=>setOpen(false)} side="left" width="sm" title="数据管理导航" closeLabel="关闭数据管理导航"><div onClick={event=>{if((event.target as HTMLElement).closest('a'))setOpen(false);}}>{navigation(false,()=>setOpen(false))}</div></Drawer></>:<ShellSidebarFrame mode={collapsed?'collapsed':'expanded'}>{navigation(collapsed,()=>setCollapsed(v=>!v))}</ShellSidebarFrame>}</>;
}
