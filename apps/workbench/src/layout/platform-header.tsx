import React from 'react';
import {ShellHeader} from '@vxture/design-system';
import './platform-header.css';

// Product-wide control geometry; the DS retains each page's header height.
export function PlatformHeader({className,...props}:React.ComponentProps<typeof ShellHeader>){
 return <ShellHeader {...props} className={['platform-header',className].filter(Boolean).join(' ')}/>;
}
