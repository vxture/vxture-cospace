import React,{useEffect,useState} from 'react';
import {businessEndpoint} from './business-endpoint';
import {recordLink} from './record-navigation';
type Node={kind:string;title:string;status:string;id:string|null;detail:string;model_manifest_sha256?:string;ontology_ref?:{ontology_id:string;version:string;sha256:string}};
type Report={profile:string;space_id:string;publication_id:string;nodes:Node[];notice:string;package_generated:false;preflight_sequence:null};
export function PublicationProvenance({space,publication}:{space:string;publication:string}){
 const [state,setState]=useState<{key:string;report?:Report;error?:string}|null>(null),[revision,setRevision]=useState(0);
 const key=JSON.stringify([space,publication,revision]),current=state?.key===key?state:null;
 useEffect(()=>{
  const controller=new AbortController();setState(null);
  fetch(`${businessEndpoint}/publications/${encodeURIComponent(publication)}/api/provenance`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'当前身份无权读取此发布来源。':'发布来源暂不可读，不会切换到当前发布。');
   const report:Report=await r.json();
   if(report.profile!=='cospace.publication-provenance/0.1'||report.space_id!==space||report.publication_id!==publication||report.package_generated!==false||!Array.isArray(report.nodes))throw Error('来源响应与指定发布不一致。');
   if(!controller.signal.aborted)setState({key,report});
  }).catch(e=>{if(!controller.signal.aborted)setState({key,error:e.message});});
  return()=>controller.abort();
 },[key]);
 return <section aria-label="固定发布来源" className="flex min-w-0 flex-col gap-md border border-border rounded-md p-md"><h2>固定发布来源</h2><p className="break-all">{publication}</p><button onClick={()=>setRevision(v=>v+1)}>刷新来源</button>{current?.error?<p role="alert">{current.error}</p>:!current?.report?<p role="status">正在核对固定发布来源…</p>:<><ol className="flex flex-col gap-md">{current.report.nodes.map(node=><li key={node.kind} className="break-all border-b border-border pb-md"><h3>{node.title} · {node.status==='matched'?'绑定一致':node.status==='mismatch'?'绑定不一致':'未记录或不可读'}</h3><p>{node.id||'未记录'}</p><p>{node.detail}</p>{node.model_manifest_sha256&&<p>模型摘要：{node.model_manifest_sha256}</p>}{node.id&&node.status==='matched'&&<div className="flex flex-wrap gap-md">{node.kind==='input'&&<a href={recordLink('data',{space,tab:'inputs',input:node.id,from:publication})}>查看资料与预检历史</a>}{node.kind==='build'&&<a href={recordLink('build',{space,tab:'tasks',job:node.id,from:publication})}>查看来源任务</a>}{node.kind==='candidate'&&<a href={recordLink('data',{space,tab:'versions',artifact:'candidate:'+node.id,from:publication})}>查看来源候选</a>}{node.ontology_ref&&<a href={recordLink('ontology',{space,tab:'rules',ontology_id:node.ontology_ref.ontology_id,ontology_version:node.ontology_ref.version,ontology_sha256:node.ontology_ref.sha256})}>查看固定规则</a>}</div>}</li>)}</ol><p>{current.report.notice}</p><p>未核对下载、安装或消费端启用状态。</p></>}</section>;
}
