/// <reference types="vite/client" />
import React,{useEffect,useMemo,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {TooltipProvider,ShellThemeToggle,NativeSelect} from '@vxture/design-system';
import {Compass} from '@phosphor-icons/react';
import seed from '../../../../contracts/examples/spatial-registration-campus.json';
import {RegistrationWorkbench,type PlanBuilding} from '../layout/registration-workbench';
import type {RegistrationInput} from '../layout/registration-preview-data';
import type {PreviewGeometry,XYZ} from '../layout/geometry-preview-data';
import '../layout/globals.css';
import './preview.css';

// This entry is only served by Vite dev and is not a production build input.
if(!import.meta.env.DEV)throw Error('registration_preview_development_only');
const buildings:PlanBuilding[]=[
 {id:'a',name:'A 区',x:12,y:8,width:22,depth:18,height:9},
 {id:'b',name:'B 区',x:50,y:8,width:32,depth:18,height:7},
 {id:'c',name:'C 区',x:12,y:40,width:26,depth:14,height:8},
 {id:'d',name:'D 区',x:58,y:38,width:32,depth:16,height:11},
];

function geometry(dark:boolean):PreviewGeometry{
 const points:XYZ[]=[],colors:XYZ[]=[];
 const ground:XYZ=dark?[110,129,146]:[174,189,199],wall:XYZ=dark?[105,164,213]:[67,121,167],roof:XYZ=dark?[150,192,219]:[108,153,183];
 function add(x:number,y:number,z:number,color:XYZ){points.push([x,y,z]);colors.push(color);}
 for(let x=0;x<=100;x+=2)for(let y=0;y<=60;y+=2)add(x,y,0,ground);
 for(const b of buildings){
  for(let x=b.x;x<=b.x+b.width;x+=.8)for(let y=b.y;y<=b.y+b.depth;y+=.8)add(x,y,b.height,roof);
  for(let z=0;z<=b.height;z+=.8){
   for(let x=b.x;x<=b.x+b.width;x+=.8){add(x,b.y,z,wall);add(x,b.y+b.depth,z,wall);}
   for(let y=b.y;y<=b.y+b.depth;y+=.8){add(b.x,y,z,wall);add(b.x+b.width,y,z,wall);}
  }
 }
 return {point_count:points.length,bounds:[[0,0,0],[100,60,11]],points,colors,sampling:{method:'synthetic_surfaces',stride:1,limit:10000,count:points.length},unit:'m',frame_id:'model-local',axes:['right','forward','up'],appearance:'synthetic'};
}

function Preview(){
 const [theme,setTheme]=useState<'light'|'dark'>('light'),[sample,setSample]=useState('within');
 const [editedInput,setEditedInput]=useState<RegistrationInput|null>(null);
 useEffect(()=>{document.documentElement.classList.toggle('dark',theme==='dark');},[theme]);
 const input=useMemo(()=>{const doc=structuredClone(seed) as RegistrationInput;if(sample==='exceeded')doc.controls[5].target_m[0]+=.32;return doc;},[sample]);
 const dark=theme==='dark';
 const cloud=useMemo(()=>geometry(dark),[dark]);
 return <div className="registration-preview-page"><header className="registration-preview-bar"><div><Compass size={20}/><span>CoSpace</span><span className="registration-preview-separator">/</span><span>空间关联</span><span className="registration-preview-separator">/</span><strong>空间基准</strong></div><div><span className="registration-preview-tag">B07a · 交互预览</span><ShellThemeToggle currentTheme={theme} onThemeChange={setTheme} buttonLabel="切换主题"/></div></header><main><div className="registration-preview-notice"><span><i/>合成园区算例 · 不对应真实场地{editedInput?' · 本地修改':''}</span><NativeSelect aria-label="切换检查算例" value={sample} onChange={e=>{setSample(e.target.value);setEditedInput(null);}}><option value="within">检查在门限内</option><option value="exceeded">K3 水平偏差超限</option></NativeSelect></div><RegistrationWorkbench input={editedInput??input} geometry={cloud} buildings={buildings} onPreviewChange={setEditedInput}/></main></div>;
}
createRoot(document.getElementById('root')!).render(<TooltipProvider><Preview/></TooltipProvider>);
