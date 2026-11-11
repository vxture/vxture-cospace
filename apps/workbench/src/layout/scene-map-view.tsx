import React,{Suspense,useState} from 'react';
import {readMapPreferences,mapPreferenceKey} from './map-preferences';
import type {SceneSpace} from './scene-directory';
import './scene-map.css';
const AmapView=React.lazy(()=>import('./scene-map').then(m=>({default:m.AmapSceneMap})));
const Globe=React.lazy(()=>import('./scene-globe').then(m=>({default:m.SceneGlobe})));
type Props={spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void};
export function SceneMap(props:Props){
 const [mode,setMode]=useState(readMapPreferences().viewMode);
 function changeView(value:'2D'|'3D'){try{localStorage.setItem(mapPreferenceKey,JSON.stringify({...readMapPreferences(),viewMode:value}));}catch{/* Current session remains usable. */}setMode(value);}
 return <div className="scene-geographic-view"><Suspense fallback={<div role="status">正在加载地图引擎…</div>}>{mode==='3D'?<Globe {...props} onViewChange={changeView}/>:<AmapView {...props} onViewChange={changeView}/>}</Suspense></div>;
}
