import React,{useLayoutEffect,useRef,useSyncExternalStore} from 'react';
import {useLocation} from 'react-router-dom';
import {ConfirmDestructive} from '@vxture/design-system';
import {OperationConfirmationStore,type OperationDetails} from './operation-confirmation-store';

const operations=new OperationConfirmationStore();
window.addEventListener('cospace:scope-reset',()=>operations.cancel());

/** Scope includes the record and its reviewed revision/draft, never just its label. */
export function useOperationConfirmation(scope:string){
 const owner=useRef(Symbol());
 useLayoutEffect(()=>()=>operations.cancel(owner.current),[scope]);
 return(details:OperationDetails,execute:()=>unknown|Promise<unknown>)=>operations.request(owner.current,details,execute);
}

export function OperationConfirmations(){
 const location=useLocation(),pending=useSyncExternalStore(operations.subscribe,operations.snapshot);
 useLayoutEffect(()=>{operations.cancel();},[location.pathname,location.search]);
 return pending?<ConfirmDestructive open verb={pending.verb} target={pending.target} consequence={pending.consequence} preconditions={pending.preconditions} titleTemplate="{verb}{target}？" cancelLabel="取消" pendingLabel="处理中…" blockedHint="当前条件不满足，请取消并核对。" onOpenChange={open=>{if(!open)operations.cancel(pending.owner);}} onConfirm={()=>operations.commit(pending)}/>:null;
}
