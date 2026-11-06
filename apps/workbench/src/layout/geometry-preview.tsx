import React,{lazy,Suspense,useState} from 'react';
import {Button,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '@vxture/design-system';
import type {PreviewGeometry} from './geometry-preview-data';
import './geometry-preview.css';
const Canvas=lazy(()=>import('./geometry-preview-canvas'));
export function GeometryPreview({data,label}:{data:PreviewGeometry;label:string}){
 const [large,setLarge]=useState(false),[show,setShow]=useState(true);
 const view=()=> <Suspense fallback={<p role="status">正在加载三维显示…</p>}><Canvas data={data}/></Suspense>;
 return <section className="geometry-preview" aria-label={label}><div className="geometry-preview-title"><h4>{label}</h4><div><Button size="sm" variant="ghost" type="button" onClick={()=>setShow(v=>!v)}>{show?'收起画面':'显示画面'}</Button><Button size="sm" variant="ghost" type="button" onClick={()=>setLarge(true)}>放大查看</Button></div></div>{show&&!large&&view()}<p>{data.point_count.toLocaleString()} 个原始点／单元 · 显示 {data.sampling.count.toLocaleString()} · 按索引等距抽样</p><dl className="geometry-bounds">{['X','Y','Z'].map((axis,i)=><div key={axis}><dt>{axis}</dt><dd>{data.bounds[0][i].toLocaleString(undefined,{maximumFractionDigits:3})} ～ {data.bounds[1][i].toLocaleString(undefined,{maximumFractionDigits:3})}{data.unit==='m'?' m':''}</dd></div>)}</dl><p>{data.frame_id} · {data.unit==='m'?'米制声明':'文件数值，单位待确认'} · {data.appearance==='source_rgb'?'原始RGB':data.appearance==='surface_cells'?'表面单元 · 其余未知':'中性／灰度显示'}</p><p>仅供内容核对，抽样可能遗漏细节；坐标轴置于显示中心，朝向为观察约定，场景对齐和精度未核验。</p><Dialog open={large} onOpenChange={setLarge}><DialogContent className="geometry-preview-dialog"><DialogHeader><DialogTitle>{label}</DialogTitle><DialogDescription>旋转与缩放仅调整显示，不改变原文件或坐标。</DialogDescription></DialogHeader>{large&&view()}<p>{data.sampling.count.toLocaleString()} 个显示点 · 局部坐标 · 精度未验收</p></DialogContent></Dialog></section>;
}
