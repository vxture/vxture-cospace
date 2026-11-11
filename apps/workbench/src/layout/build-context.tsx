import React,{useEffect,useState} from 'react';
import {Button,Textarea,useToast} from '@vxture/design-system';
import {FileText,PencilSimple,FloppyDisk,X} from '@phosphor-icons/react';
import {useUnsavedNavigation} from './unsaved-navigation';
export type BuildInfo={name:string;purpose:string;changes:string};
export function BuildSceneLink({selected,onSelect}:{selected:boolean;onSelect:()=>void}){
 return <Button variant={selected?'secondary':'ghost'} className="build-scene-link" aria-current={selected?'page':undefined} onClick={onSelect}><FileText size={18}/>基本信息</Button>;
}
const descriptionOf=(value:BuildInfo)=>value.purpose||[value.name,value.changes].filter(Boolean).join('；');
export function BuildContext({endpoint,space,draft,value,onChange,jobId,revision=0,onSaved}:{endpoint:string;space:string;draft:boolean;value:BuildInfo;onChange:(value:BuildInfo)=>void;jobId?:string;revision?:number;onSaved:()=>void}){
 const {toast}=useToast();
 const [editing,setEditing]=useState(false),[form,setForm]=useState({...value,purpose:descriptionOf(value)}),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{setEditing(false);setForm({...value,purpose:descriptionOf(value)});setError('');},[jobId,space,draft]);
 const dirty=editing&&form.purpose!==descriptionOf(value);
 async function save(){if(busy)return false;setBusy(true);setError('');try{
  if(draft){onChange(form);toast({title:'构建说明已暂存',description:'开始构建时一并保存。',tone:'success'});}
  else{const response=await fetch(`${endpoint}/api/build-info`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:space,candidate_id:jobId,expected_revision:revision,build_info:form})});const result=await response.json();if(!response.ok)throw Error(result.detail==='build_info_revision_changed'?'说明已被其他操作更新，请取消编辑后重新读取。':'保存构建说明失败，请重试。');if(result.job_id!==jobId||result.space_id!==space)throw Error('返回记录与当前构建不一致。');onSaved();toast({title:'构建说明已保存',tone:'success'});}
  setEditing(false);return true;
 }catch(e){setError(e instanceof Error?e.message:'保存失败');return false;}finally{setBusy(false);}}
 useUnsavedNavigation(dirty,'构建说明',{discard:()=>{setForm({...value,purpose:descriptionOf(value)});setEditing(false);},save,canSave:!busy});
 return <div className="build-title-description" role="group" aria-label="构建说明">{editing?<><Textarea aria-label="构建说明" value={form.purpose} maxLength={500} placeholder="本次构建的用途或变更内容" disabled={busy} onChange={e=>setForm({...form,purpose:e.target.value})}/><Button variant="ghost" size="sm" title="保存说明" aria-label="保存说明" disabled={busy} onClick={()=>void save()}><FloppyDisk size={16}/></Button><Button variant="ghost" size="sm" title="取消编辑" aria-label="取消编辑" disabled={busy} onClick={()=>{setForm({...value,purpose:descriptionOf(value)});setEditing(false);setError('');}}><X size={16}/></Button></>:<><span className="build-title-description-text">{descriptionOf(value)||'添加构建说明'}</span><Button variant="ghost" size="sm" title="编辑构建说明" aria-label="编辑构建说明" onClick={()=>{setForm({...value,purpose:descriptionOf(value)});setEditing(true);}}><PencilSimple size={14}/></Button></>}{error&&<span role="alert">{error}</span>}</div>;
}
