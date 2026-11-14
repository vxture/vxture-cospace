export type SessionScope={authenticated:boolean;authority_state:string;authority_ready?:boolean;user?:{subject:string;workspace_id:string;org_id:string}};
export function sessionScopeKey(session:SessionScope|null){
 return session?.authenticated&&session.user?JSON.stringify([session.user.org_id,session.user.workspace_id,session.user.subject]):'';
}
export function sessionConfirmed(session:SessionScope|null){return !!sessionScopeKey(session)&&(session?.authority_state==='confirmed'||session?.authority_state==='cached'&&session.authority_ready===true);}

// Use monotonic time and the request start: network delay cannot extend a lease.
export function confirmationDeadline(seconds:unknown,requestStarted:number){
 return requestStarted+(typeof seconds==='number'&&Number.isFinite(seconds)?Math.max(0,seconds)*1000:0);
}

// Confirm directly. Only a rotated cookie/CSRF requires one recovery GET.
// This helper never sends or retries a business request.
export async function requestSessionConfirmation(send:typeof fetch,csrf:string,current:()=>boolean){
 const post=(token:string)=>send('/api/auth/session',{method:'POST',headers:{'X-CoSpace-CSRF':token}});
 let response=await post(csrf);
 if(!current())return null;
 if(response.status===403){
  const fresh=await send('/api/auth/session',{cache:'no-store'});
  if(!current())return null;
  if(fresh.ok){
   const saved=await fresh.json();
   if(!current())return null;
   response=await post(saved.csrf||'');
  }
 }
 return current()?response:null;
}
