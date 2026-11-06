import React,{useEffect,useRef,useState} from 'react';
import {Button,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '@vxture/design-system';
import {readPreview} from './geometry-preview-data';
import {processSourceFrame,supportsRGBD,validateRGBDDirectory,validateRGBDImage,type RGBDDirectory,type RGBDImage,type RGBDBinding} from './rgbd-preview-data';
import type {ProcessFrame} from './build-process-data';
import './rgbd-preview.css';

function Trajectory({data,index}:{data:RGBDDirectory;index:number}){
 const raw=data.frames.filter(f=>f.pose).map(f=>[f.pose![0][3],f.pose![2][3]]),magnitude=Math.max(1,...raw.flat().map(Math.abs)),poses=raw.map(p=>p.map(v=>v/magnitude)),xs=poses.map(p=>p[0]),zs=poses.map(p=>p[1]);
 const minX=Math.min(...xs),minZ=Math.min(...zs),scale=190/Math.max(Math.max(...xs)-minX,Math.max(...zs)-minZ,.001);
 const xy=(p:number[])=>[25+(p[0]-minX)*scale,215-(p[1]-minZ)*scale],points=poses.map(xy),current=points[index];
 return <details className="rgbd-trajectory"><summary>已有估计相机轨迹 · {poses.length} 帧</summary><svg viewBox="0 0 240 240" role="img" aria-label="局部坐标X/Z轨迹投影"><polyline points={points.map(p=>p.join(',')).join(' ')} fill="none" stroke="currentColor" strokeWidth="1.5"/>{current&&<circle cx={current[0]} cy={current[1]} r="4" fill="var(--primary)"/>}<text x="8" y="234">X → · Z ↑</text></svg><p>首深度相机局部坐标 · X右／Y下／Z前。X/Z投影不是地面平面，估计轨迹不是导航路线。</p></details>;
}

function Images({data,onError}:{data:RGBDImage;onError:()=>void}){return <><div className="rgbd-image-grid"><figure><img src={data.rgb_png} onError={onError} width="320" height="240" alt={`第${data.frame.index+1}帧彩色图`}/><figcaption>彩色 · 原传感器画幅</figcaption></figure><figure><img src={data.depth_png} onError={onError} width="320" height="240" alt={`第${data.frame.index+1}帧深度图`}/><figcaption>深度 · 无效区域透明</figcaption></figure></div><div className="rgbd-depth-legend"><span>0 m</span><i/><span>10 m</span></div><p>固定米制色标 · 原图640×480，显示320×240 · 深度有效像素 {data.valid_depth_pixels.toLocaleString()} / 307,200</p></>;}

export function RGBDPreview({endpoint,binding,process,compact=false}:{endpoint:string;binding:RGBDBinding;process?:ProcessFrame;compact?:boolean}){
 const [directory,setDirectory]=useState<RGBDDirectory|null>(null),[image,setImage]=useState<RGBDImage|null>(null),[selected,setSelected]=useState(0),[error,setError]=useState(''),[frameError,setFrameError]=useState(''),[busy,setBusy]=useState(true),[retry,setRetry]=useState(0),[large,setLarge]=useState(false);
 const generation=useRef(0),current=useRef<string>(''),[imageKey,setImageKey]=useState('');
 const processKey=process?JSON.stringify(process):'',bindingKey=JSON.stringify(binding);
 current.current=bindingKey+'|'+processKey+'|'+selected+'|'+retry;
 useEffect(()=>{setSelected(0);setLarge(false);},[bindingKey]);
 useEffect(()=>{const controller=new AbortController();setDirectory(null);setImage(null);setError('');setBusy(true);
  void(async()=>{const cap=await readPreview(`${endpoint}/api/input-uploads?${new URLSearchParams({space_id:binding.space})}`,controller.signal);if(!supportsRGBD(cap))throw Error('当前服务未开放RGB-D原资料预览。');
   const d=validateRGBDDirectory(await readPreview(`${endpoint}/api/inputs/${encodeURIComponent(binding.input)}/rgbd-preview?${new URLSearchParams({space_id:binding.space})}`,controller.signal,1024*1024),binding);
   if(!controller.signal.aborted)setDirectory(d);
  })().catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'RGB-D资料暂不可用。');}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
  return()=>controller.abort();
 },[endpoint,bindingKey,retry]);
 let index=selected,mappingError='';
 if(process&&directory){try{index=processSourceFrame(directory,process);}catch(e){mappingError=e instanceof Error?e.message:'来源不一致。';}}
 const displayKey=current.current+'|'+index;
 useEffect(()=>{const controller=new AbortController(),run=++generation.current;setImage(null);setFrameError('');
  if(!directory||mappingError)return()=>controller.abort();
  const key=current.current;let timer:ReturnType<typeof setTimeout>;
  timer=setTimeout(()=>{void(async()=>{const value=await readPreview(`${endpoint}/api/inputs/${encodeURIComponent(binding.input)}/rgbd-preview/frame?${new URLSearchParams({space_id:binding.space,frame_index:String(index)})}`,controller.signal);const checked=validateRGBDImage(value,directory,index);if(!controller.signal.aborted&&run===generation.current&&current.current===key){setImage(checked);setImageKey(key+'|'+index);}})().catch(e=>{if(!controller.signal.aborted&&run===generation.current&&current.current===key)setFrameError(e instanceof Error?e.message:'源画面不可用。');});},100);
  return()=>{controller.abort();clearTimeout(timer);generation.current++;};
 },[endpoint,directory,index,mappingError,displayKey,retry]);
 const frame=directory?.frames[index],ready=image&&imageKey===displayKey&&image.frame.index===index&&!mappingError;
 const content=<>{busy&&<p role="status">正在核对RGB-D资料来源…</p>}{(error||mappingError||frameError)&&<div role="alert"><p>源画面不可用。{error||mappingError||frameError}</p><Button size="sm" variant="outline" onClick={()=>setRetry(v=>v+1)}>重试源画面</Button></div>}{directory&&<>
  {!compact&&<p>{directory.input_frames} 帧资料 · {directory.pose_frames} 帧已有估计位姿 · {directory.input_frames-directory.pose_frames} 帧无位姿</p>}
  {!process&&<div className="rgbd-controls"><Button size="sm" variant="ghost" aria-label="上一资料帧" disabled={index===0} onClick={()=>setSelected(v=>v-1)}>上一帧</Button><input aria-label="RGB-D资料帧" type="range" min="0" max={directory.input_frames-1} step="1" value={index} onChange={e=>setSelected(Number(e.target.value))}/><Button size="sm" variant="ghost" aria-label="下一资料帧" disabled={index===directory.input_frames-1} onClick={()=>setSelected(v=>v+1)}>下一帧</Button></div>}
  {frame&&<div className="rgbd-frame-info"><span>源帧 {index+1} / {directory.input_frames}</span><span>{frame.relative_time_us===null?'相对时间未知':`相对源时间 ${(frame.relative_time_us/1e6).toFixed(3)}s`}</span><span>{frame.pair_delta_us===null?'配对时差未记录':`RGB−深度 ${(frame.pair_delta_us/1000).toFixed(2)}ms`}</span><span>{process?'本任务已保存帧':frame.pose?'已有位姿已提供':'无已有位姿'}</span></div>}
  {ready?<Images data={image} onError={()=>{setImage(null);setFrameError('图像解码失败，请重新核查来源。');}}/>:!error&&!frameError&&!mappingError&&<div className="rgbd-loading" role="status">正在读取当前帧…</div>}
  {!compact&&<Trajectory data={directory} index={index}/>}
  <p>预录RGB-D · UTC未核验 · 仅核验当前图像对，完整预检另行执行。彩色与深度未在此对齐叠加。</p>
 </>}</>;
 return <section className={`rgbd-preview${compact?' rgbd-preview-compact':''}`} aria-label="RGB-D资料预览" data-source-frame={ready?index:''} data-source-key={ready?image.frame.depth_sha256:''}>
  {!compact&&<div className="rgbd-preview-toolbar"><Button size="sm" variant="ghost" onClick={()=>setLarge(true)}>放大RGB-D预览</Button></div>}{!large&&content}
  <Dialog open={large} onOpenChange={setLarge}><DialogContent className="rgbd-preview-dialog"><DialogHeader><DialogTitle>RGB-D资料预览</DialogTitle><DialogDescription>原始观测与已有估计轨迹，仅供资料核对。</DialogDescription></DialogHeader>{large&&content}</DialogContent></Dialog>
 </section>;
}

export function BuildSource({endpoint,binding,process}:{endpoint:string;binding:RGBDBinding;process:ProcessFrame}){
 const [available,setAvailable]=useState(false),[open,setOpen]=useState(false);
 const key=JSON.stringify(binding);
 useEffect(()=>{const controller=new AbortController();setAvailable(false);setOpen(false);
  void readPreview(`${endpoint}/api/input-uploads?${new URLSearchParams({space_id:binding.space})}`,controller.signal).then(cap=>{if(!controller.signal.aborted)setAvailable(supportsRGBD(cap));}).catch(()=>{});return()=>controller.abort();
 },[endpoint,key]);
 return available?<><Button size="sm" variant="ghost" className="build-source-toggle" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'关闭源画面':'源画面'}</Button>{open&&<aside className="build-source-panel" aria-label="当前构建帧源画面"><div className="rgbd-source-heading"><span>当前帧来源</span><Button size="sm" variant="ghost" aria-label="关闭当前源画面" onClick={()=>setOpen(false)}>关闭</Button></div><RGBDPreview endpoint={endpoint} binding={binding} process={process} compact/></aside>}</>:null;
}
