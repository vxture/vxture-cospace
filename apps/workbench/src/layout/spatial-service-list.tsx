import React,{useState} from 'react';
import {Link} from 'react-router-dom';
import {Drawer,StatusBadge} from '@vxture/design-system';
import {Cube,Cloud,DownloadSimple,Eye,Code} from '@phosphor-icons/react';
import {serviceKinds,sectionServices,type ServiceSpace,type ServiceVersion,type ServiceSection} from './spatial-service-contract';
import {servicePageHref,type ServiceListFilter} from './service-workspace-contract';
import {ServiceDirectoryRow} from './service-directory-row';
import {ServiceCard,ServiceCardActions} from './service-card';
import {serviceEntryDestinations} from './service-entry-actions';

export const serviceStateLabels={active:'已发布',paused:'已暂停',retired:'已退役',unknown:'待核对'};
export const serviceVersionLabel=(version:ServiceVersion)=>version.release.display_code||version.release.version_code||version.release.id.slice(-8);
export function ServiceListEntry({group,version,section,filter,view='list'}:{group:ServiceSpace;version:ServiceVersion;section:ServiceSection;filter:ServiceListFilter;view?:'cards'|'list'}){
 const [overview,setOverview]=useState(false);
 const href=servicePageHref(section,group.scene.id,version.release.id,undefined,filter);
 const ServiceIcon=section==='online'?Cloud:section==='offline'?DownloadSimple:Cube;
 const capabilityIcons={preview:Eye,query:Code,offline:DownloadSimple};
 const capabilities=sectionServices(version,section);
 const label=`${group.scene.name} · ${section==='online'?'在线服务':section==='offline'?'离线交付':'场景服务'}`;
 const icons={overview:Cube,online:Cloud,offline:DownloadSimple,feedback:Cloud,recipients:Cube};
 const actions=serviceEntryDestinations(group,version,section,filter).map(item=>{const Icon=icons[item.key];return {...item,icon:<Icon size={16}/>};});
 const controls=<ServiceCardActions label={group.scene.name} items={actions}/>;
 const status=<StatusBadge size="sm" icon={false} tone={version.available?'success':'neutral'}>{serviceStateLabels[version.state]}</StatusBadge>;
 const capabilityList=<div className="service-list-capabilities" aria-label="已授权能力">{capabilities.map(item=>{const Icon=capabilityIcons[item.kind];return <span key={item.kind}><Icon size={14}/>{serviceKinds[item.kind].label}</span>;})}</div>;
 const metadata=<><span title={version.release.id}>Ver: {serviceVersionLabel(version)}</span><span>{version.release.created_at.slice(0,10)||'时间未记录'} · {group.versions.length} 个版本</span></>;
 if(view==='cards')return <><ServiceCard label={label} symbol={<ServiceIcon size={26} weight="duotone"/>}
  heading={<><div className="service-card-title-line"><h3 title={group.scene.name}>{group.scene.name}</h3>{status}</div><span className="service-project">{group.scene.project_name||'未指定项目'}</span></>}
  metadata={metadata} actions={controls} onOverview={()=>setOverview(true)}>{capabilityList}</ServiceCard>
  <Drawer open={overview} onClose={()=>setOverview(false)} side="right" width="md" title="服务概要" description={group.scene.name} closeLabel="关闭服务概要"><div className="service-card-overview"><section><div>{status}</div><dl>{[['所属项目',group.scene.project_name||'未指定项目'],['发布版本',serviceVersionLabel(version)],['发布时间',version.release.created_at||'未记录'],['可见版本',String(group.versions.length)]].map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></section><section><h3>服务能力</h3>{capabilityList}</section><div className="service-card-overview-actions">{controls}</div></div></Drawer></>;
 return <ServiceDirectoryRow label={label}
  symbol={<ServiceIcon size={36} weight="duotone"/>}
  heading={<><div className="service-entry-title"><Link to={href}>{group.scene.name}</Link><StatusBadge size="sm" icon={false} tone={version.available?'success':'neutral'}>{serviceStateLabels[version.state]}</StatusBadge></div><span className="service-project">{group.scene.project_name||'未指定项目'}</span></>}
  capabilities={<><span className="service-entry-label">服务能力</span><div className="service-list-capabilities" aria-label="已授权能力">{capabilities.map(item=>{const CapabilityIcon=capabilityIcons[item.kind];return <span key={item.kind}><CapabilityIcon size={14}/>{serviceKinds[item.kind].label}</span>;})}</div></>}
  metadata={<><div className="service-release-primary"><span title={version.release.id}>Ver: {serviceVersionLabel(version)}</span></div><div className="service-release-secondary"><span>{version.release.created_at.slice(0,10)||'时间未记录'}</span><span>共 {group.versions.length} 个版本</span></div></>}
  action={controls}/>;
}
