import {appNavigate,appRoute} from './app-router';
import {SignInContent} from './signin-content';
import {EntryStatus} from './entry-status';
import {identityEntryState,subscriptionEntryState} from './entry-state';
import './entry-status.css';

import {sessionScopeKey,sessionConfirmed,confirmationDeadline,requestSessionConfirmation} from './session-continuity';
import React,{createContext,useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Button} from '@vxture/design-system';
import {HomeLayout} from './home-layout';
import {productQuotaMessage} from './product-quota-messages';
import type {AccountProfile} from './account-profile';

type Session={authenticated:boolean;authority_state:string;authority_ready?:boolean;confirmation_max_age_s?:number;csrf?:string;access_ready?:boolean;user?:AccountProfile};
export type AuthMode='checking'|'preview'|'platform'|'business'|'unavailable';
export const PlatformSession=createContext<Session|null>(null);
export const usePlatformSession=()=>useContext(PlatformSession);
type Subscription={application_authorized?:boolean|null;access_reason?:string|null;business_allowed:boolean;data_allowed:boolean;status:string|null;tier:string|null;bundled:boolean;pricing_url:string};
function SubscriptionNotice({value,unavailable=false,onRetry,user}:{value:Subscription|null;unavailable?:boolean;onRetry:()=>void;user?:AccountProfile}){
 const state=subscriptionEntryState(value,unavailable);
 return <EntryStatus state={state} user={user} onRetry={onRetry}/>;
}
function IdentitySubscription({user,onSessionCheck}:{user?:AccountProfile;onSessionCheck:()=>Promise<void>}){
 const [value,setValue]=useState<Subscription|null>(null),[enabled,setEnabled]=useState(false),[unavailable,setUnavailable]=useState(false),[checking,setChecking]=useState(true);
 const read=async(reconfirm=false)=>{setChecking(true);try{if(reconfirm)await onSessionCheck();const r=await fetch('/api/auth/config',{cache:'no-store'});if(!r.ok)throw Error();const config=await r.json();setEnabled(config.subscription_authorization===true);if(config.subscription_authorization===true){const r=await fetch('/api/subscription',{cache:'no-store'});if(!r.ok){if(r.status===401)await onSessionCheck();throw Error();}setValue(await r.json());}setUnavailable(false);}catch{setUnavailable(true);}finally{setChecking(false);}};
 useEffect(()=>{void read();},[]);
 if(checking)return <EntryStatus state="checking-access" user={user}/>;
 return enabled?<SubscriptionNotice user={user} value={value} unavailable={unavailable} onRetry={()=>void read(true)}/>:<EntryStatus state={unavailable?'access-unavailable':'connected'} user={user} onRetry={()=>void read(true)}/>;
}
export async function platformLogout(csrf:string){
 const response=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CoSpace-CSRF':csrf}});
 if(!response.ok)throw Error('logout_failed');
 // Same-origin tabs react immediately; other products/domains are checked on
 // resume through the platform's existing central-session protocol.
 try{localStorage.setItem('cospace.session.logout',String(Date.now()));}catch{}
 const result=await response.json();const destination=new URL(result.redirect_url);
 if(destination.protocol!=='https:'&&destination.origin!==location.origin)throw Error('logout_destination_rejected');
 try{sessionStorage.setItem('cospace.entry.signed-out','1');}catch{}
 location.assign(destination.href);
}

export function useAuthMode():AuthMode{
 const [mode,setMode]=useState<AuthMode>('checking');
 useEffect(()=>{const controller=new AbortController();fetch('/api/auth/config',{cache:'no-store',signal:controller.signal}).then(async response=>{
  // Old local engineering servers do not expose this new endpoint yet.
  if(response.status===404){setMode('preview');return;}
  if(!response.ok)throw new Error('config unavailable');
  const config=await response.json();
  if(config.enabled===true&&config.mode==='identity_pilot')setMode('platform');
  else if(config.enabled===true&&config.mode==='authorized_workbench'&&config.business_authorization===true)setMode('business');
  else if(config.enabled===false&&config.mode==='engineering_preview')setMode('preview');
  else throw new Error('invalid mode');
 }).catch(error=>{if(error.name!=='AbortError')setMode('unavailable');});return()=>controller.abort();},[]);
 return mode;
}

export function PlatformIdentityPage({preserveWork=false}:{preserveWork?:boolean}){
 const [session,setSession]=useState<Session|null>(null),[error,setError]=useState('');
 const csrf=useRef(''),activeAt=useRef(0);
 const read=async()=>{const r=await fetch('/api/auth/session',{cache:'no-store'});if(!r.ok)throw new Error();let value:Session=await r.json();csrf.current=value.csrf||'';if(value.authenticated){const r=await fetch('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':csrf.current}});if(!r.ok){setSession({...value,authority_state:'unavailable'});throw Error();}value=await r.json();}setSession(value);csrf.current=value.csrf||'';setError('');};
 useEffect(()=>{read().catch(()=>setError('平台会话暂不可用，请稍后重试。'));},[]);
 useEffect(()=>{const activity=(event:Event)=>{
  if(!event.isTrusted||!csrf.current||document.visibilityState!=='visible'||Date.now()-activeAt.current<30000)return;
  activeAt.current=Date.now();fetch('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':csrf.current}}).then(async r=>{
   if(!r.ok)throw new Error();const value:Session=await r.json();setSession(value);csrf.current=value.csrf||'';
  }).catch(()=>{setSession(old=>old?{...old,authority_state:'unavailable'}:old);setError('暂时无法确认平台状态。');});
 };window.addEventListener('pointerdown',activity);window.addEventListener('keydown',activity);return()=>{window.removeEventListener('pointerdown',activity);window.removeEventListener('keydown',activity);};},[]);
 const login=()=>{try{sessionStorage.removeItem('cospace.entry.signed-out');}catch{}const url='/auth/login?returnTo='+encodeURIComponent(location.pathname+location.search);if(preserveWork)window.open(url,'_blank','noopener,noreferrer');else location.assign(url);};
 const retry=()=>{void read().catch(()=>setError('平台会话暂不可用，请稍后重试。'));};
 let signedOut=false;try{signedOut=sessionStorage.getItem('cospace.entry.signed-out')==='1';}catch{}
 const state=identityEntryState(session,{failed:!!error,preserveWork,signedOut});
 const retrySession=()=>{retry();if(preserveWork)window.dispatchEvent(new Event('cospace:confirm-session'));};
 let content:React.ReactNode;
 if(state==='identity')content=<IdentitySubscription key={sessionScopeKey(session)} user={session?.user} onSessionCheck={read}/>;
 else if(state==='signin')content=<SignInContent onLogin={login}/>;
 else content=<EntryStatus state={state} user={session?.user} preserveWork={preserveWork} onLogin={state==='signed-out'||state==='recovery'&&!session?.authenticated?login:undefined} onRetry={state==='unavailable'||state==='recovery'?retrySession:undefined}/>;
 return <HomeLayout>{content}</HomeLayout>;

}

export function AuthBoundary({children}:{children:React.ReactNode}){
 const mode=useAuthMode();
 if(mode==='preview')return <>{children}</>;
 if(mode==='platform')return <PlatformIdentityPage/>;
 if(mode==='business')return <BusinessSession>{children}</BusinessSession>;
 return <HomeLayout><EntryStatus state={mode==='checking'?'connecting':'unavailable'} onRetry={mode==='unavailable'?()=>location.reload():undefined}/></HomeLayout>;
}

function BusinessSession({children}:{children:React.ReactNode}){
 const [quotaError,setQuotaError]=useState('');
 const [session,setSession]=useState<Session|null>(null),[ready,setReady]=useState(false),[error,setError]=useState('');
 const retained=useRef<Session|null>(null),lastScope=useRef('');
 useLayoutEffect(()=>{
  const key=sessionScopeKey(session);if(!key)return;
  if(lastScope.current&&lastScope.current!==key){
   window.dispatchEvent(new Event('cospace:scope-reset'));
   appNavigate('/'+appRoute(),true);
  }
  lastScope.current=key;
 },[session]);
 const [subscription,setSubscription]=useState<Subscription|null>(null),[subscriptionRequired,setSubscriptionRequired]=useState(false),[subscriptionUnavailable,setSubscriptionUnavailable]=useState(false);
 useEffect(()=>{let stopped=false;const nativeFetch=window.fetch.bind(window);let csrf='';let confirmAfter=0;let confirming:Promise<void>|null=null;let needsSubscription=false;let authority:Session|null=null;let businessAllowed=false;let generation=0;
  const acceptDeadline=(value:Session,started:number)=>{confirmAfter=confirmationDeadline(value.confirmation_max_age_s,started);};
  const checkSubscription=async(force=false)=>{
   if(!needsSubscription){businessAllowed=true;return;}
   const subscriptionGeneration=generation;businessAllowed=false;
   try{
    const r=await nativeFetch('/api/subscription',{cache:'no-store',...(force?{headers:{'Cache-Control':'no-cache'}}:{})});
    if(!r.ok)throw new Error('subscription_unavailable');
    const value:Subscription=await r.json();
    if(stopped||subscriptionGeneration!==generation)return;
    businessAllowed=value.business_allowed;setSubscription(value);setSubscriptionUnavailable(false);
   }catch{
    if(!stopped&&subscriptionGeneration===generation){setSubscription(null);setSubscriptionUnavailable(true);}
   }
  };
  const confirm=async(forceAccess=false)=>{
   const confirmationGeneration=generation,started=performance.now();
   const response=await requestSessionConfirmation(nativeFetch,csrf,()=>!stopped&&confirmationGeneration===generation);
   if(!response)return;
   if(!response.ok){authority=null;businessAllowed=false;generation++;setSession(old=>old?{...old,authority_state:'unavailable'}:old);throw new Error('会话确认暂不可用');}
   const next:Session=await response.json();if(stopped||confirmationGeneration!==generation)return;
   if(sessionScopeKey(authority)!==sessionScopeKey(next)){generation++;businessAllowed=false;setSubscription(null);setSession({...next,authority_state:'checking'});}
   authority=next;csrf=next.csrf||'';acceptDeadline(next,started);
   if(!sessionConfirmed(next)){businessAllowed=false;setSession(next);if(next.authenticated)throw new Error('会话确认暂不可用');return;}
   const acceptedGeneration=generation;
   setError('');await checkSubscription(forceAccess);if(!stopped&&acceptedGeneration===generation)setSession(next);
  };
  const recheck=(notify=false,forceAccess=false)=>{if(confirming)return;confirming=confirm(forceAccess).then(()=>{if(notify&&!stopped&&sessionConfirmed(authority)&&businessAllowed)window.dispatchEvent(new Event('cospace:session-confirmed'));}).catch(()=>{if(!stopped){authority=null;businessAllowed=false;generation++;setSession(old=>old?{...old,authority_state:'unavailable'}:old);setError('平台暂不可用，未保存修改保留在当前标签页。');}}).finally(()=>{confirming=null;});};
  const activity=(event:Event)=>{if(!event.isTrusted||document.visibilityState!=='visible'||performance.now()<confirmAfter)return;recheck();};
  const resume=(event:Event)=>{if(!event.isTrusted||document.visibilityState!=='visible'||performance.now()<confirmAfter)return;recheck(true);};
  const retry=()=>recheck(true,true);
  const otherTabLogout=(event:StorageEvent)=>{
   if(event.key!=='cospace.session.logout'||!event.newValue)return;
   window.dispatchEvent(new Event('cospace:access-invalidated'));authority=null;businessAllowed=false;csrf='';generation++;
   setSession({authenticated:false,authority_state:'signed_out'});setError('');
  };
  const bootstrapAuthority=async()=>{
   const started=performance.now();
   const response=await nativeFetch('/api/auth/session',{cache:'no-store'});
   if(!response.ok)throw new Error('无法读取平台会话');
   const next:Session=await response.json();csrf=next.csrf||'';authority=next;
   if(next.authenticated){
    try{sessionStorage.removeItem('cospace.entry.signed-out');}catch{}
    try{if(sessionConfirmed(next)&&next.confirmation_max_age_s&&next.confirmation_max_age_s>0){acceptDeadline(next,started);await checkSubscription();if(!stopped)setSession(next);}else await confirm();}catch{if(!stopped){setSession({...next,authority_state:'unavailable'});setError('平台会话暂不可用，重新检查后继续。');}}
   }else if(!stopped)setSession(next);
  };
  const bootstrap=async()=>{
   const config=await nativeFetch('/api/auth/config').then(r=>{if(!r.ok)throw new Error('auth_config_unavailable');return r.json();});
   needsSubscription=config.subscription_authorization===true;setSubscriptionRequired(needsSubscription);
   await bootstrapAuthority();
   if(stopped)return;
   window.fetch=async(input,init)=>{const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.href);
    if(url.origin!==location.origin)return nativeFetch(input,init);
    const requestGeneration=generation;
    // Lazy engine/config reads can start long after the last visible input.
    // Confirm before sending them, rather than relying on pointer/focus events.
    const business=url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/api/auth/');
    if(business&&performance.now()>=confirmAfter)recheck();
    if(confirming&&business)await confirming;
    if(requestGeneration!==generation)return new Response(JSON.stringify({detail:'session_scope_changed'}),{status:409,headers:{'Content-Type':'application/json'}});
    if(business&&(!sessionConfirmed(authority)||!businessAllowed))return new Response(JSON.stringify({detail:'session_confirmation_required'}),{status:401,headers:{'Content-Type':'application/json'}});
    const method=(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase();
    const headers=new Headers(init?.headers||(input instanceof Request?input.headers:undefined));
    if(!['GET','HEAD'].includes(method)&&csrf)headers.set('X-CoSpace-CSRF',csrf);
    const result=await nativeFetch(input,{...init,headers});
    if(requestGeneration!==generation)return new Response(JSON.stringify({detail:'session_scope_changed'}),{status:409,headers:{'Content-Type':'application/json'}});
    if(needsSubscription&&[403,409,503].includes(result.status)){
     const body=await result.clone().json().catch(()=>({}));
     const quotaMessage=productQuotaMessage(body.code||body.detail);
     if(quotaMessage){setQuotaError(quotaMessage);}
     if(body.detail==='subscription_required'||body.detail==='subscription_unavailable'||body.detail==='application_access_required'){window.dispatchEvent(new Event('cospace:access-invalidated'));await checkSubscription();}
    }
    if(result.status===401&&!url.pathname.startsWith('/api/auth/')){window.dispatchEvent(new Event('cospace:access-invalidated'));authority=null;businessAllowed=false;csrf='';generation++;setSession({authenticated:false,authority_state:'signed_out'});setError('');}
    if(result.ok&&!['GET','HEAD'].includes(method)&&url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/api/auth/')&&!/comparisons|\/query(?:-range)?$/.test(url.pathname))window.dispatchEvent(new Event('cospace:records-changed'));
    return result;
   };
   setReady(true);window.addEventListener('pointerdown',activity);window.addEventListener('keydown',activity);window.addEventListener('focus',resume);document.addEventListener('visibilitychange',resume);window.addEventListener('cospace:confirm-session',retry);window.addEventListener('storage',otherTabLogout);
  };bootstrap().catch(()=>{if(!stopped)setError('平台会话暂不可用，请刷新重试。');});
  return()=>{stopped=true;window.fetch=nativeFetch;window.removeEventListener('pointerdown',activity);window.removeEventListener('keydown',activity);window.removeEventListener('focus',resume);document.removeEventListener('visibilitychange',resume);window.removeEventListener('cospace:confirm-session',retry);window.removeEventListener('storage',otherTabLogout);};
 },[]);
 if(error&&!ready)return <HomeLayout><EntryStatus state="unavailable" onRetry={()=>location.reload()}/></HomeLayout>;
 if(!ready)return <HomeLayout><EntryStatus state="restoring"/></HomeLayout>;
 const authorized=sessionConfirmed(session)&&(!subscriptionRequired||!!subscription?.business_allowed&&!subscriptionUnavailable);
 if(session?.authenticated&&retained.current&&sessionScopeKey(session)!==sessionScopeKey(retained.current))retained.current=null;
 if(authorized)retained.current=session;
 const suspended=!!retained.current&&!authorized;
 return <>
  {retained.current&&<div style={authorized?{display:'contents'}:{display:'none'}} aria-hidden={!authorized} inert={!authorized}><PlatformSession.Provider value={retained.current}><React.Fragment key={sessionScopeKey(retained.current)}>{children}</React.Fragment></PlatformSession.Provider></div>}
  {!authorized&&(!session?.authenticated?<PlatformIdentityPage preserveWork={suspended}/>:!sessionConfirmed(session)?<HomeLayout><EntryStatus state="recovery" user={session.user} preserveWork={suspended} onRetry={()=>window.dispatchEvent(new Event('cospace:confirm-session'))}/></HomeLayout>:<HomeLayout><SubscriptionNotice user={session.user} value={subscription} unavailable={subscriptionUnavailable} onRetry={()=>window.dispatchEvent(new Event('cospace:confirm-session'))}/></HomeLayout>)}
  {authorized&&(quotaError||error)&&<div role="alert" className="fixed bottom-lg left-lg right-lg z-notification flex flex-wrap items-center gap-md rounded-md border bg-popover p-lg text-body-small"><span>{quotaError||error}</span>{quotaError&&<Button variant="ghost" size="sm" onClick={()=>setQuotaError('')}>关闭提示</Button>}</div>}
 </>;
}
