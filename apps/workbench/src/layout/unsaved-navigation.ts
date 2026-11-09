import {useLayoutEffect,useRef} from 'react';
import {appNavigate} from './app-router';
import {DraftRegistry,type Draft} from './draft-registry';
export const drafts=new DraftRegistry();
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
export async function navigateSafely(href:string){appNavigate(href);}
// Native anchors share the same router as imperative actions. Modified clicks and
// new tabs retain standard browser behavior; React Router blocks dirty transitions.
const routes=new Set(['/', '/space','/data','/build','/delivery','/ontology','/association','/settings','/members','/identity','/account']);
document.addEventListener('click',event=>{
 const anchor=(event.target instanceof Element?event.target:null)?.closest('a');
 if(!anchor||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||anchor.target==='_blank'||anchor.hasAttribute('download'))return;
 const url=new URL(anchor.href,location.href);
 if(url.origin===location.origin&&routes.has(url.pathname)){
  event.preventDefault();appNavigate(url.pathname+url.search+url.hash);
 }
},true);
window.addEventListener('beforeunload',event=>{if(drafts.entries.size){event.preventDefault();event.returnValue='';}});
export function useUnsavedNavigation(dirty:boolean,label:string,options:Omit<Draft,'label'>={}){
 const id=useRef(Symbol()),acknowledged=useRef(false);
 useLayoutEffect(()=>{if(!dirty)acknowledged.current=false;drafts.set(id.current,dirty&&!acknowledged.current?{label,...options}:null);return()=>drafts.set(id.current,null);});
 return()=>{acknowledged.current=true;drafts.set(id.current,null);};
}

window.addEventListener('cospace:scope-reset',()=>{
 const previous=prompt;prompt=null;drafts.clear();
 changed();previous?.resolve(false);
});
