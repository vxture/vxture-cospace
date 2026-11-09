import React from 'react';
import {ShellPanelSection,ShellPanelRow} from '@vxture/design-system';
import {moduleGroups,moduleNames,type ModuleRoute} from './product-navigation';
import './product-launcher.css';

/** Product navigation only; scene selection deliberately clears record scope. */
export function ProductLauncher({route,hasScene=false,hrefForRoute,onNavigate}:{route?:string;hasScene?:boolean;hrefForRoute:(route:ModuleRoute)=>string;onNavigate:()=>void}){
 const work=moduleGroups.find(group=>group.title==='场景作业')!;
 const resources=moduleGroups.find(group=>group.title==='公共资源')!;
 return <nav className="product-launcher-grid" aria-label="功能 Launcher">
  <ShellPanelSection title={<span className="product-launcher-section-title">场景中心<small>默认首页</small></span>} divided={false} className="product-launcher-group product-launcher-home">
   <ShellPanelRow icon="app-grid" label="我的场景" description="查看、选择与创建场景" chevron={false} href="/space" active={route==='space'&&!hasScene} onClick={onNavigate}/>
   <p className="product-launcher-home-note">从场景开始，连接数据、构建与服务。</p>
  </ShellPanelSection>
  {[work,resources].map(group=><ShellPanelSection key={group.title} title={group.title} divided={false} className="product-launcher-group">
   {group.items.map(item=><ShellPanelRow key={item.route} icon={item.icon} label={moduleNames[item.route]} description={item.route==='space'&&!hasScene?'选择场景后浏览空间':item.description} href={item.route==='space'&&!hasScene?undefined:hrefForRoute(item.route)} disabled={item.route==='space'&&!hasScene} active={route===item.route&&(item.route!=='space'||hasScene)} onClick={onNavigate}/>)}
  </ShellPanelSection>)}
 </nav>;
}
