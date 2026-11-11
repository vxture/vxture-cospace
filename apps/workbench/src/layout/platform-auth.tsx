import {appNavigate,appRoute} from './app-router';
import {Info,ArrowClockwise} from '@phosphor-icons/react';
import {SignInContent} from './signin-content';

import {sessionScopeKey,sessionConfirmed} from './session-continuity';
import React,{createContext,useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Button,Icon} from '@vxture/design-system';
import {HomeLayout} from './home-layout';
import {productQuotaMessage} from './product-quota-messages';
import type {AccountProfile} from './account-profile';

type Session={authenticated:boolean;authority_state:string;authority_ready?:boolean;csrf?:string;access_ready?:boolean;user?:AccountProfile};
export type AuthMode='checking'|'preview'|'platform'|'business'|'unavailable';
export const PlatformSession=createContext<Session|null>(null);
export const usePlatformSession=()=>useContext(PlatformSession);
type Subscription={business_allowed:boolean;data_allowed:boolean;status:string|null;tier:string|null;bundled:boolean;pricing_url:string};
function SubscriptionNotice({value,unavailable=false,onRetry}:{value:Subscription|null;unavailable?:boolean;onRetry:()=>void}){
 if(!value&&!unavailable)return <p role="status" className="text-body-small text-muted-foreground">正在检查工作区订阅…</p>;
 const lapsed=value?.status!=null&&!value?.business_allowed;
 return <section className="grid gap-lg" aria-label="Workspace 订阅"><div><h2 className="text-heading-2">{unavailable?'订阅状态暂不可用':value?.business_allowed?'工作区已开通 CoSpace':lapsed?'工作区订阅需要续订':'工作区尚未开通 CoSpace'}</h2><p className="mt-md text-body-small text-muted-foreground">{unavailable?'平台会话已保留，请稍后重新检查。':value?.business_allowed?'空间访问仍按当前工作区的场景权限执行。':lapsed?'请检查当前工作区的订阅状态。已有空间与历史成果会保留。':'请为当前工作区开通订阅后使用空间服务。已有空间与历史成果会保留。'}</p></div><div className="flex flex-wrap gap-md"><Button variant="outline" onClick={onRetry}>重新检查</Button>{!unavailable&&!value?.business_allowed&&<Button onClick={()=>location.assign(value?.pricing_url||'https://vxture.com/pricing?product=cospace')}>查看套餐与权益<Icon name="arrow-right"/></Button>}</div></section>;
}
function IdentitySubscription(){
 const [value,setValue]=useState<Subscription|null>(null),[enabled,setEnabled]=useState(false),[unavailable,setUnavailable]=useState(false);
 const read=async()=>{try{const config=await fetch('/api/auth/config').then(r=>r.json());setEnabled(config.subscription_authorization===true);if(config.subscription_authorization!==true)return;const session=await fetch('/api/auth/session',{cache:'no-store'}).then(r=>r.json());if(!session.authenticated)throw Error();const active=await fetch('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':session.csrf}});if(!active.ok)throw Error();const r=await fetch('/api/subscription',{cache:'no-store'});if(!r.ok)throw Error();setValue(await r.json());setUnavailable(false);}catch{setUnavailable(true);}};
 useEffect(()=>{void read();},[]);
 return enabled?<SubscriptionNotice value={value} unavailable={unavailable} onRetry={()=>void read()}/>:null;
}
export async function platformLogout(csrf:string){
 const response=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CoSpace-CSRF':csrf}});
 if(!response.ok)throw Error('logout_failed');
 // Same-origin tabs react immediately; other products/domains are checked on
 // resume through the platform's existing central-session protocol.
 try{localStorage.setItem('cospace.session.logout',String(Date.now()));}catch{}
 const result=await response.json();const destination=new URL(result.redirect_url);
 if(destination.protocol!=='https:'&&destination.origin!==location.origin)throw Error('logout_destination_rejected');
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

export function PlatformIdentityPage({business=false,preserveWork=false}:{business?:boolean;preserveWork?:boolean}){
 const [session,setSession]=useState<Session|null>(null),[error,setError]=useState('');
 const [busy,setBusy]=useState(false);const csrf=useRef(''),activeAt=useRef(0);
 const read=async()=>{const r=await fetch('/api/auth/session',{cache:'no-store'});if(!r.ok)throw new Error();const value:Session=await r.json();setSession(value);csrf.current=value.csrf||'';setError('');};
 useEffect(()=>{read().catch(()=>setError('平台会话暂不可用，请稍后重试。'));},[]);
 useEffect(()=>{const activity=(event:Event)=>{
  if(!event.isTrusted||!csrf.current||document.visibilityState!=='visible'||Date.now()-activeAt.current<30000)return;
  activeAt.current=Date.now();fetch('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':csrf.current}}).then(async r=>{
   if(!r.ok)throw new Error();const value:Session=await r.json();setSession(value);csrf.current=value.csrf||'';
  }).catch(()=>setError('暂时无法确认平台状态，会话已保留。'));
 };window.addEventListener('pointerdown',activity);window.addEventListener('keydown',activity);return()=>{window.removeEventListener('pointerdown',activity);window.removeEventListener('keydown',activity);};},[]);
 const login=()=>{const url='/auth/login?returnTo='+encodeURIComponent((location.pathname==='/'?'/space':location.pathname+location.search));if(preserveWork)window.open(url,'_blank','noopener,noreferrer');else location.assign(url);};
 return <HomeLayout>
    {session?.authenticated?<><h2 className="text-heading-1">{session.user?.display_name}</h2><p className="text-body-small text-muted-foreground">平台会话已建立。空间权限与业务接口正在接入。</p><dl className="grid grid-cols-[auto_1fr] gap-x-lg gap-y-md text-body-small"><dt>组织</dt><dd className="break-all">{session.user?.org_id}</dd><dt>工作区</dt><dd className="break-all">{session.user?.workspace_id}</dd><dt>会话状态</dt><dd>{session.authority_state==='unavailable'?'平台暂不可达，会话已保留':session.authority_state==='confirmed'?'平台已确认':'已保存平台会话'}</dd></dl><IdentitySubscription/><p className="text-label-small text-muted-foreground">此入口尚未开放空间数据，原工程预览服务独立运行。</p><div className="flex flex-wrap gap-md"><Button variant="outline" disabled={busy} onClick={async()=>{setBusy(true);try{const r=await fetch('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':csrf.current}});if(!r.ok)throw new Error();const value:Session=await r.json();setSession(value);csrf.current=value.csrf||'';setError('');}catch{setError('平台状态暂不可用，会话已保留。');}finally{setBusy(false);}}}>检查平台会话</Button><Button variant="outline" onClick={login}>重新连接</Button></div><form action="/auth/logout" method="post"><input type="hidden" name="csrf" value={session.csrf||''}/><Button type="submit" variant="ghost"><Icon name="sign-out"/>退出平台登录</Button></form></>:<><SignInContent onLogin={login}/></>}
    {error&&<p className="text-body-small text-destructive" role="alert">{error}</p>}
 </HomeLayout>;
}

export function AuthBoundary({children}:{children:React.ReactNode}){
 const mode=useAuthMode();
 if(mode==='preview')return <>{children}</>;
 if(mode==='platform')return <PlatformIdentityPage/>;
 if(mode==='business')return <BusinessSession>{children}</BusinessSession>;
 return <main className="flex min-h-dvh items-center justify-center bg-background text-foreground"><p role="status" className="text-body-small text-muted-foreground">{mode==='checking'?'正在连接 CoSpace…':'认证配置暂不可用，请刷新重试。'}</p></main>;
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
 useEffect(()=>{let stopped=false;const nativeFetch=window.fetch.bind(window);let csrf='';let activityAt=0;let confirming:Promise<void>|null=null;let needsSubscription=false;let authority:Session|null=null;let businessAllowed=false;let generation=0;
  const checkSubscription=async()=>{if(!needsSubscription){businessAllowed=true;return;}const subscriptionGeneration=generation;businessAllowed=false;try{const r=await nativeFetch('/api/subscription',{cache:'no-store'});if(!r.ok)throw Error();const value:Subscription=await r.json();if(stopped||subscriptionGeneration!==generation)return;businessAllowed=value.business_allowed;if(!stopped){setSubscription(value);setSubscriptionUnavailable(false);}}catch{if(!stopped&&subscriptionGeneration===generation){setSubscription(null);setSubscriptionUnavailable(true);}}};
  const confirm=async()=>{
   const confirmationGeneration=generation;
   {const r=await nativeFetch('/api/auth/session',{cache:'no-store'});if(!r.ok)throw new Error('会话暂不可读');const saved:Session=await r.json();if(stopped||confirmationGeneration!==generation)return;csrf=saved.csrf||'';authority=saved;if(!saved.authenticated){setSession(saved);return;}}
   const response=await nativeFetch('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':csrf}});
   if(stopped||confirmationGeneration!==generation)return;
   if(!response.ok){authority=null;businessAllowed=false;generation++;setSession(old=>old?{...old,authority_state:'unavailable'}:old);throw new Error('会话确认暂不可用');}
   const next:Session=await response.json();if(stopped||confirmationGeneration!==generation)return;
   if(sessionScopeKey(authority)!==sessionScopeKey(next)){generation++;businessAllowed=false;setSubscription(null);setSession({...next,authority_state:'checking'});}
   authority=next;csrf=next.csrf||'';
   if(!sessionConfirmed(next)){businessAllowed=false;setSession(next);if(next.authenticated)throw new Error('会话确认暂不可用');return;}
   const acceptedGeneration=generation;
   setError('');await checkSubscription();if(!stopped&&acceptedGeneration===generation)setSession(next);
  };
  const recheck=(notify=false)=>{if(confirming)return;activityAt=Date.now();confirming=confirm().then(()=>{if(notify&&!stopped&&sessionConfirmed(authority)&&businessAllowed)window.dispatchEvent(new Event('cospace:session-confirmed'));}).catch(()=>{if(!stopped){authority=null;businessAllowed=false;generation++;setSession(old=>old?{...old,authority_state:'unavailable'}:old);setError('平台暂不可用，未保存修改保留在当前标签页。');}}).finally(()=>{confirming=null;});};
  const activity=(event:Event)=>{if(!event.isTrusted||document.visibilityState!=='visible'||Date.now()-activityAt<30000)return;recheck();};
  const resume=(event:Event)=>{if(!event.isTrusted||document.visibilityState!=='visible')return;recheck(true);};
  const retry=()=>recheck(true);
  const otherTabLogout=(event:StorageEvent)=>{
   if(event.key!=='cospace.session.logout'||!event.newValue)return;
   authority=null;businessAllowed=false;csrf='';generation++;
   setSession({authenticated:false,authority_state:'signed_out'});setError('');
  };
  const bootstrap=async()=>{const config=await nativeFetch('/api/auth/config').then(r=>{if(!r.ok)throw Error();return r.json();});needsSubscription=config.subscription_authorization===true;setSubscriptionRequired(needsSubscription);const response=await nativeFetch('/api/auth/session',{cache:'no-store'});if(!response.ok)throw Error('无法读取平台会话');const next:Session=await response.json();csrf=next.csrf||'';authority=next;
   if(next.authenticated)await confirm();else if(!stopped)setSession(next);
   if(stopped)return;
   window.fetch=async(input,init)=>{const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.href);
    if(url.origin!==location.origin)return nativeFetch(input,init);
    const requestGeneration=generation;
    // Lazy engine/config reads can start long after the last visible input.
    // Confirm before sending them, rather than relying on pointer/focus events.
    if(!url.pathname.startsWith('/api/auth/')&&Date.now()-activityAt>=30000)recheck();
    if(confirming&&!url.pathname.startsWith('/api/auth/'))await confirming;
    if(requestGeneration!==generation)return new Response(JSON.stringify({detail:'session_scope_changed'}),{status:409,headers:{'Content-Type':'application/json'}});
    if(!url.pathname.startsWith('/api/auth/')&&(!sessionConfirmed(authority)||!businessAllowed))return new Response(JSON.stringify({detail:'session_confirmation_required'}),{status:401,headers:{'Content-Type':'application/json'}});
    const method=(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase();
    const headers=new Headers(init?.headers||(input instanceof Request?input.headers:undefined));
    if(!['GET','HEAD'].includes(method)&&csrf)headers.set('X-CoSpace-CSRF',csrf);
    const result=await nativeFetch(input,{...init,headers});
    if(requestGeneration!==generation)return new Response(JSON.stringify({detail:'session_scope_changed'}),{status:409,headers:{'Content-Type':'application/json'}});
    if(needsSubscription&&[403,409,503].includes(result.status)){const body=await result.clone().json().catch(()=>({}));const quotaMessage=productQuotaMessage(body.code||body.detail);if(quotaMessage)setQuotaError(quotaMessage);if(body.detail==='subscription_required'||body.detail==='subscription_unavailable')await checkSubscription();}
    if(result.status===401&&!url.pathname.startsWith('/api/auth/')){authority=null;businessAllowed=false;csrf='';generation++;setSession({authenticated:false,authority_state:'signed_out'});setError('');}
    if(result.ok&&!['GET','HEAD'].includes(method)&&url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/api/auth/')&&!/comparisons|\/query(?:-range)?$/.test(url.pathname))window.dispatchEvent(new Event('cospace:records-changed'));
    return result;
   };
   setReady(true);window.addEventListener('pointerdown',activity);window.addEventListener('keydown',activity);window.addEventListener('focus',resume);document.addEventListener('visibilitychange',resume);window.addEventListener('cospace:confirm-session',retry);window.addEventListener('storage',otherTabLogout);
  };bootstrap().catch(()=>{if(!stopped)setError('平台会话暂不可用，请刷新重试。');});
  return()=>{stopped=true;window.fetch=nativeFetch;window.removeEventListener('pointerdown',activity);window.removeEventListener('keydown',activity);window.removeEventListener('focus',resume);document.removeEventListener('visibilitychange',resume);window.removeEventListener('cospace:confirm-session',retry);window.removeEventListener('storage',otherTabLogout);};
 },[]);
 if(error&&!ready)return <HomeLayout><p role="alert">{error}</p></HomeLayout>;
 if(!ready)return <HomeLayout><p role="status">正在确认平台会话…</p></HomeLayout>;
 const authorized=sessionConfirmed(session)&&(!subscriptionRequired||!!subscription?.business_allowed&&!subscriptionUnavailable);
 if(session?.authenticated&&retained.current&&sessionScopeKey(session)!==sessionScopeKey(retained.current))retained.current=null;
 if(authorized)retained.current=session;
 const suspended=!!retained.current&&!authorized;
 return <>
  {retained.current&&<div style={authorized?{display:'contents'}:{display:'none'}} aria-hidden={!authorized} inert={!authorized}><PlatformSession.Provider value={retained.current}><React.Fragment key={sessionScopeKey(retained.current)}>{children}</React.Fragment></PlatformSession.Provider></div>}
  {!authorized&&(!session?.authenticated?<><PlatformIdentityPage business preserveWork={suspended}/>{suspended&&<section className="session-recovery-notice" role="status" aria-label="恢复当前工作"><Info size={20} aria-hidden="true"/><div><strong>会话已失效，当前工作已暂存</strong><p>点击“继续登录”将在新标签页登录，完成后回到此页。请勿刷新或关闭此页。</p><Button variant="ghost" size="sm" onClick={()=>window.dispatchEvent(new Event('cospace:confirm-session'))}><ArrowClockwise size={16}/>重新检查会话</Button></div></section>}</>:!sessionConfirmed(session)?<HomeLayout><h2>等待恢复平台会话</h2><p>工作面已遮挡，内存草稿保留。确认会话后可继续；不会重放保存、构建或发布操作。</p><Button onClick={()=>window.dispatchEvent(new Event('cospace:confirm-session'))}>重新检查会话</Button></HomeLayout>:<HomeLayout><p>{session.user?.display_name} · 当前工作区</p><SubscriptionNotice value={subscription} unavailable={subscriptionUnavailable} onRetry={()=>window.dispatchEvent(new Event('cospace:confirm-session'))}/><Button variant="ghost" onClick={()=>platformLogout(session.csrf||'')}>退出登录</Button></HomeLayout>)}
  {authorized&&(quotaError||error)&&<div role="alert" className="fixed bottom-lg left-lg right-lg z-notification flex flex-wrap items-center gap-md rounded-md border bg-popover p-lg text-body-small"><span>{quotaError||error}</span>{quotaError&&<Button variant="ghost" size="sm" onClick={()=>setQuotaError('')}>关闭提示</Button>}</div>}
 </>;
}
