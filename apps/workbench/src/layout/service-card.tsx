import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Button,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem} from '@vxture/design-system';
import {DotsThreeVertical,ArrowRight} from '@phosphor-icons/react';
import './service-card.css';

export type ServiceCardAction={key:string;label:string;icon:ReactNode;href:string;newTab?:boolean};

export function ServiceCardActions({label,items}:{label:string;items:ServiceCardAction[]}){
 if(!items.length)return null;
 if(items.length===1){const item=items[0];return <Button asChild variant="outline" size="xl"><Link to={item.href} target={item.newTab?'_blank':undefined} rel={item.newTab?'noopener noreferrer':undefined} aria-label={`${item.label}：${label}`}>{item.label}<ArrowRight size={16}/></Link></Button>;}
 return <DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline" size="icon-xl" aria-label={`${label}更多操作`}><DotsThreeVertical size={20}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="service-card-menu">{items.map(item=><DropdownMenuItem asChild key={item.key}><Link to={item.href} target={item.newTab?'_blank':undefined} rel={item.newTab?'noopener noreferrer':undefined}>{item.icon}{item.label}</Link></DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>;
}

export function ServiceCard({label,symbol,heading,children,metadata,actions,onOverview,artwork}:{
 label:string;symbol:ReactNode;heading:ReactNode;children:ReactNode;metadata?:ReactNode;actions?:ReactNode;onOverview:()=>void;artwork?:ReactNode;
}){
 return <article className="service-card" aria-label={label}>
  {artwork}
  <button type="button" className="service-card-open" aria-label={`查看${label}概要`} aria-haspopup="dialog" onClick={onOverview}/>
  <header className="service-card-header"><div className="service-card-symbol" aria-hidden="true">{symbol}</div><div className="service-card-heading">{heading}</div></header>
  <div className="service-card-body">{children}</div>
  <footer className="service-card-footer"><div className="service-card-meta">{metadata}</div><div className="service-card-actions">{actions}</div></footer>
 </article>;
}
