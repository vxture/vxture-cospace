import React,{Suspense,useState} from 'react';
import {SegmentedControl} from '@vxture/design-system';
import type {SceneSpace} from './scene-directory';
import './scene-map.css';
const Map=React.lazy(()=>import('./scene-map').then(m=>({default:m.AmapSceneMap})));
const Globe=React.lazy(()=>import('./scene-globe').then(m=>({default:m.SceneGlobe})));
type Props={spaces:SceneSpace[];loading:boolean;error:string;onBack:()=>void;onRefresh:()=>void};
export function SceneMap(props:Props){
 const [mode,setMode]=useState(()=>{try{return localStorage.getItem('cospace.geo-mode')==='map'?'map':'globe';}catch{return 'globe';}});
 return <div className="scene-geographic-view"><Suspense fallback={<div role="status">正在加载地图引擎…</div>}>{mode==='globe'?<Globe {...props}/>:<Map {...props}/>}</Suspense><div className="scene-geographic-switch"><SegmentedControl ariaLabel="地理视图" size="md" value={mode} onChange={value=>{setMode(value);try{localStorage.setItem('cospace.geo-mode',value);}catch{/* Session selection remains usable. */}}} items={[{value:'map',label:'二维地图'},{value:'globe',label:'三维地球'}]}/></div></div>;
}
