import React,{createContext,useContext,useEffect,useLayoutEffect,useRef,useState,useCallback} from 'react';
import {Button,ShellDock} from '@vxture/design-system';
import {Sparkle,CaretDoubleLeft,CaretDoubleRight,CornersOut,CornersIn,X} from '@phosphor-icons/react';
import {AssistantConversation} from './assistant-conversation';
import {appNavigate} from './app-router';
import {useSceneDirectory} from './use-scene-directory';
import {usePlatformSession} from './platform-auth';
import type {AssistantReport} from './assistant-contract';
import './workspace-assistant.css';

type Published={scope:string;owner:symbol;report:AssistantReport};
const Assistant=createContext<{scope:string;open:boolean;toggle:()=>void;publish:(value:Published|null,owner:symbol)=>void}|null>(null);
export function useAssistantReport(report:AssistantReport){
 const context=useContext(Assistant),latest=useRef(report);latest.current=report;
 const owner=useRef(Symbol('assistant-report')).current;
 const signature=JSON.stringify({...report,tasks:report.tasks.map(({run,...task})=>task)});
 const publish=context?.publish,scope=context?.scope;
 useLayoutEffect(()=>{
  if(!publish||!scope)return;
  const current=latest.current;
  publish({scope,owner,report:{...current,tasks:current.tasks.map(task=>({...task,run:()=>latest.current.tasks.find(t=>t.id===task.id)?.run()}))}},owner);
  return()=>publish(null,owner);
 },[publish,scope,owner,signature]);
}
export function WorkspaceAssistant({scope,route,scene,children,header}:{scope:string;route:string;scene:string;children:React.ReactNode;header:(controls:{open:boolean;toggle:()=>void})=>React.ReactNode}){
 const [open,setOpen]=useState(false),[mode,setMode]=useState<'narrow'|'wide'|'full'>('narrow'),[published,setPublished]=useState<Published|null>(null);
 const toggle=useCallback(()=>setOpen(value=>!value),[]);
 const publish=useCallback((value:Published|null,owner:symbol)=>setPublished(current=>value|| (current?.owner===owner?null:current)),[]);
 const report=published?.scope===scope?published.report:null;
 const close=()=>{setOpen(false);requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('.platform-header-actions button[aria-label="智能助手"]')?.focus());};
 useEffect(()=>{if(!open)return;const key=(event:KeyboardEvent)=>{if(event.key!=='Escape'||event.defaultPrevented||document.querySelector('[role="dialog"],[role="alertdialog"],[role="menu"]'))return;event.preventDefault();if(mode==='full')setMode('narrow');else close();};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[open,mode]);
 return <Assistant.Provider value={{scope,open,toggle,publish}}>{header({open,toggle})}<div className="workspace-with-assistant"><div className="workspace-business-content" inert={open&&mode==='full'}>{children}</div>{open&&<div id="workspace-assistant" role="region" aria-label="智能助手面板" className={`workspace-assistant-dock workspace-assistant-${mode}`}>
  <ShellDock mode={mode} className="workspace-assistant-panel"><header className="workspace-assistant-heading"><Sparkle size={18}/><h2>智能助手</h2><div>
   <Button variant="ghost" size="icon-xl" aria-label={mode==='wide'?'收窄助手':'加宽助手'} title={mode==='wide'?'切换为窄模式':'切换为宽模式'} aria-pressed={mode==='wide'} onClick={()=>setMode(mode==='wide'?'narrow':'wide')}>{mode==='wide'?<CaretDoubleRight size={18}/>:<CaretDoubleLeft size={18}/>}</Button>
   <Button variant="ghost" size="icon-xl" aria-label={mode==='full'?'退出助手全屏':'全屏助手'} aria-pressed={mode==='full'} onClick={()=>setMode(mode==='full'?'narrow':'full')}>{mode==='full'?<CornersIn size={16}/>:<CornersOut size={16}/>}</Button>
   <Button variant="ghost" size="icon-xl" aria-label="关闭智能助手" onClick={close}><X size={16}/></Button>
  </div></header><AssistantTasks key={scope} report={report} route={route} scene={scene} onSelect={()=>{setMode('narrow');if(innerWidth<1200)setOpen(false);}}/></ShellDock>
 </div>}</div></Assistant.Provider>;
}
function AssistantTasks({report,route,scene,onSelect}:{report:AssistantReport|null;route:string;scene:string;onSelect:()=>void}){
 const directory=useSceneDirectory(),session=usePlatformSession();
 const current=directory.spaces.find(item=>item.id===scene);
 const allowed=(cap:string)=>!!current&&(!session||!!current.capabilities?.includes(cap));
 const go=(path:string)=>appNavigate(path);
 const params=new URLSearchParams(location.search),section=params.get('space')&&params.get('tab')?params.get('tab')!:params.get('section')||'directory';
 const link=(route:string,tab:string)=>`/${route}?${new URLSearchParams({space:scene,tab})}`;
 const fallback:AssistantReport={title:({services:'空间服务检查',data:'资料检查',ontology:'规则检查',build:'构建检查',association:'关联检查',delivery:'发布检查'} as Record<string,string>)[route]||'账户与工作区',status:directory.loading?'loading':directory.error?'error':'ready',note:directory.error||undefined,tasks:[]};
 if(route==='services'){
  if(section==='feedback')fallback.note='态势反馈接入尚未开放，暂无可检查的上报任务。';
  else if(section==='recipients')fallback.note='正在读取设备登记信息。';
  else {
   const available=scene?(current?[current]:[]):directory.spaces;
   for(const item of available.slice(0,3)){
    const versions=(item.publications||[]).filter(p=>!p.lifecycle_state||p.lifecycle_state==='active');
    const release=params.get('publication')?versions.find(v=>v.id===params.get('publication')):versions[0];
    if(release)fallback.tasks.push({id:item.id,title:section==='offline'?'核对离线交付':'核对服务接入',evidence:`${item.name} · ${release.display_code||release.version_code||'固定发布'}`,label:section==='offline'?'进入离线交付':'进入在线服务',run:()=>go('/services?'+new URLSearchParams({section:section==='offline'?'offline':'online',space:item.id,publication:release.id,tab:section==='offline'?'offline':'online'}))});
   }
   if(!fallback.tasks.length)fallback.note='当前授权范围没有可用的固定发布。';
  }
 }else if(['settings','members','identity','account'].includes(route)){
  fallback.status='ready';fallback.note=undefined;
  fallback.tasks=[{id:'account',title:'核对账号与组织',evidence:'账号与组织信息由平台统一维护。',label:'个人信息',run:()=>go('/account')},{id:'access',title:'核对工作区授权',evidence:'场景操作以当前工作区的实际授权为准。',label:'工作区与授权',run:()=>go('/settings')}];
 }else if(!report){
  fallback.note=!scene?'请先选择可访问的场景。':!current?'当前场景不可访问，请先选择已授权场景。':'当前工作面尚无可执行任务，请核对场景授权或等待页面读取完成。';
  if(route==='data'&&allowed('data.manage'))fallback.tasks.push({id:'inputs',title:'检查场景资料',evidence:'进入当前场景的资料工作面，核对登记与预检记录。',label:'进入场景资料',run:()=>go(link('data','inputs'))});
 }
 if(directory.error&&!['settings','members','identity','account'].includes(route))fallback.note=directory.error;
 const value=report||fallback;
 return <AssistantConversation report={value} onSelect={onSelect}/>;
}
