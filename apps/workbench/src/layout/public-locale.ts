import {useSyncExternalStore} from 'react';
const event='cospace:public-locale';
const subscribe=(fn:()=>void)=>{window.addEventListener(event,fn);window.addEventListener('storage',fn);return()=>{window.removeEventListener(event,fn);window.removeEventListener('storage',fn);};};
const snapshot=()=>{try{return localStorage.getItem('cospace.public.locale')==='en'?'en':'zh-CN';}catch{return 'zh-CN';}};
export function usePublicLocale(){return useSyncExternalStore(subscribe,snapshot);}
export function setPublicLocale(locale:string){try{localStorage.setItem('cospace.public.locale',locale);}catch{}window.dispatchEvent(new Event(event));}
