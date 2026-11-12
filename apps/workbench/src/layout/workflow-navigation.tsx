import React from 'react';
import {Button} from '@vxture/design-system';
import {CaretLeft,CaretRight} from '@phosphor-icons/react';
import './workflow-navigation.css';

/** Shared navigation control for the three scene workflow workspaces. */
export function WorkflowNavigationToggle({open,label,panelId,onToggle}:{open:boolean;label:string;panelId:string;onToggle:()=>void}) {
 const Icon=open?CaretLeft:CaretRight;
 return <Button variant="ghost" size="icon-sm" className={open?'workflow-nav-collapse':'workflow-nav-edge'} aria-label={`${open?'收起':'展开'}${label}导航`} aria-expanded={open} aria-controls={panelId} onClick={onToggle}><Icon size={16}/></Button>;
}
