import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Button,Drawer,Input,NativeSelect,Table,TableHeader,TableHead,TableRow,TableBody,TableCell} from '@vxture/design-system';
import {usePlatformSession} from './platform-auth';
import {sessionScopeKey} from './session-continuity';
import {businessEndpoint} from './business-endpoint';
import {displayText} from './display-text';
import {runGuarded} from './unsaved-navigation';
import {ScenePermissionsPanel} from './scene-permissions';
import {productRoleDefinitions} from './management-contract';
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
 const [saving,setSaving]=useState(false),[directoryInfo,setDirectoryInfo]=useState(false);
 const [query,setQuery]=useState(''),[filter,setFilter]=useState<Role|''>(role||''),[offset,setOffset]=useState(0),[refresh,setRefresh]=useState(0);
 const [data,setData]=useState<Directory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[selected,setSelected]=useState<Member|null>(null),[mode,setMode]=useState<'details'|'assign'>('details');
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
  <div className="management-card-heading"><h2>成员清单</h2><Button variant="ghost" size="sm" onClick={()=>setDirectoryInfo(true)}>名单说明</Button></div>
  <Drawer open={directoryInfo} onClose={()=>setDirectoryInfo(false)} side="right" width="md" title="成员名单说明" closeLabel="关闭名单说明"><p className="management-directory-notice">{data?.directory_complete?'名单来自平台当前工作区已获准使用 CoSpace 的成员，包含尚未访问本产品的成员。角色与场景范围由 CoSpace 分配；平台撤权后不会删除历史角色记录，产品访问仍由平台独立校验。':'当前仅展示本产品访问、协作申请及已授权记录中的成员，不代表完整平台名单。产品访问仍由平台校验。'}</p></Drawer>
  <div className="management-member-toolbar"><label>搜索成员<Input aria-label="搜索产品成员" placeholder="按成员名称搜索" value={query} onChange={e=>{const value=e.target.value;browse(()=>{setQuery(value);setOffset(0);});}}/></label>{!role&&<label>产品角色<NativeSelect aria-label="筛选产品角色" value={filter} onChange={e=>{const value=e.target.value as Role|'';browse(()=>{setFilter(value);setOffset(0);});}}><option value="">全部角色</option>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</NativeSelect></label>}<Button variant="outline" size="sm" disabled={loading} onClick={()=>browse(()=>setRefresh(value=>value+1))}>重新读取成员</Button></div>
  {error&&<p role="alert">{error}</p>}{loading&&<p role="status">正在读取成员…</p>}
  {data&&!data.can_manage&&<p>当前角色无权查看成员清单或分配角色。<Link to="/settings?section=scenes" className="text-primary underline">查看协作权限</Link></p>}
  {data?.can_manage&&<MemberTable {...{data,loading,offset}} onSelect={(member,mode)=>void runGuarded(()=>{setSelected(member);setMode(mode);})} onPage={value=>browse(()=>setOffset(value))}/>}
  <Drawer open={!!selected&&!!data?.can_manage} onClose={()=>{if(!saving)void runGuarded(()=>{setSelected(null);setRefresh(value=>value+1);});}} side="right" width="min(600px, 100vw)" title={mode==='details'?'成员详情':'分配成员角色'} description={selected?displayText(selected.display_name,'成员名称待补全'):undefined} closeLabel="关闭成员面板">
   {selected&&data?.can_manage&&(mode==='details'?<div className="management-drawer-content"><dl className="management-information"><div><dt>成员</dt><dd>{displayText(selected.display_name,'成员名称待补全')}</dd></div><div><dt>产品角色</dt><dd>{selected.roles.map(value=>value==='owner'?'所有者':labels[value]).join('、')||'默认查看者'}</dd></div><div><dt>已授权场景</dt><dd>{selected.scene_count} 个</dd></div><div><dt>最近访问</dt><dd>{selected.last_seen?new Date(selected.last_seen).toLocaleString('zh-CN'):'暂无记录'}</dd></div></dl><p>角色与授权场景数仅统计你可管理的范围。平台使用资格由平台维护。</p>{!selected.roles.includes('owner')&&<Button onClick={()=>setMode('assign')}>分配角色</Button>}</div>:<ScenePermissionsPanel initialSubject={selected.subject} initialRole={assignmentRole||role} editorOnly onBusyChange={setSaving} onSaved={()=>{setSelected(null);setRefresh(value=>value+1);}}/>)}
  </Drawer>
 </div>;
}
function MemberTable({data,loading,offset,onPage,onSelect}:{readonly data:Directory;readonly loading:boolean;readonly offset:number;readonly onPage:(value:number)=>void;readonly onSelect:(member:Member,mode:'details'|'assign')=>void}){
 const total=data.member_total||0;
 return <><p className="text-body-small text-muted-foreground">当前筛选共 {total} 位{data.directory_complete?'平台授权成员':'已记录成员'}。角色与场景数仅统计你可管理的场景范围。</p><div className="management-member-table"><Table><TableHeader><TableRow><TableHead>成员</TableHead><TableHead>产品角色</TableHead><TableHead>已授权场景</TableHead><TableHead data-table-actions>操作</TableHead></TableRow></TableHeader><TableBody>{data.members?.map(member=><TableRow key={member.subject}><TableCell><span>{displayText(member.display_name,'成员名称待补全')}</span>{member.last_seen&&<span className="management-member-meta">最近访问 {new Date(member.last_seen).toLocaleDateString('zh-CN')}</span>}{member.requested_at&&<span className="management-member-meta">已提交协作申请</span>}</TableCell><TableCell>{member.roles.map(value=>(value==='owner'?'所有者':labels[value])).join('、')||'默认查看者'}</TableCell><TableCell>{member.scene_count} 个</TableCell><TableCell data-table-actions><div className="management-row-actions"><Button variant="ghost" size="sm" onClick={()=>onSelect(member,'details')}>查看详情</Button>{!member.roles.includes('owner')&&<Button variant="ghost" size="sm" onClick={()=>onSelect(member,'assign')}>分配角色</Button>}</div></TableCell></TableRow>)}</TableBody></Table></div>{!data.members?.length&&<p>没有匹配的成员。</p>}<div className="permission-pages"><Button variant="ghost" size="sm" disabled={loading||offset===0} onClick={()=>onPage(Math.max(0,offset-25))}>上一页</Button><Button variant="ghost" size="sm" disabled={loading||offset+25>=total} onClick={()=>onPage(offset+25)}>下一页</Button></div></>;
}
export function RoleManagement(){
 const [selected,setSelected]=useState<string|null>(null);
 return <><div className="management-member-table"><Table><TableHeader><TableRow><TableHead>角色</TableHead><TableHead>授权范围</TableHead><TableHead data-table-actions>操作</TableHead></TableRow></TableHeader><TableBody>{productRoleDefinitions.map(item=><TableRow key={item.role}><TableCell>{item.role}</TableCell><TableCell>{item.scope}</TableCell><TableCell data-table-actions><Button variant="ghost" size="sm" onClick={()=>setSelected(item.role)}>查看详情</Button></TableCell></TableRow>)}</TableBody></Table></div><p className="text-body-small text-muted-foreground">固定角色的权限组合由产品定义；成员角色在成员管理中分配。</p><Drawer open={!!selected} onClose={()=>setSelected(null)} side="right" width="md" title="角色详情" description={selected||undefined} closeLabel="关闭角色详情">{selected&&<div className="management-drawer-content"><RoleDefinitions role={selected}/><Link to="/settings?section=members" className="text-primary underline">前往成员管理</Link></div>}</Drawer></>;
}
