import React from 'react';
import {Bell,Question} from '@phosphor-icons/react';
import {ShellIconButton,Popover,PopoverTrigger,ShellPanelContent,ShellPanelSection} from '@vxture/design-system';

export function HeaderSupportControls(){
 return <>
  <Popover><PopoverTrigger asChild><ShellIconButton icon="bell" label="通知"><Bell size={16}/></ShellIconButton></PopoverTrigger><ShellPanelContent align="end"><ShellPanelSection title="通知"><p className="header-support-copy">通知服务尚未接入。</p></ShellPanelSection></ShellPanelContent></Popover>
  <Popover><PopoverTrigger asChild><ShellIconButton icon="bell" label="帮助"><Question size={16}/></ShellIconButton></PopoverTrigger><ShellPanelContent align="end"><ShellPanelSection title="帮助"><div className="header-support-copy"><p>从“我的场景”选择场景，进入后使用功能导航开展工作。</p><p>地图支持场景定位和状态筛选，未登记位置的场景可从清单查看。</p></div></ShellPanelSection></ShellPanelContent></Popover>
 </>;
}
