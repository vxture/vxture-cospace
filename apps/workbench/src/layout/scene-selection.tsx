import {legacyExampleHref,associationExample} from './association-examples';
import React,{createContext,useContext,useLayoutEffect,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {usePlatformSession} from './platform-auth';
import {sessionScopeKey} from './session-continuity';
import {preferredScene,sceneContextHref,scenePreferenceKey} from './scene-preference';

const SelectedScene=createContext('');
const SceneControls=createContext({selectScene:(_id:string)=>{},mapActive:false,setMapActive:(_active:boolean)=>{}});
export const useSceneControls=()=>useContext(SceneControls);
export const useSelectedScene=()=>useContext(SelectedScene);
function read(key:string){try{return localStorage.getItem(key)||'';}catch{return '';}}
export function SceneSelection({children}:{children:React.ReactNode}){
 const scope=sessionScopeKey(usePlatformSession())||'engineering-preview';
 return <ScopedSceneSelection key={scope} scope={scope}>{children}</ScopedSceneSelection>;
}
function ScopedSceneSelection({scope,children}:{scope:string;children:React.ReactNode}){
 const key=scenePreferenceKey(scope),location=useLocation(),navigate=useNavigate();
 const [remembered,setRemembered]=useState(()=>associationExample(read(key))?'':read(key));
 const [mapActive,setMapActive]=useState(false);
 function selectScene(id:string){setRemembered(id);try{if(id)localStorage.setItem(key,id);else localStorage.removeItem(key);}catch{/* Selection works without storage. */}}
 const legacy=legacyExampleHref(location.pathname+location.search);
 const explicit=legacy?'':new URLSearchParams(location.search).get('space');
 const scene=preferredScene(explicit,remembered);
 useLayoutEffect(()=>{
  if(explicit===null)return;
  setRemembered(explicit);
  try{if(explicit)localStorage.setItem(key,explicit);else localStorage.removeItem(key);}catch{/* The in-memory selection still works when storage is blocked. */}
 },[explicit,key]);
 useLayoutEffect(()=>{
  if(legacy){void navigate(legacy,{replace:true});return;}
  const href=location.pathname+location.search,next=sceneContextHref(href,scene);
  if(next!==href)void navigate(next,{replace:true});
 },[location.pathname,location.search,scene,navigate,legacy]);
 return <SceneControls.Provider value={{selectScene,mapActive,setMapActive}}><SelectedScene.Provider value={scene}>{children}</SelectedScene.Provider></SceneControls.Provider>;
}
