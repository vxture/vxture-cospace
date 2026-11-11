import React,{useState} from 'react';
import {Button} from '@vxture/design-system';
import {CaretLeft,CaretRight} from '@phosphor-icons/react';
import './workspace-frame.css';

type WorkspaceIcon=React.ComponentType<{size?:number;className?:string}>;
export function WorkspaceHeading({icon:HeadingIcon,title,description,actions,secondary}:{icon:WorkspaceIcon;title:string;description:React.ReactNode;actions?:React.ReactNode;secondary?:React.ReactNode}){
 return <header className="workspace-page-heading"><HeadingIcon size={28}/><div className="workspace-page-copy"><div><h1>{title}</h1>{secondary}</div><p>{description}</p></div>{actions&&<div className="workspace-page-actions">{actions}</div>}</header>;
}
export function WorkspaceNavigation({title,icon:NavigationIcon,children}:{title:string;icon:WorkspaceIcon;children:React.ReactNode}){
 const [open,setOpen]=useState(()=>innerWidth>=1100);
 return <>{open?<aside className="workspace-navigation" aria-label={`${title}导航`}><header><NavigationIcon size={18}/><h2>{title}</h2><Button variant="ghost" size="icon-sm" aria-label={`收起${title}导航`} onClick={()=>setOpen(false)}><CaretLeft size={14}/></Button></header><div className="workspace-navigation-surface">{children}</div></aside>:<Button className="workspace-navigation-expand" variant="ghost" size="icon-sm" aria-label={`展开${title}导航`} onClick={()=>setOpen(true)}><CaretRight size={16}/></Button>}</>;
}
