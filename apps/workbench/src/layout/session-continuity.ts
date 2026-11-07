export type SessionScope={authenticated:boolean;authority_state:string;authority_ready?:boolean;user?:{subject:string;workspace_id:string;org_id:string}};
export function sessionScopeKey(session:SessionScope|null){
 return session?.authenticated&&session.user?JSON.stringify([session.user.org_id,session.user.workspace_id,session.user.subject]):'';
}
export function sessionConfirmed(session:SessionScope|null){return !!sessionScopeKey(session)&&(session?.authority_state==='confirmed'||session?.authority_state==='cached'&&session.authority_ready===true);}
