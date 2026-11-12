import React from 'react';
import {Link} from 'react-router-dom';
import {Button,StatusBadge} from '@vxture/design-system';
import {ArrowRight} from '@phosphor-icons/react';
import {serviceKinds,sectionServices,type ServiceSpace,type ServiceVersion,type ServiceSection} from './spatial-service-contract';
import {servicePageHref,type ServiceListFilter} from './service-workspace-contract';

export const serviceStateLabels={active:'已发布',paused:'已暂停',retired:'已退役',unknown:'待核对'};
export const serviceVersionLabel=(version:ServiceVersion)=>version.release.display_code||version.release.version_code||version.release.id.slice(-8);
export function ServiceListEntry({group,version,section,filter}:{group:ServiceSpace;version:ServiceVersion;section:ServiceSection;filter:ServiceListFilter}){
 const href=servicePageHref(section,group.scene.id,version.release.id,undefined,filter);
 return <article className="service-list-row" aria-label={`${group.scene.name} · ${section==='online'?'在线服务':section==='offline'?'离线交付':'场景服务'}`}>
  <div className="service-list-identity"><Link to={href}>{group.scene.name}</Link><p>{group.scene.project_name||'未指定项目'}</p></div>
  <div className="service-list-capabilities" aria-label="已授权能力">{sectionServices(version,section).map(item=><span key={item.kind}>{serviceKinds[item.kind].label}</span>)}</div>
  <div className="service-list-version"><span title={version.release.id}>Ver: {serviceVersionLabel(version)}</span><small>{version.release.created_at.slice(0,10)||'时间未记录'}</small></div>
  <div><StatusBadge size="sm" icon={false} tone={version.available?'success':'neutral'}>{serviceStateLabels[version.state]}</StatusBadge></div>
  <Button asChild variant="ghost" size="sm"><Link to={href} aria-label={`查看${group.scene.name}服务`}>查看服务<ArrowRight size={14}/></Link></Button>
 </article>;
}
