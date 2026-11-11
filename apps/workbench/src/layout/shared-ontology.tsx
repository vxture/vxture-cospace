import {Button} from '@vxture/design-system';
import {WorkspaceNavigation,WorkspaceHeading} from './workspace-frame';
import {Graph,PencilRuler,ShieldCheck,LinkSimple} from '@phosphor-icons/react';
import React from 'react';
import {OntologyWorkbench} from './ontology-workbench';
import {recordLink,useRecordNavigation} from './record-navigation';
import {usePlatformSession} from './platform-auth';

export function SharedOntology(){
 const target=useRecordNavigation(),platform=usePlatformSession();
 const params=new URLSearchParams(location.search);
 const view=target.tab==='rules'||!target.tab&&params.has('ontology_id')?'rules':'authoring';
 const refs=Object.fromEntries(['ontology_id','ontology_version','ontology_sha256'].filter(k=>params.has(k)).map(k=>[k,params.get(k)!]));
 return <div className="shared-support-layout"><WorkspaceNavigation title="语义本体" icon={Graph}><nav aria-label="语义本体能力导航"><a href={recordLink('ontology',{...refs,tab:'authoring'})} aria-current={view==='authoring'?'page':undefined}><PencilRuler size={18}/>规则编制与封存</a><a href={recordLink('ontology',{...refs,tab:'rules'})} aria-current={view==='rules'?'page':undefined}><ShieldCheck size={18}/>固定版本与校验</a></nav></WorkspaceNavigation><main className="shared-data-catalog" aria-label="共用语义本体"><WorkspaceHeading icon={Graph} title="语义本体" description="管理共用类型、属性与关系规则；场景引用固定版本，升级不自动迁移实例。" actions={target.space&&<Button asChild variant="secondary" size="sm"><a href={recordLink('association',{})}><LinkSimple size={16}/>空间关联</a></Button>}/><OntologyWorkbench key={platform?.user?.workspace_id||'engineering'}/></main></div>;
}
