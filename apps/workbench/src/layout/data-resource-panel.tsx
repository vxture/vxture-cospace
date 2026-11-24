import React,{useEffect,useRef,useState} from 'react';
import {Button,Drawer,Textarea} from '@vxture/design-system';
import {type ResourceItem} from './data-catalog-contract';
import {ProjectPicker} from './data-project-picker';
import {dataRequest} from './data-project-client';
import {useUnsavedNavigation} from './unsaved-navigation';
import {DataReferenceDetails} from './data-reference-details';

export function DataResourcePanel({item,edit,workspace,onClose,onChanged}:{item:ResourceItem;edit:boolean;workspace:string;onClose:()=>void;onChanged:()=>void}){
 const [owner,setOwner]=useState(item.owner_project_id||''),[base,setBase]=useState(item.is_base),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const gate=useRef(false),pending=useRef<{key:string;body:Record<string,unknown>}|null>(null),request=useRef<AbortController|null>(null);
 const dirty=owner!==(item.owner_project_id||'')||base!==item.is_base||!!reason;
 useUnsavedNavigation(dirty||busy,'资源登记');useEffect(()=>()=>request.current?.abort(),[]);
 async function save(){if(gate.current||!item.source_version)return;gate.current=true;setBusy(true);setError('');const fields={resource_id:item.resource_id,expected_revision:item.revision,expected_version:item.source_version.version_id,owner_project_id:owner,is_base:base,reason},key=JSON.stringify(fields),body=pending.current?.key===key?pending.current.body:{...fields,request_id:crypto.randomUUID().replaceAll('-','')};pending.current={key,body};const c=new AbortController();request.current=c;
  try{await dataRequest('/api/data-resources',c.signal,body);if(!c.signal.aborted)onChanged();}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'登记失败。');}finally{gate.current=false;if(!c.signal.aborted)setBusy(false);}}
 return <Drawer open title={edit?'资源登记':'数据详情'} side="right" width="lg" className="data-management-drawer" onClose={()=>{if(dirty||busy)setError('请先保存或放弃当前修改。');else onClose();}} footer={edit?<div className="data-drawer-footer"><Button variant="outline" disabled={busy} onClick={onClose}>放弃修改</Button><Button disabled={busy||!owner||!reason.trim()} onClick={()=>void save()}>{busy?'保存中…':'保存登记'}</Button></div>:undefined}>
 <div className="data-project-form"><h2>{item.label}</h2><p className="data-resource-secondary">{item.record_id}</p>{error&&<p role="alert">{error}</p>}<dl className="data-resource-details"><dt>来源场景</dt><dd>{item.space_name}</dd><dt>管理项目</dt><dd>{item.owner_project_name||'待登记'}</dd><dt>资源标识</dt><dd>{item.resource_id||'处理记录，无资源登记'}</dd><dt>已登记版本</dt><dd>{item.version_count}</dd>{item.source_version&&<><dt>来源格式</dt><dd>{item.source_version.format||'未记录'}</dd><dt>记录大小</dt><dd>{item.source_version.bytes==null?'未记录':`${item.source_version.bytes.toLocaleString()} B`}</dd><dt>形成时间</dt><dd>{item.source_version.created_at?new Date(item.source_version.created_at).toLocaleString('zh-CN'):'未记录'}</dd></>}</dl>
 {edit&&<><label>管理项目{item.registered?<p>{item.owner_project_name}</p>:<ProjectPicker workspace={workspace} value={owner} onChange={setOwner} disabled={busy}/>}</label><label className="data-resource-checkbox"><input type="checkbox" checked={base} disabled={busy} onChange={e=>setBase(e.target.checked)}/>标记为基础数据</label><label>登记原因<Textarea value={reason} maxLength={500} disabled={busy} onChange={e=>setReason(e.target.value)}/></label></>}
 {item.external&&item.uses?<DataReferenceDetails uses={item.uses} onChanged={onChanged}/>:<p className="data-resource-secondary">版本引用依据来源元数据。目录读取不重新校验原文件完整性；管理项目登记不授予跨项目使用权限。</p>}{item.href&&<Button asChild variant="outline" size="sm"><a href={item.href.replace(/^#/,'/')}>查看来源记录</a></Button>}
 </div></Drawer>;
}
