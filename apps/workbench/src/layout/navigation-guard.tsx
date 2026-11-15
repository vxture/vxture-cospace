import {keepsAssociationDrafts} from './association-context';
import {useBlocker} from 'react-router-dom';
import React,{useEffect,useState,useSyncExternalStore} from 'react';
import {Button,AlertDialogCancel,AlertDialog,AlertDialogContent,AlertDialogHeader,AlertDialogTitle,AlertDialogDescription,AlertDialogFooter} from '@vxture/design-system';
import {subscribeNavigationPrompt,navigationPrompt,resolveNavigation,requestLeave,drafts} from './unsaved-navigation';
export function NavigationGuard(){
 const blocker=useBlocker(({currentLocation,nextLocation})=>drafts.entries.size>0&&!keepsAssociationDrafts(currentLocation.pathname+currentLocation.search+currentLocation.hash,nextLocation.pathname+nextLocation.search+nextLocation.hash));
 useEffect(()=>{if(blocker.state!=='blocked')return;let active=true;
  void requestLeave().then(allow=>{if(active){if(allow)blocker.proceed();else blocker.reset();}});
  return()=>{active=false;};
 },[blocker]);
 const prompt=useSyncExternalStore(subscribeNavigationPrompt,navigationPrompt),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{setError('');},[prompt]);
 async function choose(choice:'save'|'discard'|'cancel'){
  setBusy(true);setError('');try{const ok=await resolveNavigation(choice);if(choice==='save'&&!ok)setError('保存未完成，请返回编辑面核对原因和必填项。修改仍保留，尚未离开。');}finally{setBusy(false);}
 }
 return <AlertDialog open={!!prompt} onOpenChange={open=>{if(!open&&!busy)void choose('cancel');}}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>处理未保存的修改</AlertDialogTitle><AlertDialogDescription>{prompt?.labels.join('、')}。请选择保存后继续、放弃修改，或留在当前工作面。</AlertDialogDescription></AlertDialogHeader>{!prompt?.canSave&&<p>部分修改需要在原编辑面完成必填项、核对或生成候选，请取消离开后保存。</p>}{error&&<p role="alert">{error}</p>}<AlertDialogFooter><AlertDialogCancel asChild><Button variant="ghost" disabled={busy} onClick={event=>{event.preventDefault();void choose('cancel');}}>取消离开</Button></AlertDialogCancel><Button variant="destructive-strong" disabled={busy} onClick={()=>void choose('discard')}>放弃修改并继续</Button><Button disabled={busy||!prompt?.canSave} onClick={()=>void choose('save')}>{busy?'处理中…':'保存后继续'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>;
}
