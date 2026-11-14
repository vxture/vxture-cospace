import React from 'react';
import {ShellPanelSection,ShellPanelRow} from '@vxture/design-system';
import {moduleGroups,moduleNames,type ModuleRoute} from './product-navigation';
import './product-launcher.css';

/** Product navigation only; scene selection deliberately clears record scope. */
export function ProductLauncher({route,hasScene=false,hrefForRoute,onNavigate}:{route?:string;hasScene?:boolean;hrefForRoute:(route:ModuleRoute)=>string;onNavigate:()=>void}){
 const work=moduleGroups.find(group=>group.title==='场景作业')!;
 const resources=moduleGroups.find(group=>group.title==='公共资源')!;
 return <nav className="product-launcher" aria-label="功能 Launcher">
  <div className="product-launcher-workbench">
   <ShellPanelRow icon="app-grid" label="工作台" chevron={false} href="/" active={route==='home'} onClick={onNavigate}/>
  </div>
  <div className="product-launcher-grid">
  <ShellPanelSection title={<span className="product-launcher-section-title">场景中心</span>} divided={false} className="product-launcher-group product-launcher-home">
   <ShellPanelRow icon="app-grid" label="我的场景" description="查看、选择与创建场景" chevron={false} href="/space" active={route==='space'&&!hasScene} onClick={onNavigate}/>
   <ShellPanelRow icon="globe" label="空间服务" description="发现服务与获取接入支持" chevron={false} href="/services" active={route==='services'} onClick={onNavigate}/>
  </ShellPanelSection>
  {[work,resources].map(group=><ShellPanelSection key={group.title} title={<span className="product-launcher-section-title">{group.title}</span>} divided={false} className="product-launcher-group">
   {group.items.filter(item=>item.route!=='space').map(item=><ShellPanelRow key={item.route} icon={item.icon} label={moduleNames[item.route]} description={item.description} href={hrefForRoute(item.route)} active={route===item.route} onClick={onNavigate}/>)}
  </ShellPanelSection>)}

  </div>
 </nav>;
}
