import React,{useState} from 'react';
import {Button} from '@vxture/design-system';
import {CaretLeft,CaretRight} from '@phosphor-icons/react';
import './workspace-frame.css';

type Symbol=React.ComponentType<{size?:number;className?:string}>;
export function WorkspaceHeading({icon:Symbol,title,description,actions,secondary}:{icon:Symbol;title:string;description:React.ReactNode;actions?:React.ReactNode;secondary?:React.ReactNode}){
 return <header className="workspace-page-heading"><Symbol size={28}/><div className="workspace-page-copy"><div><h1>{title}</h1>{secondary}</div><p>{description}</p></div>{actions&&<div className="workspace-page-actions">{actions}</div>}</header>;
}
export function WorkspaceNavigation({title,icon:Symbol,children}:{title:string;icon:Symbol;children:React.ReactNode}){
 const [open,setOpen]=useState(()=>innerWidth>=1100);
 return <>{open?<aside className="workspace-navigation" aria-label={`${title}导航`}><header><Symbol size={18}/><h2>{title}</h2><Button variant="ghost" size="icon-sm" aria-label={`收起${title}导航`} onClick={()=>setOpen(false)}><CaretLeft size={14}/></Button></header><div className="workspace-navigation-surface" onClick={event=>{if(innerWidth<1100&&(event.target as HTMLElement).closest('a,button'))setOpen(false);}}>{children}</div></aside>:<Button className="workspace-navigation-expand" variant="ghost" size="icon-sm" aria-label={`展开${title}导航`} onClick={()=>setOpen(true)}><CaretRight size={16}/></Button>}</>;
}
