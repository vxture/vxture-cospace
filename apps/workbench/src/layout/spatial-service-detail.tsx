import React,{useState} from 'react';
import {Button} from '@vxture/design-system';
import {DownloadSimple,Copy} from '@phosphor-icons/react';
import {serviceResourcePath,type SpatialService} from './spatial-service-contract';
import {businessEndpoint} from './business-endpoint';
import {PreviewConsumerGuide} from './preview-consumer-guide';
import {PreviewRangeQuery} from './preview-range-query';
import {OnlineServiceGuide} from './online-service-guide';

// Metadata is shared by all capabilities in the scene page header.
export function ServiceAccess({item}:{item:SpatialService}){
 const [copyState,setCopyState]=useState('');
 const url=businessEndpoint+serviceResourcePath(item);
 if(!item.available)return <p className="spatial-service-section-note" role="status">此版本已暂停、退役或状态待核对，接入操作已停用。请明确选择可用版本。</p>;
 async function copy(){try{await navigator.clipboard.writeText(url);setCopyState('已复制服务地址');}catch{setCopyState('复制未完成，请选择地址手动复制');}}
 return <section className="service-access" aria-label={item.kind==='query'?'在线接入':'离线成果'}>
  <div className="service-section-heading"><h2>{item.kind==='query'?'服务接入':'离线成果'}</h2>{item.kind==='offline'&&<Button size="sm" asChild><a href={url} target="_blank" rel="noopener noreferrer">下载交付包<DownloadSimple size={16}/></a></Button>}</div>
  <p className="spatial-service-section-note">{item.kind==='query'?'以下地址供当前登录会话使用；跨系统接入请展开服务身份接入说明。':'下载当前固定版本的交付包，在使用端完成安装和激活。'}</p>
  <div className="flex items-start gap-sm"><code className="spatial-service-address">{url}</code><Button size="icon-xl" variant="secondary" aria-label="复制服务地址" onClick={copy}><Copy size={16}/></Button></div>{copyState&&<p role="status" className="spatial-service-section-note">{copyState}</p>}
  {item.kind==='query'&&<><details className="service-inline-details"><summary>服务身份接入说明</summary><OnlineServiceGuide item={item}/></details>{item.scene.capabilities?.includes('space.preview')&&<details className="service-inline-details"><summary>在当前会话中试用范围查询</summary><PreviewRangeQuery key={item.id} publication={item.release.id}/></details>}</>}
  {item.kind==='offline'&&<details className="service-inline-details"><summary>安装、版本校验与恢复说明</summary><PreviewConsumerGuide key={item.id} publication={item.release.id} space={item.scene.id}/></details>}
 </section>;
}
