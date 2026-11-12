import React,{useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,StatusBadge,Table,TableHeader,TableHead,TableRow,TableBody,TableCell} from '@vxture/design-system';
import {Buildings,Users,UserCircle,ShieldCheck,ArrowClockwise,ArrowSquareOut,FileText} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {useSceneDirectory} from './use-scene-directory';
import {managementPage,sceneInformationHref,capabilityNames} from './management-contract';
import {accountVerification} from './account-profile';

function Information({items}:{readonly items:readonly (readonly [string,string|undefined])[]}){
 return <dl className="management-information">{items.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||'未提供'}</dd></div>)}</dl>;
}
function WorkspaceAccess(){
 const session=usePlatformSession(),[revision,setRevision]=useState(0);
 const {spaces,loading,error}=useSceneDirectory(revision);
 return <>
  <section className="management-card"><h2><Buildings size={20}/>当前工作区</h2>{session?<Information items={[
   ['组织',session.user?.org_name||session.user?.org_id],['工作区',session.user?.workspace_name||session.user?.workspace_id],['当前用户',session.user?.display_name],
  ]}/>:<p className="text-body-small text-muted-foreground">当前为设计预览，未连接平台身份与授权。</p>}</section>
  <section className="management-card"><div className="management-card-heading"><h2><Users size={20}/>当前用户的场景权限</h2><Button variant="ghost" size="sm" disabled={loading} onClick={()=>setRevision(v=>v+1)}><ArrowClockwise size={16}/>刷新权限</Button></div>
   {loading&&<output>正在读取场景权限…</output>}
   {error&&<p role="alert" className="text-destructive">{error}</p>}
   {!loading&&!error&&<>{!session&&<p className="text-body-small text-muted-foreground">以下为演示目录，不代表真实账户授权。</p>}
   <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>场景</TableHead><TableHead>可用权限</TableHead><TableHead className="text-center">操作</TableHead></TableRow></TableHeader><TableBody>{spaces.map(scene=><TableRow key={scene.id}><TableCell><span>{scene.name}</span><span className="management-scene-code">{scene.scene_code||scene.id}</span></TableCell><TableCell><div className="management-capabilities">{(scene.capabilities||[]).map(capability=><StatusBadge key={capability} tone="neutral">{capabilityNames[capability]||capability}</StatusBadge>)}{!scene.capabilities?.length&&<span className="text-muted-foreground">未提供权限信息</span>}</div></TableCell><TableCell className="text-center"><Button asChild variant="ghost" size="sm"><Link to={sceneInformationHref(scene.id)}><FileText size={16}/>基本信息</Link></Button></TableCell></TableRow>)}</TableBody></Table></div>
   {!spaces.length&&<p className="text-body-small text-muted-foreground">当前没有可访问的场景。</p>}</>}
  </section>
 </>;
}
function AccountSession({onLogout}:{readonly onLogout:()=>void|Promise<void>}){
 const session=usePlatformSession(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const user=session?.user,verification=accountVerification(user);
 let authority='平台会话已保存';
 if(session?.authority_state==='confirmed')authority='平台已确认';
 else if(session?.authority_state==='unavailable')authority='平台暂不可达';
 return <>
  <section className="management-card"><div className="management-card-heading"><h2><UserCircle size={20}/>当前账户</h2>{verification&&<StatusBadge tone="neutral">{verification.label}</StatusBadge>}</div>{session?<Information items={[
   ['姓名',user?.display_name],['用户名',user?.username],['邮箱',user?.email],['手机',user?.phone],['账户标识',user?.subject],
  ]}/>:<p className="text-body-small text-muted-foreground">当前为设计预览，未连接真实账户。</p>}<div className="management-card-actions"><Button asChild variant="secondary" size="sm"><a href="https://accounts.vxture.com" target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={16}/>账号中心</a></Button></div></section>
  <section className="management-card"><h2><ShieldCheck size={20}/>登录状态</h2><Information items={[
   ['当前状态',session?authority:'设计预览'],['组织',user?.org_name||user?.org_id],['工作区',user?.workspace_name||user?.workspace_id],
  ]}/>{error&&<p role="alert" className="text-destructive">{error}</p>}<div className="management-card-actions"><Button variant="ghost" size="sm" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await onLogout();}catch{setError('退出暂未完成，请稍后重试。');}finally{setBusy(false);}}}>{session?'退出登录':'退出预览'}</Button></div></section>
 </>;
}
export function ManagementWorkspace({route,onLogout}:{readonly route:string;readonly onLogout:()=>void|Promise<void>}){
 if(managementPage(route)==='account')return <AccountSession onLogout={onLogout}/>;
 return <WorkspaceAccess/>;
}
