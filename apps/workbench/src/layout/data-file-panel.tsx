import React,{useEffect,useRef,useState} from 'react';
import {Button,Drawer,Input,NativeSelect,Textarea} from '@vxture/design-system';
import {ProjectPicker} from './data-project-picker';
import {businessEndpoint} from './business-endpoint';
import {dataResponse} from './data-project-client';
import {fileUploadQuery,referenceFileAccept,referenceFileError} from './data-file-contract';
import type {ResourceItem} from './data-catalog-contract';
import {fileAppendQuery} from './data-upgrade-contract';
import {useUnsavedNavigation} from './unsaved-navigation';

export function DataFilePanel({workspace,project,item,onClose,onChanged}:Readonly<{workspace:string;project:string;item?:ResourceItem;onClose:()=>void;onChanged:()=>void}>){
 const [ownerKind,setOwnerKind]=useState('project'),[owner,setOwner]=useState(project),[file,setFile]=useState<File|null>(null),[base,setBase]=useState(false),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const pending=useRef<{file:File;key:string;id:string}|null>(null),gate=useRef(false),request=useRef<AbortController|null>(null);
 const dirty=!!file||!!reason||base||ownerKind!=='project'||owner!==project;
 useUnsavedNavigation(dirty||busy,'上传资料');useEffect(()=>()=>request.current?.abort(),[]);
 async function upload(){
  if(gate.current||!file){return;}
  const invalid=referenceFileError(file);if(invalid){setError(invalid);return;}gate.current=true;setBusy(true);setError('');
  const fields={ownerKind,project:owner,name:file.name,base,reason},key=JSON.stringify(fields);
  if(pending.current?.file!==file||pending.current.key!==key){
   pending.current={file,key,id:crypto.randomUUID().replaceAll('-','')};
  }
  const c=new AbortController();request.current=c;
  try{const response=await fetch(businessEndpoint+(item?'/api/data-files/versions?':'/api/data-files?')+(item?fileAppendQuery(item,file.name,reason,pending.current.id):fileUploadQuery({...fields,requestId:pending.current.id})),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file,signal:c.signal,cache:'no-store'});await dataResponse(response);if(!c.signal.aborted)onChanged();}
  catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'上传失败，请重试。');}finally{gate.current=false;if(!c.signal.aborted)setBusy(false);}
 }
 const submitLabel=item?'保存新版本':'上传资料';
 return <Drawer open title={item?'追加版本':'上传资料'} side="right" width="lg" className="data-management-drawer" onClose={()=>{if(dirty||busy)setError('请先上传或放弃当前修改。');else onClose();}} footer={<div className="data-drawer-footer"><Button variant="outline" disabled={busy} onClick={onClose}>{dirty?'放弃上传':'取消'}</Button><Button disabled={busy||!file||!reason.trim()||!item&&ownerKind==='project'&&!owner} onClick={()=>void upload()}>{busy?'保存中…':submitLabel}</Button></div>}>
 <div className="data-project-form data-sharing-form">{error&&<p role="alert">{error}</p>}{item?<><h2>{item.label}</h2><p className="data-resource-secondary">新版本沿用当前管理归属。既有共享授权与项目引用保留原版本。</p></>:<><label>管理归属<NativeSelect value={ownerKind} disabled={busy} onChange={e=>setOwnerKind(e.target.value)}><option value="project">业务项目</option><option value="workspace">工作区共用</option></NativeSelect></label>{ownerKind==='project'&&<label>管理项目<ProjectPicker workspace={workspace} value={owner} onChange={setOwner} disabled={busy}/></label>}</>}
 <label>资料文件<Input type="file" accept={referenceFileAccept} disabled={busy} onChange={e=>{const selected=e.target.files?.[0]||null;setFile(selected);setError(selected?referenceFileError(selected):'');}}/></label>{file&&<p className="data-resource-secondary">{file.name} · {file.size<1024?`${file.size} B`:`${(file.size/1024).toLocaleString('zh-CN',{maximumFractionDigits:1})} KiB`}</p>}<p className="data-resource-secondary">支持 PDF、图片、CSV、TXT、IFC，单文件不超过 32 MiB。原件保存为固定版本，上传后可设置共享。</p>
 {!item&&<label className="data-resource-checkbox"><input type="checkbox" checked={base} disabled={busy} onChange={e=>setBase(e.target.checked)}/>标记为基础数据</label>}<label>上传说明<Textarea maxLength={500} disabled={busy} value={reason} onChange={e=>setReason(e.target.value)}/></label>
 {ownerKind==='workspace'&&<p className="data-resource-secondary">由当前工作区统一管理；项目需通过共享授权关联使用。</p>}</div></Drawer>;
}
