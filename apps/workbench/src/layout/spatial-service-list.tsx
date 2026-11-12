import React from 'react';
import {Link} from 'react-router-dom';
import {Button,StatusBadge} from '@vxture/design-system';
import {ArrowRight,Cube,Cloud,DownloadSimple,Eye,Code} from '@phosphor-icons/react';
import {serviceKinds,sectionServices,type ServiceSpace,type ServiceVersion,type ServiceSection} from './spatial-service-contract';
import {servicePageHref,type ServiceListFilter} from './service-workspace-contract';

export const serviceStateLabels={active:'已发布',paused:'已暂停',retired:'已退役',unknown:'待核对'};
export const serviceVersionLabel=(version:ServiceVersion)=>version.release.display_code||version.release.version_code||version.release.id.slice(-8);
export function ServiceListEntry({group,version,section,filter}:{group:ServiceSpace;version:ServiceVersion;section:ServiceSection;filter:ServiceListFilter}){
 const href=servicePageHref(section,group.scene.id,version.release.id,undefined,filter);
 const ServiceIcon=section==='online'?Cloud:section==='offline'?DownloadSimple:Cube;
 const capabilityIcons={preview:Eye,query:Code,offline:DownloadSimple};
 const capabilities=sectionServices(version,section);
 return <article className="service-list-row" aria-label={`${group.scene.name} · ${section==='online'?'在线服务':section==='offline'?'离线交付':'场景服务'}`}>
  <div className="service-entry-symbol" aria-hidden="true"><ServiceIcon size={36} weight="duotone"/></div>
  <div className="service-entry-heading"><div className="service-entry-title"><Link to={href}>{group.scene.name}</Link><StatusBadge size="sm" icon={false} tone={version.available?'success':'neutral'}>{serviceStateLabels[version.state]}</StatusBadge></div><span className="service-project">{group.scene.project_name||'未指定项目'}</span></div>
  <div className="service-entry-capability-group"><span className="service-entry-label">服务能力</span><div className="service-list-capabilities" aria-label="已授权能力">{capabilities.map(item=>{const CapabilityIcon=capabilityIcons[item.kind];return <span key={item.kind}><CapabilityIcon size={14}/>{serviceKinds[item.kind].label}</span>;})}</div></div>
  <div className="service-entry-release"><div className="service-release-primary"><span title={version.release.id}>Ver: {serviceVersionLabel(version)}</span></div><div className="service-release-secondary"><span>{version.release.created_at.slice(0,10)||'时间未记录'}</span><span>共 {group.versions.length} 个版本</span></div></div>
  <Button asChild variant="outline" size="xl"><Link to={href} aria-label={`查看${group.scene.name}服务`}>查看服务<ArrowRight size={16}/></Link></Button>
 </article>;
}
