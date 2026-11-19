import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,Input,NativeSelect,Table,TableHeader,TableHead,TableRow,TableBody,TableCell} from '@vxture/design-system';
import {usePlatformSession} from './platform-auth';
import {sessionScopeKey} from './session-continuity';
import {businessEndpoint} from './business-endpoint';
import {displayText} from './display-text';
import {runGuarded} from './unsaved-navigation';
import {ScenePermissionsPanel} from './scene-permissions';
import {RoleDefinitions} from './management-overview';

type Role='viewer'|'engineer'|'manager';
type Member={subject:string;display_name:string;requested_at:string|null;last_seen?:string;roles:(Role|'owner')[];scene_count:number};
type Directory={workspace_id:string;can_manage:boolean;members?:Member[];member_total?:number;role_counts?:Partial<Record<Role,number>>;directory_complete?:boolean};
const labels:Record<Role,string>={viewer:'查看者',engineer:'工程师',manager:'管理者'};
export function MemberManagement({role,assignmentRole}:{readonly role?:Role;readonly assignmentRole?:Role}){
 const session=usePlatformSession();
 if(!session)return <p>登录后可查看成员管理。</p>;
 return <MemberDirectory key={sessionScopeKey(session)+(role||'all')} role={role} assignmentRole={assignmentRole}/>;
}
function MemberDirectory({role,assignmentRole}:{readonly role?:Role;readonly assignmentRole?:Role}){
 const session=usePlatformSession();
 const [query,setQuery]=useState(''),[filter,setFilter]=useState<Role|''>(role||''),[offset,setOffset]=useState(0),[refresh,setRefresh]=useState(0);
 const [data,setData]=useState<Directory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[selected,setSelected]=useState<Member|null>(null);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');setData(null);
  const params=new URLSearchParams({members_q:query,member_offset:String(offset),role:filter});
  fetch(businessEndpoint+'/api/scene-permissions?'+params,{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error('成员信息暂不可读，请重新读取。');
   const value:Directory=await response.json();
   if(value.workspace_id!==session?.user?.workspace_id||typeof value.can_manage!=='boolean')throw Error('成员范围无法确认，请重新读取。');
   if(!controller.signal.aborted)setData(value);
  }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'成员信息暂不可读。');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[query,filter,offset,refresh,session?.user?.workspace_id]);
 function browse(action:()=>void){void runGuarded(()=>{setSelected(null);action();});}
 return <div className="member-management">
  <p className="management-directory-notice">平台完整授权成员清单尚未接入。以下仅为本产品访问、协作申请及已授权记录中的成员，不代表当前完整平台名单或实时平台授权状态。产品访问仍由平台校验。</p>
  <div className="management-member-toolbar"><label>搜索成员<Input aria-label="搜索产品成员" placeholder="按成员名称搜索" value={query} onChange={e=>{const value=e.target.value;browse(()=>{setQuery(value);setOffset(0);});}}/></label>{!role&&<label>产品角色<NativeSelect aria-label="筛选产品角色" value={filter} onChange={e=>{const value=e.target.value as Role|'';browse(()=>{setFilter(value);setOffset(0);});}}><option value="">全部角色</option>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</NativeSelect></label>}<Button variant="outline" size="sm" disabled={loading} onClick={()=>browse(()=>setRefresh(value=>value+1))}>重新读取成员</Button></div>
  {error&&<p role="alert">{error}</p>}{loading&&<p role="status">正在读取成员…</p>}
  {data&&!data.can_manage&&<p>当前角色无权查看成员清单或分配角色。<Link to="/settings?section=permissions" className="text-primary underline">查看协作权限</Link></p>}
  {data?.can_manage&&<MemberTable {...{data,loading,offset}} onSelect={member=>void runGuarded(()=>setSelected(member))} onPage={value=>browse(()=>setOffset(value))}/>}
  {selected&&<section className="management-card" aria-label="成员角色分配"><div className="management-card-heading"><h2>{displayText(selected.display_name,'成员名称待补全')} · 分配角色</h2><Button variant="ghost" size="sm" onClick={()=>void runGuarded(()=>{setSelected(null);setRefresh(value=>value+1);})}>关闭并刷新清单</Button></div><p>选择你可管理的场景后分配角色。此操作不授予平台使用资格，也不转移工作区所有权。</p><ScenePermissionsPanel initialSubject={selected.subject} initialRole={assignmentRole||role}/></section>}
 </div>;
}
function MemberTable({data,loading,offset,onPage,onSelect}:{readonly data:Directory;readonly loading:boolean;readonly offset:number;readonly onPage:(value:number)=>void;readonly onSelect:(member:Member)=>void}){
 const total=data.member_total||0;
 return <><p className="text-body-small text-muted-foreground">当前筛选共 {total} 位已记录成员。角色与场景数仅统计你可管理的场景范围。</p><div className="management-member-table"><Table><TableHeader><TableRow><TableHead>成员</TableHead><TableHead>产品角色</TableHead><TableHead>已授权场景</TableHead><TableHead data-table-actions>操作</TableHead></TableRow></TableHeader><TableBody>{data.members?.map(member=><TableRow key={member.subject}><TableCell><span>{displayText(member.display_name,'成员名称待补全')}</span>{member.last_seen&&<span className="management-member-meta">最近访问 {new Date(member.last_seen).toLocaleDateString('zh-CN')}</span>}{member.requested_at&&<span className="management-member-meta">已提交协作申请</span>}</TableCell><TableCell>{member.roles.map(value=>(value==='owner'?'所有者':labels[value])).join('、')||'无单独角色'}</TableCell><TableCell>{member.scene_count} 个</TableCell><TableCell data-table-actions>{member.roles.includes('owner')?<span>平台所有者</span>:<Button variant="ghost" size="sm" onClick={()=>onSelect(member)}>分配角色</Button>}</TableCell></TableRow>)}</TableBody></Table></div>{!data.members?.length&&<p>没有匹配的已记录成员。</p>}<div className="permission-pages"><Button variant="ghost" size="sm" disabled={loading||offset===0} onClick={()=>onPage(Math.max(0,offset-25))}>上一页</Button><Button variant="ghost" size="sm" disabled={loading||offset+25>=total} onClick={()=>onPage(offset+25)}>下一页</Button></div></>;
}
export function RoleManagement(){
 const [role,setRole]=useState<Role|'owner'>('engineer'),[assign,setAssign]=useState(false);
 return <><section className="management-card"><h2>产品角色</h2><div className="management-role-tabs" role="group" aria-label="选择管理角色">{(['owner','manager','engineer','viewer'] as const).map(value=><Button key={value} variant={role===value?'secondary':'ghost'} aria-pressed={role===value} onClick={()=>void runGuarded(()=>{setRole(value);setAssign(false);})}>{value==='owner'?'所有者':labels[value]}</Button>)}</div></section><RoleDefinitions role={role==='owner'?'所有者':labels[role]}/><section className="management-card"><h2>角色成员与分配</h2>{role==='owner'?<p>所有者由平台工作区身份确定，不能在 CoSpace 分配或转移。平台完整成员清单尚未接入，无法在此列出所有者。</p>:<><Button variant="outline" size="sm" onClick={()=>void runGuarded(()=>setAssign(value=>!value))}>{assign?'查看关联成员':'为成员分配此角色'}</Button><p className="text-body-small text-muted-foreground">{assign?`选择成员，为其分配${labels[role]}的场景权限。`:`以下为你可管理场景范围内的${labels[role]}。`}</p><MemberManagement key={String(assign)+role} role={assign?undefined:role} assignmentRole={role}/></>}</section></>;
}
