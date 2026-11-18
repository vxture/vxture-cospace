import React,{useEffect,useState} from 'react';
import {Button,Input,NativeSelect} from '@vxture/design-system';
import {usePlatformSession} from './platform-auth';
import {sessionScopeKey} from './session-continuity';
import {businessEndpoint} from './business-endpoint';
import {runGuarded,useUnsavedNavigation} from './unsaved-navigation';
import './scene-permissions.css';

type Role='viewer'|'engineer'|'manager';
type Grant={subject:string;space_id:string;role:Role};
type Member={subject:string;display_name:string;requested_at:string|null};
type Access={workspace_id:string;can_manage:boolean;revision:number;requested:boolean;default_role:'viewer'|null;members?:Member[];scenes?:{id:string;name:string}[];grants?:Grant[];history?:{revision:number;subject:string;space_id:string;role:Role|null;previous_role:Role|null;actor:string;reason:string;changed_at:string}[]};
const roleLabels:Record<Role|string,string>={viewer:'查看者',engineer:'工程师',manager:'管理者',none:'无权限'};
const endpoint=businessEndpoint+'/api/scene-permissions';

export function ScenePermissionsPanel(){
 const session=usePlatformSession();
 if(!session)return <p>登录后可查看工作区场景权限。</p>;
 return <ScenePermissions key={sessionScopeKey(session)}/>;
}

function ScenePermissions(){
 const session=usePlatformSession();
 const [data,setData]=useState<Access|null>(null),[refresh,setRefresh]=useState(0),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [subject,setSubject]=useState(''),[space,setSpace]=useState(''),[role,setRole]=useState<Role|'none'>('viewer'),[reason,setReason]=useState('');
 const labels:Record<string,string>={...roleLabels,none:data?.default_role==='viewer'?'默认查看者':'无权限'};
 const current=data?.grants?.find(g=>g.subject===subject&&g.space_id===space)?.role||'none';
 const dirty=!!reason||!!subject&&!!space&&current!==role;
 const acknowledge=useUnsavedNavigation(dirty,'场景权限调整',{discard:()=>{setSubject('');setSpace('');setReason('');}});
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');
  fetch(endpoint,{cache:'no-store',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error('暂时无法读取场景权限，请重试。');
   const value:Access=await response.json();
   if(value.workspace_id!==session?.user?.workspace_id||!Number.isSafeInteger(value.revision)||typeof value.can_manage!=='boolean')throw Error('权限信息无法确认，请重试。');
   if(!controller.signal.aborted){setData(value);setSubject('');setSpace('');setReason('');}
  }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'读取失败，请重试。');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[refresh,session?.user?.workspace_id]);
 async function submit(event?:React.FormEvent){event?.preventDefault();if(busy||loading||!data)return;setBusy(true);setError('');setNotice('');
  try{
   await savePermission(data,{subject,space,role,reason});
   acknowledge();setReason('');setSubject('');setSpace('');setNotice(data.can_manage?'场景权限已保存。成员刷新“我的场景”后即可看到授权结果。':'协作申请已提交，请联系工作区所有者或管理者分配角色。');setRefresh(n=>n+1);
  }catch(e){setError(e instanceof Error?e.message:'提交失败，请重试。');}finally{setBusy(false);}
 }
 function choose(nextSubject:string,nextSpace:string){
  void runGuarded(()=>{setSubject(nextSubject);setSpace(nextSpace);setReason('');setRole(data?.grants?.find(g=>g.subject===nextSubject&&g.space_id===nextSpace)?.role||(data?.default_role==='viewer'?'engineer':'viewer'));});
 }
 return <div className="scene-permissions-content" aria-busy={busy||loading}>
  <p>{data?.default_role==='viewer'?'工作区成员默认可查看、预览和查询全部场景。':''}查看者可预览和查询；工程师可新建、编辑、管理和发布场景，拥有全部场景操作权限；管理者增加系统高级配置和人员角色管理权限。场景成员授权由工作区所有者或对应场景管理者维护，所有者保留本工作区全部场景的管理权限。</p>
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  <Button size="sm" variant="outline" disabled={busy||loading} onClick={()=>void runGuarded(()=>setRefresh(n=>n+1))}>重新读取权限</Button>
  {loading?<p role="status">正在读取权限…</p>:data?.can_manage?<>
   <PermissionEditor {...{data,busy,error,subject,space,role,reason,current,labels,choose,setRole,setReason,submit}}/>
   <PermissionGrants {...{data,busy,labels,choose}}/>
   <PermissionHistory {...{data,labels}}/>
  </>:data?<section aria-label="申请协作权限"><h3>申请协作权限</h3><p>你可以查看本工作区全部场景。如需管理资料、构建或发布，请申请协作权限，由工作区所有者或管理者分配角色。</p><Button disabled={busy||data.requested} onClick={()=>void submit()}>{data.requested?'已申请协作权限':busy?'正在提交…':'申请协作权限'}</Button>{data.requested&&<p>请联系工作区所有者或管理者处理；授权后刷新页面以使用对应功能。</p>}</section>:null}
 </div>;
}

type EditorProps={data:Access;busy:boolean;error:string;subject:string;space:string;role:Role|'none';reason:string;current:string;labels:Record<string,string>;choose:(subject:string,space:string)=>void;setRole:(role:Role|'none')=>void;setReason:(reason:string)=>void;submit:(event?:React.FormEvent)=>Promise<void>};

function PermissionEditor({data,busy,error,subject,space,role,reason,current,labels,choose,setRole,setReason,submit}:EditorProps){
 const members=data.members??[],scenes=data.scenes??[];
 return <section aria-label="成员场景授权"><h3>分配场景权限</h3><p>需要编辑或管理场景的成员，可在“配置与管理 → 工作区与授权 → 场景权限”中申请协作权限，随后在此分配角色。成员无需申请即可查看本工作区场景。</p>
    {!members.length?<p>暂无申请或已授权成员。</p>:!scenes.length?<p>当前工作区暂无可分配的场景，请先创建场景。</p>:<form onSubmit={submit} className="scene-permissions-form">
     <label>成员<NativeSelect aria-label="授权成员" value={subject} disabled={busy} onChange={e=>choose(e.target.value,space)}><option value="">选择成员</option>{members.map(m=><option key={m.subject} value={m.subject}>{m.display_name} · {m.subject}</option>)}</NativeSelect></label>
     <label>场景<NativeSelect aria-label="授权场景" value={space} disabled={busy} onChange={e=>choose(subject,e.target.value)}><option value="">选择场景</option>{scenes.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect></label>
     <label>角色<NativeSelect aria-label="场景角色" value={role} disabled={busy||!subject||!space} onChange={e=>setRole(e.target.value as Role|'none')}>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</NativeSelect></label>
     {subject&&space&&<p>当前角色：{labels[current]}。{data.default_role==='viewer'?'选择“默认查看者”会撤销额外操作权限，仍保留场景查看。':'选择“无权限”会撤销场景授权。'}</p>}
     <label>调整原因<Input aria-label="权限调整原因" maxLength={500} required value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
     <Button type="submit" disabled={busy||!!error||!subject||!space||!reason.trim()||role===current}>{busy?'正在保存…':'保存场景权限'}</Button>
    </form>}
   </section>;
}

function PermissionGrants({data,busy,labels,choose}:Pick<EditorProps,'data'|'busy'|'labels'|'choose'>){
 return <section aria-label="已授权成员"><h3>已授权成员</h3>{!data.grants?.length?<p>暂无单独授权；成员默认可查看场景，工作区所有者可管理全部场景。</p>:<ul>{data.grants.map(g=><li key={g.subject+g.space_id}><span>{data.members?.find(m=>m.subject===g.subject)?.display_name||g.subject} · {data.scenes?.find(s=>s.id===g.space_id)?.name||g.space_id} · {labels[g.role]}</span><Button size="sm" variant="ghost" disabled={busy} onClick={()=>choose(g.subject,g.space_id)}>调整</Button></li>)}</ul>}</section>;
}

function PermissionHistory({data,labels}:Pick<EditorProps,'data'|'labels'>){
 return <section aria-label="权限操作记录"><h3>最近操作</h3>{!data.history?.length?<p>暂无权限调整记录。</p>:<ul>{data.history.map(h=><li key={h.revision}><span>{data.members?.find(m=>m.subject===h.subject)?.display_name||h.subject} · {data.scenes?.find(s=>s.id===h.space_id)?.name||h.space_id}：{labels[h.previous_role||'none']} → {labels[h.role||'none']}<br/>{h.reason}<br/><small>操作人 {h.actor} · {new Date(h.changed_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}</small></span></li>)}</ul>}</section>;
}

function permissionFailure(status:number){
 if(status===409)return '权限已被其他管理员调整，请重新读取后核对。';
 if(status===403)return '当前无权执行此操作，请重新读取权限。';
 return '提交结果暂无法确认，请重新读取后核对。';
}
async function savePermission(data:Access,{subject,space,role,reason}:Pick<EditorProps,'subject'|'space'|'role'|'reason'>){
   const response=await fetch(endpoint+(data.can_manage?'/grants':'/requests'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data.can_manage?{expected_revision:data.revision,subject,space_id:space,role:role==='none'?null:role,reason:reason.trim()}:{})});
   if(!response.ok)throw Error(permissionFailure(response.status));
}
