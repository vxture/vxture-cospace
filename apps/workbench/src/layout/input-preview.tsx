import React,{useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {readUploadCapabilities} from './input-format';
import {GeometryPreview} from './geometry-preview';
import {readPreview,validatePreview,PreviewResponse} from './geometry-preview-data';
import {RGBDPreview} from './rgbd-preview';
type Input={id:string;format:string;cloud_sha256?:string;snapshot_sha256?:string;tracking_sha256?:string};
export function InputPreview({endpoint,space,input}:{endpoint:string;space:string;input:Input}){
 if(input.format==='nyu_rgbd_with_existing_poses')return <RGBDInput key={space+input.id} endpoint={endpoint} space={space} input={input}/>;
 return <PointcloudInput endpoint={endpoint} space={space} input={input}/>;
}
function RGBDInput({endpoint,space,input}:{endpoint:string;space:string;input:Input}){
 const [open,setOpen]=useState(false);
 return <section className="data-detail-section" aria-label="资料内容预览"><div className="flex items-center justify-between gap-sm"><h3>内容预览</h3><Button type="button" size="sm" variant="ghost" onClick={()=>setOpen(v=>!v)}>{open?'关闭RGB-D预览':'查看RGB-D'}</Button></div>{open?<RGBDPreview endpoint={endpoint} binding={{space,input:input.id,snapshot:input.snapshot_sha256,tracking:input.tracking_sha256}}/>:<p>按需查看彩色、深度与已有估计轨迹。</p>}</section>;
}
function PointcloudInput({endpoint,space,input}:{endpoint:string;space:string;input:Input}){
 const [open,setOpen]=useState(false),[data,setData]=useState<PreviewResponse|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{setOpen(false);setData(null);setError('');},[space,input.id]);
 useEffect(()=>{setData(null);setError('');if(!open)return;const controller=new AbortController();setBusy(true);
  void(async()=>{const cap=await readUploadCapabilities(endpoint,space,controller.signal);const p=cap.input_preview;if(p?.profile!=='cospace.input-preview/0.1'||p.max_points!==10000||!p.formats?.includes(input.format))throw Error('当前服务未开放此资料的内容预览。');
   const value=await readPreview(`${endpoint}/api/inputs/${encodeURIComponent(input.id)}/preview?${new URLSearchParams({space_id:space})}`,controller.signal),checked=validatePreview(value,{space,input:input.id,source:input.cloud_sha256,snapshot:input.snapshot_sha256});if(!controller.signal.aborted)setData(checked);
  })().catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'预览失败。');}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});return()=>controller.abort();
 },[open,endpoint,space,input.id,input.cloud_sha256,input.snapshot_sha256,revision]);
 return <section className="data-detail-section" aria-label="资料内容预览"><div className="flex items-center justify-between gap-sm"><h3>内容预览</h3>{input.format==='ply_pointcloud'&&<Button type="button" size="sm" variant="ghost" onClick={()=>setOpen(v=>!v)}>{open?'关闭内容预览':'查看点云'}</Button>}</div>{input.format!=='ply_pointcloud'?<p>此路线暂未提供原资料预览，可在构建流程查看生成的模型。</p>:open?<>{busy&&<p role="status">正在核对来源并读取显示抽样…</p>}{error&&<div role="alert"><p>{error}</p><Button type="button" size="sm" variant="outline" onClick={()=>setRevision(v=>v+1)}>重试预览</Button></div>}{data&&<GeometryPreview data={data} label="登记资料点云"/>}</>:<p>按需查看原始点云抽样；不会启动构建或修改资料。</p>}</section>;
}
