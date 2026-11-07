import {useLayoutEffect,useRef} from 'react';
import {DraftRegistry,type Draft} from './draft-registry';
export const drafts=new DraftRegistry();
let accepted=location.href,index=0;
const marker='cospaceNavigationIndex';
history.replaceState({...history.state,[marker]:index},'',accepted);
let permitted='',restoring=false;
type Prompt={labels:string[];canSave:boolean;resolve:(allow:boolean)=>void};
let prompt:Prompt|null=null;
const listeners=new Set<()=>void>();
const changed=()=>listeners.forEach(fn=>fn());
export const subscribeNavigationPrompt=(fn:()=>void)=>{listeners.add(fn);return()=>{listeners.delete(fn);};};
export const navigationPrompt=()=>prompt;
export function requestLeave(){
 if(prompt)return Promise.resolve(false);
 const entries=drafts.list();if(!entries.length)return Promise.resolve(true);
 return new Promise<boolean>(resolve=>{prompt={labels:[...new Set(entries.map(([,d])=>d.label))],canSave:entries.every(([,d])=>!!d.save&&d.canSave!==false),resolve};changed();});
}
export async function resolveNavigation(choice:'save'|'discard'|'cancel'){
 const current=prompt;if(!current)return;
 let allow=false;
 try{if(choice==='save')allow=await drafts.saveAll();else if(choice==='discard'){drafts.discardAll();allow=true;}}
 catch{allow=false;}
 if(prompt!==current)return false;
 if(allow||choice==='cancel'){prompt=null;changed();current.resolve(allow);}
 return allow;
}
export async function runGuarded(action:()=>void){if(await requestLeave())action();}
export async function navigateSafely(href:string){
 if(href===location.hash||new URL(href,location.href).href===location.href)return;
 if(await requestLeave()){permitted=new URL(href,location.href).href;location.assign(href);}
}
// Back/forward keeps the original history entry: cancel returns to the accepted
// index rather than replacing the destination and destroying it.
window.addEventListener('hashchange',event=>{
 if(restoring&&location.href===accepted){restoring=false;return;}
 if(location.href===accepted)return;
 const destination=location.href;
 let next=history.state?.[marker];
 if(!Number.isInteger(next)){next=index+1;history.replaceState({...history.state,[marker]:next},'',destination);}
 if(drafts.entries.size&&permitted!==destination){
  event.stopImmediatePropagation();const delta=next-index;restoring=true;history.go(-delta);
  void requestLeave().then(allow=>{if(allow){permitted=destination;history.go(delta);}});
  return;
 }
 permitted='';accepted=destination;index=next;
});
document.addEventListener('click',event=>{
 const anchor=(event.target instanceof Element?event.target:null)?.closest('a');
 if(!anchor||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||anchor.target==='_blank'||anchor.hasAttribute('download'))return;
 const url=new URL(anchor.href,location.href);
 if(url.origin===location.origin&&url.pathname===location.pathname&&url.search===location.search&&url.hash!==location.hash){
  event.preventDefault();void navigateSafely(url.href);
 }
},true);
window.addEventListener('beforeunload',event=>{if(drafts.entries.size){event.preventDefault();event.returnValue='';}});
export function useUnsavedNavigation(dirty:boolean,label:string,options:Omit<Draft,'label'>={}){
 const id=useRef(Symbol());
 useLayoutEffect(()=>{drafts.set(id.current,dirty?{label,...options}:null);return()=>drafts.set(id.current,null);});
 return()=>drafts.set(id.current,null);
}

window.addEventListener('cospace:scope-reset',()=>{
 const previous=prompt;prompt=null;drafts.clear();permitted='';restoring=false;
 accepted=location.href;index=0;history.replaceState({...history.state,[marker]:0},'',accepted);
 changed();previous?.resolve(false);
});
