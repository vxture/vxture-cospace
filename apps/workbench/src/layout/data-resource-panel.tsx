import React,{useEffect,useRef,useState} from 'react';
import {Button,Drawer,NativeSelect,Textarea} from '@vxture/design-system';
import {resourceOwnerLabel,resourceFileDownload,resourceScopeLabel,type ResourceItem} from './data-catalog-contract';
import {ProjectPicker} from './data-project-picker';
import {dataRequest} from './data-project-client';
import {runGuarded,useUnsavedNavigation} from './unsaved-navigation';
import {businessEndpoint} from './business-endpoint';
import {DataReferenceDetails} from './data-reference-details';
import {DataLineagePanel} from './data-lineage-panel';
import {DataProcessingPanel,DataGovernancePanel} from './data-processing-panel';
import {ArtifactControl} from './artifact-control';

function ResourceTrace({workspace,item}:Readonly<{workspace:string;item:ResourceItem}>){
 const projects=[...new Map(item.uses?.map(u=>[u.project_id,u.project_name])).entries()];
 const [selected,setSelected]=useState(projects[0]?.[0]||'');
 if(item.external&&!selected)return null;
 return <>{item.external&&projects.length>1&&<label>追溯项目<NativeSelect value={selected} onChange={e=>setSelected(e.target.value)}>{projects.map(([id,name])=><option key={id} value={id}>{name}</option>)}</NativeSelect></label>}<DataLineagePanel key={selected} workspace={workspace} resource={item.resource_id!} project={item.external?selected:undefined}/></>;
}

export function DataResourcePanel({item,edit,workspace,onClose,onChanged}:{item:ResourceItem;edit:boolean;workspace:string;onClose:()=>void;onChanged:()=>void}){
 const [owner,setOwner]=useState(item.owner_project_id||''),[base,setBase]=useState(item.is_base),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const gate=useRef(false),pending=useRef<{key:string;body:Record<string,unknown>}|null>(null),request=useRef<AbortController|null>(null);
 const [control,setControl]=useState(false);
 const artifact=item.kind==='input'?'input:'+item.record_id:'candidate:'+item.record_id;
 const referenceNote=item.kind==='resource_file'?'原件按固定版本保存，下载时核验完整性。管理归属与共享授权分别设置。':'版本引用依据来源元数据。目录读取不重新校验原文件完整性；管理项目登记不授予跨项目使用权限。';
 const dirty=owner!==(item.owner_project_id||'')||base!==item.is_base||!!reason;
 useUnsavedNavigation(dirty||busy,'资源登记');useEffect(()=>()=>request.current?.abort(),[]);
 async function save(){
  if(gate.current||!item.source_version){return;}
  gate.current=true;setBusy(true);setError('');const fields={resource_id:item.resource_id,expected_revision:item.revision,expected_version:item.source_version.version_id,owner_kind:item.owner_kind==='workspace'?'workspace':'project',owner_project_id:owner||null,is_base:base,reason},key=JSON.stringify(fields),body=pending.current?.key===key?pending.current.body:{...fields,request_id:crypto.randomUUID().replaceAll('-','')};pending.current={key,body};const c=new AbortController();request.current=c;
  try{await dataRequest('/api/data-resources',c.signal,body);if(!c.signal.aborted)onChanged();}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'登记失败。');}finally{gate.current=false;if(!c.signal.aborted)setBusy(false);}}
 return <Drawer open title={edit?'资源登记':'数据详情'} side="right" width="lg" className="data-management-drawer" onClose={()=>{if(dirty||busy)setError('请先保存或放弃当前修改。');else void runGuarded(onClose);}} footer={edit?<div className="data-drawer-footer"><Button variant="outline" disabled={busy} onClick={onClose}>放弃修改</Button><Button disabled={busy||item.owner_kind!=='workspace'&&!owner||!reason.trim()} onClick={()=>void save()}>{busy?'保存中…':'保存登记'}</Button></div>:undefined}>
 <div className="data-project-form"><h2>{item.label}</h2><p className="data-resource-secondary">{item.record_id}</p>{error&&<p role="alert">{error}</p>}<dl className="data-resource-details"><dt>{item.space_name?'来源场景':'资料层级'}</dt><dd>{resourceScopeLabel(item)}</dd><dt>管理归属</dt><dd>{resourceOwnerLabel(item)}</dd><dt>资源标识</dt><dd>{item.resource_id||'处理记录，无资源登记'}</dd><dt>已登记版本</dt><dd>{item.version_count}</dd>{item.source_version&&<><dt>来源格式</dt><dd>{item.source_version.format||'未记录'}</dd><dt>记录大小</dt><dd>{item.source_version.bytes==null?'未记录':`${item.source_version.bytes.toLocaleString()} B`}</dd><dt>形成时间</dt><dd>{item.source_version.created_at?new Date(item.source_version.created_at).toLocaleString('zh-CN'):'未记录'}</dd></>}</dl>
 {edit&&<><label>管理归属{item.registered?<p>{resourceOwnerLabel(item)}</p>:<ProjectPicker workspace={workspace} value={owner} onChange={setOwner} disabled={busy}/>}</label><label className="data-resource-checkbox"><input type="checkbox" checked={base} disabled={busy} onChange={e=>setBase(e.target.checked)}/>标记为基础数据</label><label>登记原因<Textarea value={reason} maxLength={500} disabled={busy} onChange={e=>setReason(e.target.value)}/></label></>}
 {item.kind==='resource_file'&&!item.external&&<Button asChild variant="outline" size="sm"><a href={businessEndpoint+resourceFileDownload(item)}>下载原件</a></Button>}{item.external&&item.uses?<DataReferenceDetails workspace={workspace} uses={item.uses} onChanged={onChanged}/>:<p className="data-resource-secondary">{referenceNote}</p>}{item.href&&<Button asChild variant="outline" size="sm"><a href={item.href.replace(/^#/,'/')}>查看来源记录</a></Button>}
 {!edit&&item.registered&&item.resource_id&&(item.can_manage||item.external)&&<ResourceTrace key={item.resource_id} workspace={workspace} item={item}/>}
 {!edit&&item.registered&&item.resource_id&&item.can_manage&&!item.external&&<><DataProcessingPanel workspace={workspace} resource={item.resource_id}/>{item.kind==='resource_file'?<DataGovernancePanel workspace={workspace} resource={item.resource_id} label={item.label} onChanged={onChanged}/>:item.space_id&&['input','candidate','human_view','agent_view'].includes(item.kind)&&<section className="data-lineage-panel"><div className="data-lineage-heading"><h3>成果使用状态</h3><Button size="sm" variant="outline" onClick={()=>setControl(v=>!v)}>{control?'收起':'管理使用状态'}</Button></div>{control&&<ArtifactControl space={item.space_id} artifact={artifact} onClose={()=>setControl(false)} onCommitted={onChanged}/>}</section>}</>}
 </div></Drawer>;
}
