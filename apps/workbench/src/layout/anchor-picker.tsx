import React,{lazy,Suspense,useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {readPreview,validatePreview,type PreviewGeometry} from './geometry-preview-data';
import './geometry-preview.css';
const Canvas=lazy(()=>import('./geometry-preview-canvas'));
export function AnchorPicker({endpoint,space,candidate,manifest,onPick,disabled}:{endpoint:string;space:string;candidate:string;manifest:string;onPick:(index:number)=>void;disabled:boolean}){
 const [data,setData]=useState<PreviewGeometry|null>(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{const controller=new AbortController();setData(null);setError('');
  readPreview(`${endpoint}/candidates/${candidate}/api/anchor-preview`,controller.signal).then(v=>validatePreview(v,{space,candidate,manifest})).then(v=>{if(!controller.signal.aborted)setData(v);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[endpoint,space,candidate,manifest,revision]);
 return <section aria-label="三维画面选点" className="geometry-preview"><h4>在三维画面中选择位置</h4><p>双击可见点选取位置；拖动旋转、滚轮缩放。位置由服务端重新核对，选点不确认对象类型或现场语义。</p>
 {error&&<p role="alert">{error}<Button type="button" variant="ghost" onClick={()=>setRevision(v=>v+1)}>重新加载画面</Button></p>}
 {!data&&!error&&<p role="status">正在读取固定模型…</p>}
 {data&&<Suspense fallback={<p>正在加载画面…</p>}><Canvas data={data} onPick={disabled?undefined:onPick}/></Suspense>}
 {data&&<p>显示 {data.sampling.count.toLocaleString()} / {data.point_count.toLocaleString()} 个模型点 · 抽样可能遗漏细节 · {data.frame_id}</p>}
 </section>;
}
