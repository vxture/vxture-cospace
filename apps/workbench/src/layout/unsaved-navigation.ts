import {useLayoutEffect,useRef} from 'react';
// Installed before React's hash subscriptions, including browser back/forward.
const drafts=new Map<symbol,string>();
let accepted=location.href;
let permitted=false;
function approve(){return !drafts.size||window.confirm(`尚有未保存的修改（${[...new Set(drafts.values())].join('、')}）。离开后可能丢失。确定离开？`);}
window.addEventListener('hashchange',event=>{
 if(location.href===accepted)return;
 if(!permitted&&!approve()){event.stopImmediatePropagation();history.replaceState(null,'',accepted);return;}
 permitted=false;accepted=location.href;
});
document.addEventListener('click',event=>{
 const anchor=(event.target as Element)?.closest('a');
 if(!anchor||event.defaultPrevented||event.ctrlKey||event.metaKey||event.shiftKey||anchor.target==='_blank')return;
 const url=new URL(anchor.href,location.href);
 if(url.origin===location.origin&&url.pathname===location.pathname&&url.hash!==location.hash){
  if(!approve()){event.preventDefault();event.stopImmediatePropagation();}else if(drafts.size)permitted=true;
 }
},true);
export function confirmUnsavedChanges(){return approve();}
export function approveNavigation(){const allowed=approve();if(allowed&&drafts.size)permitted=true;return allowed;}
window.addEventListener('beforeunload' ,event=>{if(drafts.size){event.preventDefault();event.returnValue='';}});
export function useUnsavedNavigation(dirty:boolean,label:string){
 const id=useRef(Symbol());
 useLayoutEffect(()=>{if(dirty)drafts.set(id.current,label);else drafts.delete(id.current);return()=>{drafts.delete(id.current);};},[dirty,label]);
}
