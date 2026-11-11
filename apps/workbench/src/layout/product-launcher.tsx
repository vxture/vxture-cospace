import React from 'react';
import {Button,Collapsible,CollapsibleContent,CollapsibleTrigger,ShellPanelSection,ShellPanelRow,StatusBadge} from '@vxture/design-system';
import {CaretDown} from '@phosphor-icons/react';
import {useRecordNavigation} from './record-navigation';
import {businessEndpoint} from './business-endpoint';
import {moduleGroups,moduleNames,type ModuleRoute} from './product-navigation';
import './product-launcher.css';

/** Product navigation only; scene selection deliberately clears record scope. */
export function ProductLauncher({route,hasScene=false,hrefForRoute,onNavigate}:{route?:string;hasScene?:boolean;hrefForRoute:(route:ModuleRoute)=>string;onNavigate:()=>void}){
 const context=useRecordNavigation();
 const sceneQuery=context.space?'?'+new URLSearchParams({space:context.space}):'';
 const migrationPages=[
  {label:'空间预览',icon:'cube',href:context.space?'/space'+sceneQuery:undefined,description:context.space?'旧版场景发布目录':'选择场景后可打开'},
  {label:'业务配置',icon:'settings',href:'/settings'+sceneQuery,description:'旧版独立配置页'},
  {label:'成员与角色',icon:'users',href:'/members',description:'旧版成员入口'},
  {label:'登录集成',icon:'shield-check',href:'/identity',description:'旧版身份概览'},
  {label:'个人账户',icon:'user',href:'/account',description:'旧版产品账户页'},
  ...[{id:'equipment',name:'设备间'},{id:'pump',name:'水泵设备间'},{id:'inspection',name:'巡检设备区'}].map(item=>({label:item.name+'示例',icon:'cube' as const,href:'/space?'+new URLSearchParams({screen:'space',preview:'1',space:item.id}),description:'旧版合成示例大屏'})),
  {label:'旧版候选查看器',icon:'file',href:context.space&&context.job?businessEndpoint+'/candidates/'+encodeURIComponent(context.job)+'/':undefined,description:context.space&&context.job?'当前构建的历史 HTML 入口':'选择构建版本后可打开'},
  {label:'旧版发布查看器',icon:'package',href:context.space&&context.publication?businessEndpoint+'/publications/'+encodeURIComponent(context.publication)+'/':undefined,description:context.space&&context.publication?'当前发布的历史 HTML 入口':'选择发布版本后可打开'},
 ] as const;
 const work=moduleGroups.find(group=>group.title==='场景作业')!;
 const resources=moduleGroups.find(group=>group.title==='公共资源')!;
 return <nav className="product-launcher-grid" aria-label="功能 Launcher">
  <ShellPanelSection title={<span className="product-launcher-section-title">场景中心</span>} divided={false} className="product-launcher-group product-launcher-home">
   <ShellPanelRow icon="app-grid" label="我的场景" description="查看、选择与创建场景" chevron={false} href="/space" active={route==='space'&&!hasScene} onClick={onNavigate}/>
   <ShellPanelRow icon="globe" label="空间服务" description="发现服务与获取接入支持" chevron={false} href="/services" active={route==='services'} onClick={onNavigate}/>
  </ShellPanelSection>
  {[work,resources].map(group=><ShellPanelSection key={group.title} title={<span className="product-launcher-section-title">{group.title}</span>} divided={false} className="product-launcher-group">
   {group.items.filter(item=>item.route!=='space').map(item=><ShellPanelRow key={item.route} icon={item.icon} label={moduleNames[item.route]} description={item.description} href={hrefForRoute(item.route)} active={route===item.route} onClick={onNavigate}/>)}
  </ShellPanelSection>)}
  <Collapsible className="product-launcher-migration">
   <CollapsibleTrigger asChild><Button variant="ghost" className="product-launcher-migration-trigger" aria-label="待迁移页面"><span>待迁移<StatusBadge size="sm" tone="neutral">{migrationPages.length}</StatusBadge></span><CaretDown size={16}/></Button></CollapsibleTrigger>
   <CollapsibleContent><div className="product-launcher-migration-items">{migrationPages.map(item=><ShellPanelRow key={item.label} label={item.label} icon={item.icon} description={item.description} href={item.href} disabled={!item.href} chevron={false} onClick={onNavigate}/>)}</div></CollapsibleContent>
  </Collapsible>
 </nav>;
}
