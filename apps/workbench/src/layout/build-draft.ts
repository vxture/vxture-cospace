import {useEffect,useState} from 'react';
import type {BuildInfo} from './build-context';

type BuildDraft={createdAt:string;info:BuildInfo};
export const emptyBuildInfo:BuildInfo={name:'',purpose:'',changes:''};
function readDraft(key:string):BuildDraft|null{
 try{
  const value=JSON.parse(localStorage.getItem(key)||'null');
  if(!value||typeof value.createdAt!=='string'||!Number.isFinite(Date.parse(value.createdAt)))return null;
  return {createdAt:value.createdAt,info:{name:typeof value.info?.name==='string'?value.info.name:'',purpose:typeof value.info?.purpose==='string'?value.info.purpose:'',changes:typeof value.info?.changes==='string'?value.info.changes:''}};
 }catch{return null;}
}
export function useBuildDraft(scope:string,space:string,active:boolean){
 const key=JSON.stringify(['cospace:build-draft',scope,space]);
 const [entry,setEntry]=useState(()=>({key,draft:readDraft(key)}));
 const draft=entry.key===key?entry.draft:null;
 useEffect(()=>{
  let next=readDraft(key);
  if(!next&&active&&space){
   next={createdAt:new Date().toISOString(),info:emptyBuildInfo};
   try{localStorage.setItem(key,JSON.stringify(next));}catch{/* The current draft remains available in memory. */}
  }
  setEntry({key,draft:next});
 },[key,active,space]);
 function update(info:BuildInfo){
  if(!draft)return;
  const next={...draft,info};
  setEntry({key,draft:next});
  try{localStorage.setItem(key,JSON.stringify(next));}catch{/* Continue in memory. */}
 }
 function clear(){
  setEntry({key,draft:null});
  try{localStorage.removeItem(key);}catch{/* The current draft was cleared in memory. */}
 }
 return {draft,update,clear};
}
