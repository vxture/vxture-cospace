import React,{useRef,useState,useEffect} from 'react';
import {Button,StatusBadge,Textarea} from '@vxture/design-system';
import {DataUpgradePanel} from './data-upgrade-panel';
import {dataRequest} from './data-project-client';
import {businessEndpoint} from './business-endpoint';
import {sharingStatus,type ResourceUse} from './data-sharing-contract';
import {useOperationConfirmation} from './operation-confirmation';
import {useUnsavedNavigation} from './unsaved-navigation';

export function DataReferenceDetails({uses,workspace,onChanged}:{uses:ResourceUse[];workspace:string;onChanged:()=>void}){
 const [upgrading,setUpgrading]=useState(''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const gate=useRef(false),request=useRef<AbortController|null>(null),pending=useRef<{id:string;body:Record<string,unknown>}|null>(null);
 const confirm=useOperationConfirmation('data-reference:'+uses.map(u=>u.id+':'+u.revision).join(','));
 useUnsavedNavigation(!!reason||busy,'引用记录');useEffect(()=>()=>request.current?.abort(),[]);
 async function unlink(use:ResourceUse){if(gate.current)return;gate.current=true;setBusy(true);setError('');const c=new AbortController();request.current=c;
  const key=use.id+':'+use.revision+':'+reason,body=pending.current?.id===key?pending.current.body:{action:'unlink',use_id:use.id,expected_revision:use.revision,reason,request_id:crypto.randomUUID().replaceAll('-','')};pending.current={id:key,body};
  try{await dataRequest('/api/data-sharing',c.signal,body);if(!c.signal.aborted){setReason('');onChanged();}}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'解除失败。');}finally{gate.current=false;if(!c.signal.aborted)setBusy(false);}}
 return <section className="data-reference-details"><h3>固定版本引用</h3>{error&&<p role="alert">{error}</p>}{uses.map(use=><article key={use.id} className="data-sharing-reference"><div className="data-sharing-record"><strong>{use.project_name}{use.space_name?' · '+use.space_name:' · 项目级'}</strong><StatusBadge tone={use.access_status==='active'?'neutral':'warning'}>{sharingStatus[use.access_status]||'状态待核对'}</StatusBadge></div><dl className="data-resource-details"><dt>用途</dt><dd>{use.purpose}</dd><dt>固定版本</dt><dd>{use.version_id.slice(0,12)}</dd><dt>空间应用</dt><dd>参考关联，未应用坐标</dd></dl><div className="data-sharing-record">{use.allow_download&&<Button asChild variant="outline" size="sm"><a href={businessEndpoint+'/api/data-sharing/download?'+new URLSearchParams({grant_id:use.grant_id,project_id:use.project_id,grant_revision:String(use.grant_revision)})}>下载固定版本原件</a></Button>}{use.status==='active'&&<Button size="sm" variant="outline" disabled={busy||!!upgrading} onClick={()=>setUpgrading(use.id)}>比较与升级</Button>}{use.status==='active'&&<Button size="sm" variant="outline" disabled={busy||!!upgrading||!reason.trim()} onClick={()=>void confirm({verb:'解除引用',target:use.snapshot.label,consequence:'从当前项目清单解除此引用，保留历史审计及来源资料。'},()=>unlink(use))}>解除引用</Button>}</div>{upgrading===use.id&&<DataUpgradePanel use={use} workspace={workspace} onChanged={onChanged} onClose={()=>setUpgrading('')}/>}</article>)}<label>解除原因<Textarea value={reason} maxLength={200} disabled={busy} onChange={e=>setReason(e.target.value)}/></label></section>;
}
