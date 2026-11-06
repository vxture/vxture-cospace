import React,{useEffect,useState} from 'react';
import {NativeSelect} from '@vxture/design-system';
import {useRecordNavigation} from './record-navigation';
import {usePlatformSession} from './platform-auth';
import {useEmbeddedScene} from './module-workspace';

export function SpaceContext({endpoint}:{endpoint:string}){
 const embedded=useEmbeddedScene();
 const target=useRecordNavigation();const platform=usePlatformSession();
 const [spaces,setSpaces]=useState<{id:string;name:string;project_id:string}[]>([]),[projects,setProjects]=useState<{id:string;name:string}[]>([]),[error,setError]=useState('');
 useEffect(()=>{if(embedded)return;let active=true;Promise.all([fetch(`${endpoint}/api/spaces`),fetch(`${endpoint}/api/projects`)]).then(async ([s,p])=>{if(!s.ok||!p.ok)throw Error('空间目录无法读取');const [ss,pp]=await Promise.all([s.json(),p.json()]);if(active){setSpaces(ss.spaces);setProjects(pp.projects);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[endpoint,embedded]);
 if(embedded)return null;
 return <div className="flex flex-col gap-sm"><NativeSelect aria-label="当前工作空间" value={target.space} onChange={e=>{const route=location.hash.slice(1).split('?')[0];location.hash=route+(e.target.value?'?'+new URLSearchParams({space:e.target.value}):'');}}><option value="" disabled={!!platform}>{platform?'请选择授权空间':'历史未关联记录'}</option>{spaces.map(s=><option key={s.id} value={s.id}>{projects.find(p=>p.id===s.project_id)?.name} / {s.name}</option>)}</NativeSelect>{target.space&&!spaces.some(s=>s.id===target.space)&&<p role="alert">所选空间无权访问、不存在或尚未读取。</p>}{error&&<p role="alert">{error}</p>}<p className="text-label-small text-muted-foreground">{target.space?'当前操作仅作用于所选空间。':platform?'请先选择有权限的空间。':'此范围保留历史记录；请先选择空间，再登记新资料。'}</p></div>;
}
