import React from 'react';
import {ShellSidebarNav as DesignSystemSidebarNav} from '@vxture/design-system';
import './shell-navigation.css';

/** Console geometry for the installed DS 15 navigation / tokens 4 combination. */
export function ShellSidebarNav(props:React.ComponentProps<typeof DesignSystemSidebarNav>){
 return <div className="cospace-shell-navigation"><DesignSystemSidebarNav {...props}/></div>;
}
