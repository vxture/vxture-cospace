import React, {useState} from 'react';
import {Button, StatusBadge, DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem} from '@vxture/design-system';
import {Cube, Code, DownloadSimple, ArrowSquareOut, DotsThreeVertical, Copy, Info} from '@phosphor-icons/react';
import {serviceKinds, serviceResourcePath, type SpatialService} from './spatial-service-contract';
import {realScreenHref} from './real-space-data';
import {businessEndpoint} from './business-endpoint';

const icons = {preview: Cube, query: Code, offline: DownloadSimple};
const states = {active: '可用', paused: '已暂停', retired: '已退役', unknown: '待核对'};

export function ServiceCard({item, onDetails}: {item: SpatialService; onDetails: () => void}) {
 const [failedImage, setFailedImage] = useState('');
 const [copyMessage, setCopyMessage] = useState('');
 const ServiceIcon = icons[item.kind];
 const overview = item.scene.overview_url;
 const label = serviceKinds[item.kind].label;
 const actionLabel = item.kind === 'preview' ? '打开预览' : item.kind === 'query' ? '查看接入' : '下载交付包';
 const actionHref = item.kind === 'preview' ? realScreenHref(item.scene.id, item.release.id) : businessEndpoint + serviceResourcePath(item);
 async function copyAddress() {
  try {
   await navigator.clipboard.writeText(businessEndpoint + serviceResourcePath(item));
   setCopyMessage('已复制服务地址');
  } catch {
   setCopyMessage('复制未完成，请在服务详情中复制');
  }
 }
 return <article className="spatial-service-card" aria-label={`${item.scene.name} · ${label}`}>
  <header className="spatial-service-heading">
   <span className="spatial-service-symbol"><ServiceIcon size={18}/></span>
   <div className="spatial-service-title"><h2 title={item.scene.name}><button onClick={onDetails}>{item.scene.name}</button></h2><p title={item.scene.project_name}>{item.scene.project_name || '未指定项目'}</p></div>
   <StatusBadge tone={item.available ? 'success' : 'neutral'}>{states[item.state]}</StatusBadge>
  </header>
  <button className="spatial-service-cover" onClick={onDetails} aria-label={`查看${item.scene.name}${label}详情`}>
   {overview && failedImage !== overview ? <img src={overview} alt={`${item.scene.name}场景概览`} loading="lazy" onError={() => setFailedImage(overview)}/> : <ServiceIcon size={56} weight="duotone" aria-hidden="true"/>}
   <span>{label}</span>
  </button>
  <div className="spatial-service-body"><p className="spatial-service-description">{item.scene.description || '此服务基于场景的固定发布版本提供。'}</p></div>
  <footer className="spatial-service-footer">
   <span className="spatial-service-version" title={item.release.id}>ver: {item.release.id.slice(-8)}</span>
   <div className="spatial-service-actions">
    <DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-xl" variant="secondary" aria-label={`${item.scene.name}${label}更多操作`}><DotsThreeVertical size={16}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="scene-action-menu">
     <DropdownMenuItem onSelect={onDetails}><Info size={16}/>服务详情</DropdownMenuItem>
     <DropdownMenuItem disabled={!item.available} onSelect={copyAddress}><Copy size={16}/>复制服务地址</DropdownMenuItem>
    </DropdownMenuContent></DropdownMenu>
    {!item.available ? <Button size="xl" disabled>{states[item.state]}</Button> : item.kind === 'query' ? <Button size="xl" onClick={onDetails}>{actionLabel}</Button> : <Button size="xl" asChild><a href={actionHref} target="_blank" rel="noopener noreferrer">{actionLabel}{item.kind === 'preview' ? <ArrowSquareOut size={14}/> : <DownloadSimple size={14}/>}</a></Button>}
   </div>
  </footer>
  <span role="status" className="sr-only">{copyMessage}</span>
 </article>;
}
