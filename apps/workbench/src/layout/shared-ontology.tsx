import React from 'react';
import {OntologyWorkbench} from './ontology-workbench';
import {recordLink,useRecordNavigation} from './record-navigation';
import {usePlatformSession} from './platform-auth';

export function SharedOntology(){
 const target=useRecordNavigation(),platform=usePlatformSession();
 const params=new URLSearchParams(location.search);
 const view=target.tab==='rules'||!target.tab&&params.has('ontology_id')?'rules':'authoring';
 const refs=Object.fromEntries(['ontology_id','ontology_version','ontology_sha256'].filter(k=>params.has(k)).map(k=>[k,params.get(k)!]));
 return <div className="shared-support-layout"><aside className="support-capabilities"><strong>语义本体</strong><nav aria-label="语义本体能力导航"><a href={recordLink('ontology',{...refs,tab:'authoring'})} aria-current={view==='authoring'?'page':undefined}>规则编制与封存</a><a href={recordLink('ontology',{...refs,tab:'rules'})} aria-current={view==='rules'?'page':undefined}>固定版本与校验</a></nav></aside><main className="shared-data-catalog" aria-label="共用语义本体"><header><div><p>共用支撑 · {platform?.user?.workspace_id||'工程预览'}</p><h1>语义本体</h1><p>共享模板与当前 Workspace 的规则可被多个场景引用。场景应用固定版本，升级不自动迁移实例。</p></div></header>{target.space&&<p className="shared-data-note">场景返回上下文：{target.space} · <a href={recordLink('association',{})}>返回场景关联</a></p>}<OntologyWorkbench key={platform?.user?.workspace_id||'engineering'}/></main></div>;
}
