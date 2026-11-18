import {ViewModeSwitch} from '@vxture/design-system';
import type {ServicePresentation} from './service-workspace-contract';

export function ServiceListViewGroup({presentation,count}:Readonly<{presentation:ServicePresentation;count:string}>){
 return <div className="service-list-view-group">
  <ViewModeSwitch value={presentation.view} onChange={presentation.onView} ariaLabel="显示方式" labels={{cards:'卡片视图',list:'列表视图'}}/>
  <span className="service-list-count" aria-live="polite">{count}</span>
 </div>;
}
