import React from 'react';
import {ShellPageContainer} from '@vxture/design-system';

/** Shared page frame. The parent viewport measures space after navigation.
 * Section frames join the homepage regions; the final region keeps page safety.
 */
export function WorkspaceContent({children,className='',section=false}:{children:React.ReactNode;className?:string;section?:boolean}){
 return <ShellPageContainer width="wide-2xl" className={[
  'workspace-content-frame min-w-0',
  '[--workspace-content-inline:var(--space-md)]',
  '@page-sm/workspace:[--workspace-content-inline:var(--space-xl)]',
  '@page-lg/workspace:[--workspace-content-inline:var(--space-3xl)]',
  section?'workspace-content-section':'',className,
 ].join(' ')}>{children}</ShellPageContainer>;
}
