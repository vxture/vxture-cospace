import React,{useId,useState} from 'react';
import spaceArt from './space.svg?raw';
import './scene-cover.css';

// Only pass overview URLs from the authorized scene configuration.
export function SceneCover({overviewUrl,name}:{overviewUrl?:string;name:string}){
 const id=useId().replace(/[^a-zA-Z0-9_-]/g,''),[failed,setFailed]=useState('');
 const available=overviewUrl&&failed!==overviewUrl;
 return <div className="scene-cover">{available?<img src={overviewUrl} alt={`${name}场景概览`} loading="lazy" onError={()=>setFailed(overviewUrl)}/>:<div className="scene-cover-illustration" aria-hidden="true" dangerouslySetInnerHTML={{__html:spaceArt.replace(/id="([^"]+)"/g,`id="${id}-$1"`).replace(/url\(#([^)]+)\)/g,`url(#${id}-$1)`)}}/>}<span className="scene-cover-caption">{available?'场景概览':'空间示意'}</span></div>;
}
