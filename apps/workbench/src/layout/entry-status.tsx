import React from 'react';
import {Button} from '@vxture/design-system';
import {User,SpinnerGap} from '@phosphor-icons/react';
import type {AccountProfile} from './account-profile';
import {UnifiedAccountCard} from './unified-account-card';
import {SpatialMotif} from './spatial-motif';
import type {EntryState} from './entry-state';

const states:Record<EntryState,{title:string;label:string;footnote?:string}>={
 connecting:{title:'正在连接',label:'连接中'},
 restoring:{title:'正在恢复登录',label:'恢复中'},
 'checking-access':{title:'正在确认使用权限',label:'核验中'},
 unavailable:{title:'暂时无法连接',label:'连接暂不可用'},
 recovery:{title:'等待恢复登录',label:'等待恢复'},
 'signed-out':{title:'已退出登录',label:'已退出'},
 subscription:{title:'当前工作区未开通',label:'未开通',footnote:'请联系管理员开通，或前往工作台。'},
 expired:{title:'工作区订阅需要续订',label:'待续订',footnote:'已有场景与成果会保留。'},
 unassigned:{title:'尚未获得使用授权',label:'待授权',footnote:'请联系组织管理员授权。'},
 'access-unavailable':{title:'暂时无法确认使用权限',label:'核验暂不可用'},
 connected:{title:'平台账号已连接',label:'已连接'},
};
export function EntryIdentity({user}:{readonly user?:AccountProfile}){
 if(!user)return null;
 return <div className="entry-identity" aria-label="当前账号与组织">
  <span className="entry-identity-icon"><User size={24} aria-hidden="true"/></span>
  <div className="entry-identity-copy"><strong title={user.display_name}>{user.display_name||'当前账号'}</strong><span title={user.org_name}>{user.org_name||'组织信息待补全'}</span></div>
 </div>;
}
function EntryIllustration({state}:{readonly state:EntryState}){
 const waiting=['connecting','restoring','checking-access','recovery'].includes(state);
 const unavailable=['unavailable','access-unavailable'].includes(state);
 return <SpatialMotif className="entry-state-art">
  <g transform="translate(167 49)">
  <rect x="158" y="88" width="42" height="36" rx="12" fill="var(--card)" stroke="currentColor" strokeOpacity=".35"/>
  <g stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
   {state==='signed-out'?<path d="M170 106h18m-6-6 6 6-6 6"/>:waiting?<path d="M186 103a8 8 0 1 0-1 9m2-14v6h-6"/>:unavailable?<><path d="M172 107a7 7 0 0 1 12-5m-15 10 18-14"/><path d="M185 111h1"/></>:state==='expired'?<><circle cx="179" cy="106" r="8"/><path d="M179 101v5l4 2"/></>:state==='connected'?<path d="m171 106 5 5 11-11"/>:<><rect x="172" y="104" width="14" height="11" rx="3"/><path d="M175 104v-4a4 4 0 0 1 8 0v4"/></>}
  </g>
  </g>
 </SpatialMotif>;
}
export function EntryStatus({state,user,onRetry,onLogin,preserveWork=false}:{readonly state:EntryState;readonly user?:AccountProfile;readonly onRetry?:()=>void;readonly onLogin?:()=>void;readonly preserveWork?:boolean}){
 const content=states[state],pending=['connecting','restoring','checking-access'].includes(state);
 const workspaceAction=['subscription','expired','unassigned'].includes(state);
 return <div className="entry-status" aria-busy={pending}>
  <header><h1>{content.title}</h1></header>
  <div className="entry-status-body">
   <EntryIllustration state={state}/>
  </div>
  <div className="entry-operation-group">
  {pending&&!user?<UnifiedAccountCard/>:<EntryIdentity user={user}/>}
  <div className="entry-actions">
   {pending?<Button className="entry-action" disabled><SpinnerGap className="entry-spinner" size={18}/>{content.label}…</Button>:<>
    {workspaceAction&&<Button className="entry-action" asChild><a href="https://ruyin.work/">前往工作台</a></Button>}
    {onLogin&&<Button className="entry-action" onClick={onLogin}>重新登录</Button>}
    {onRetry&&<Button className="entry-action" variant={workspaceAction||onLogin?'outline':'default'} onClick={onRetry}>重新检查</Button>}
    {state==='signed-out'&&<Button className="entry-action" variant="outline" asChild><a href="https://accounts.vxture.com/">账号中心</a></Button>}
   </>}
  </div>
  </div>
  <footer className={`entry-footnote${preserveWork||content.footnote?'':' entry-footnote-empty'}`} aria-hidden={!(preserveWork||content.footnote)}>{preserveWork?'请保留此页，在新标签页登录后返回。':content.footnote}</footer>
 </div>;
}
