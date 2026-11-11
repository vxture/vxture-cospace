import {keepsAssociationDrafts} from './association-context';
import {useBlocker} from 'react-router-dom';
import React,{useEffect,useState,useSyncExternalStore} from 'react';
import {Button,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter} from '@vxture/design-system';
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
 return <Dialog open={!!prompt} onOpenChange={open=>{if(!open&&!busy)void choose('cancel');}}><DialogContent><DialogHeader><DialogTitle>处理未保存的修改</DialogTitle><DialogDescription>{prompt?.labels.join('、')}。请选择保存后继续、放弃修改，或留在当前工作面。</DialogDescription></DialogHeader>{!prompt?.canSave&&<p>部分修改需要在原编辑面完成必填项、核对或生成候选，请取消离开后保存。</p>}{error&&<p role="alert">{error}</p>}<DialogFooter><Button variant="ghost" disabled={busy} onClick={()=>void choose('cancel')}>取消离开</Button><Button variant="outline" disabled={busy} onClick={()=>void choose('discard')}>放弃修改并继续</Button><Button disabled={busy||!prompt?.canSave} onClick={()=>void choose('save')}>{busy?'处理中…':'保存后继续'}</Button></DialogFooter></DialogContent></Dialog>;
}
