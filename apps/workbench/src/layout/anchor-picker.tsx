import type {GeometryFocus,GeometryMarker} from './geometry-preview-canvas';
import React,{lazy,Suspense,useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {readPreview,validatePreview,type PreviewGeometry,type XYZ} from './geometry-preview-data';
import './geometry-preview.css';
const Canvas=lazy(()=>import('./geometry-preview-canvas'));
export function AnchorPicker({endpoint,space,candidate,manifest,onPick,disabled,markers,selected,onSelect,focus,editing,anchor}:{endpoint:string;space:string;candidate:string;manifest:string;onPick:(index:number)=>void;disabled:boolean;markers?:GeometryMarker[];selected?:string;onSelect?:(id:string)=>void;focus?:GeometryFocus;editing?:boolean;anchor?:XYZ}){
 const [data,setData]=useState<PreviewGeometry|null>(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{const controller=new AbortController();setData(null);setError('');
  readPreview(`${endpoint}/candidates/${candidate}/api/anchor-preview`,controller.signal).then(v=>validatePreview(v,{space,candidate,manifest})).then(v=>{if(!controller.signal.aborted)setData(v);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[endpoint,space,candidate,manifest,revision]);
 return <section aria-label="三维画面选点" className="geometry-preview"><h4>三维模型</h4><p>{editing?'双击可见点更新对象位置，锚点由服务端核对。':'点击对象标记查看属性；从清单可定位到模型。'}</p>
 {error&&<p role="alert">{error}<Button type="button" variant="ghost" onClick={()=>setRevision(v=>v+1)}>重新加载画面</Button></p>}
 {!data&&!error&&<p role="status">正在读取固定模型…</p>}
 {data&&<Suspense fallback={<p>正在加载画面…</p>}><Canvas data={data} onPick={disabled?undefined:onPick} markers={markers} selected={selected} onSelect={onSelect} focus={focus} anchor={anchor}/></Suspense>}
 {data&&<p>显示 {data.sampling.count.toLocaleString()} / {data.point_count.toLocaleString()} 个模型点 · 抽样可能遗漏细节 · {data.frame_id}</p>}
 </section>;
}
