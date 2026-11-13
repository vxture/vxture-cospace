import {sessionConfirmed,type SessionScope} from './session-continuity.ts';

export type EntryState='connecting'|'restoring'|'checking-access'|'unavailable'|'recovery'|'signed-out'|'subscription'|'expired'|'unassigned'|'access-unavailable'|'connected';
export type EntrySubscription={application_authorized?:boolean|null;business_allowed:boolean;status:string|null};

// Display platform facts without inferring billing decisions from the presence of a status.
export function subscriptionEntryState(value:EntrySubscription|null,unavailable=false):EntryState{
 if(unavailable)return 'access-unavailable';
 if(!value)return 'checking-access';
 if(value.application_authorized===false)return 'unassigned';
 if(value.business_allowed)return 'connected';
 return value.status==='expired'?'expired':'subscription';
}

export function identityEntryState(session:SessionScope|null,{failed=false,preserveWork=false,signedOut=false}={}):EntryState|'signin'|'identity'{
 if(!session)return failed?'unavailable':'restoring';
 if(session.authenticated)return sessionConfirmed(session)?'identity':'recovery';
 if(preserveWork)return 'recovery';
 return signedOut?'signed-out':'signin';
}
