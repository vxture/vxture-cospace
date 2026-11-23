import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Drawer,NativeSelect} from '@vxture/design-system';
import {CubeFocus} from '@phosphor-icons/react';
import {ModelDisplayCanvas} from './model-display-canvas';
import {engineeringScene,exactPoint,exactPoints,ModelAccessChanged,waitForModel,type EngineeringSource,type ExactPoint} from './model-exact-data';
import type {SceneData,XYZ} from './real-space-data';
import type {GeometryMarker,GeometryFocus} from './geometry-preview-canvas';
import type {SceneControls} from './real-space-canvas';
import './engineering-model-canvas.css';
export type {EngineeringSource,ExactPoint} from './model-exact-data';
type Props={source:EngineeringSource;markers?:GeometryMarker[];selected?:string;onSelect?:(id:string)=>void;focus?:GeometryFocus;anchor?:XYZ;onConfirmPoint?:(point:ExactPoint)=>void;contextKey?:string;onAccessLost?:()=>void};
export function EngineeringModelCanvas({source,markers=[],selected='',onSelect,focus,anchor,onConfirmPoint,contextKey='',onAccessLost}:Props){
 const [data,setData]=useState<SceneData|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0),[denied,setDenied]=useState(false);
 const [query,setQuery]=useState<XYZ|null>(null),[radius,setRadius]=useState('0.01'),[points,setPoints]=useState<ExactPoint[]>([]),[chosen,setChosen]=useState(''),[message,setMessage]=useState(''),[working,setWorking]=useState(false);
 const api=useRef<SceneControls|null>(null),request=useRef<AbortController|null>(null);
 const key=[source.space,source.candidate,source.manifest,source.source,source.frame].join('|');
 const context=useRef('');context.current=key+'|'+contextKey;
 const latest=useRef({onConfirmPoint,onAccessLost});latest.current={onConfirmPoint,onAccessLost};
 function clear(){request.current?.abort();setQuery(null);setPoints([]);setChosen('');setMessage('');setWorking(false);}
 function accessLost(){clear();setDenied(true);setData(null);setError('模型的访问或版本状态已变化，请重新打开。');latest.current.onAccessLost?.();}
 useEffect(()=>{const abort=new AbortController();setData(null);setError('');setDenied(false);
  void (async()=>{try{let scene;do{scene=await engineeringScene({space:source.space,identity:source.candidate,kind:'candidate'},abort.signal,source);if(!abort.signal.aborted)setData(scene);if(scene.display?.state!=='preparing')break;await waitForModel(abort.signal,3000);}while(!abort.signal.aborted);}catch(error){if(!abort.signal.aborted){setError(error instanceof Error?error.message:'模型显示暂不可用。');if(error instanceof ModelAccessChanged)accessLost();}}})();
  return()=>{abort.abort();request.current?.abort();};
 },[key,attempt]);
 // Context includes the selected control and transformation revision, never a LOD.
 useEffect(()=>{clear();},[key,contextKey,!!onConfirmPoint]);
 useEffect(()=>{if(focus)api.current?.focus(focus.position);},[focus]);
 const candidate=points.find(p=>String(p.point_index)===chosen);
 const scene=useMemo(()=>data?{...data,objects:[...markers,...(anchor?[{id:'engineering-anchor',label:'已核对位置',position:anchor}]:[]),...(candidate?[{id:'engineering-candidate',label:'待确认',position:candidate.anchor_m}]:[])].map(p=>({object_id:p.id,type_id:'engineering-marker',properties:{name:p.label,purpose:('kind' in p&&p.kind)||''},anchor_m:p.position,confirmation:'unverified',evidence:{kind:'overlay',member:'spatial.npz',sha256:source.source,point_index:0}}))}:null,[data,markers,anchor,candidate,source.source]);
 async function search(point:XYZ){
  const expected=context.current;request.current?.abort();const abort=new AbortController();request.current=abort;setQuery(point);setPoints([]);setChosen('');setWorking(true);setMessage('正在核对原始模型点…');
  try{const result=await exactPoints(source,{point,radius:Number(radius)},abort.signal,()=>setMessage('精确数据准备中，显示画面仍可浏览…'));
   if(abort.signal.aborted||context.current!==expected)return;setPoints(result.points);setMessage(result.state==='narrow_query'?'附近点过多，请缩小查询半径或放大模型后重新选点。':result.state==='unavailable'?'精确数据暂不可用，当前点位未改变；请稍后重试。':result.points.length?'请选择一个原始点，核对后确认。':'当前范围没有原始点，请调整半径或放大模型后重新选点。');
  }catch(error){if(!abort.signal.aborted){if(error instanceof ModelAccessChanged)accessLost();else setMessage(error instanceof TypeError?'原始点读取失败，请重试。':error instanceof Error?error.message:'原始点查询失败。');}}
  finally{if(!abort.signal.aborted)setWorking(false);}
 }
 async function confirm(){
  const expected=context.current;if(!candidate||working)return;request.current?.abort();const abort=new AbortController();request.current=abort;setWorking(true);
  try{const verified=await exactPoint(source,candidate.point_index,abort.signal);if(abort.signal.aborted||context.current!==expected)return;if(verified.point_id!==candidate.point_id||verified.anchor_m.some((n,i)=>n!==candidate.anchor_m[i]))throw new ModelAccessChanged('原始点已变化，请重新打开模型。');latest.current.onConfirmPoint?.(verified);clear();}
  catch(error){if(!abort.signal.aborted){if(error instanceof ModelAccessChanged)accessLost();else setMessage(error instanceof TypeError?'原始点核对失败，请重试。':error instanceof Error?error.message:'原始点核对失败。');}}
  finally{if(!abort.signal.aborted)setWorking(false);}
 }
 return <div className="engineering-model-canvas" data-picking={!!onConfirmPoint} data-engineering-context={contextKey}>
  {scene&&!denied&&<ModelDisplayCanvas data={scene} view="human" geometry markers selected={selected} select={id=>{if(markers.some(p=>p.id===id))onSelect?.(id);}} api={api} engineering focus={focus?.position} onReady={()=>{if(focus)api.current?.focus(focus.position);}} onPick={onConfirmPoint?point=>void search(point):undefined} onAccessLost={accessLost}/>}
  {!data&&!error&&<p className="engineering-model-message" role="status">正在读取固定模型…</p>}
  {error&&<div className="engineering-model-message" role="alert"><p>{error}</p>{!denied&&<Button size="sm" variant="outline" onClick={()=>setAttempt(n=>n+1)}>重试显示</Button>}</div>}
  {data?.display?.state==='ready'&&!denied&&<Button className="engineering-model-fit" size="icon-md" variant="outline" aria-label="适配全图" title="适配全图" onClick={()=>api.current?.reset()}><CubeFocus size={24}/></Button>}
  <Drawer open={!!query} onClose={clear} side="right" width="md" title="确认原始模型点" description="显示点只用于定位；确认后使用固定模型的原始坐标。" closeLabel="关闭原始点核对" footer={<div className="engineering-point-actions"><Button size="sm" variant="outline" onClick={clear}>取消</Button><Button size="sm" disabled={!candidate||working||denied||!onConfirmPoint} onClick={()=>void confirm()}>确认原始点</Button></div>}>
   <div className="engineering-point-content"><div className="engineering-point-tools"><span>查询半径</span><NativeSelect aria-label="原始点查询半径" value={radius} onChange={e=>{setRadius(e.target.value);setChosen('');setPoints([]);setMessage('半径已修改，请重新查询。');}} disabled={working}>{[['0.001','0.1 cm'],['0.005','0.5 cm'],['0.01','1 cm'],['0.05','5 cm'],['0.1','10 cm'],['1','100 cm']].map(([value,title])=><option key={value} value={value}>{title}</option>)}</NativeSelect><Button size="sm" variant="outline" disabled={working||!query} onClick={()=>query&&void search(query)}>重新查询</Button></div>
   <p role="status">{message}</p><div className="engineering-point-list" role="group" aria-label="候选原始点">{points.map(point=><label key={point.point_id} data-selected={chosen===String(point.point_index)}><input type="radio" name="engineering-original-point" checked={chosen===String(point.point_index)} disabled={working} onChange={()=>{setChosen(String(point.point_index));api.current?.focus(point.anchor_m);}}/><span><strong>原始点 {point.point_index}</strong><span>{point.anchor_m.map((n,i)=>['X','Y','Z'][i]+' '+n.toFixed(4)).join(' · ')} m</span></span></label>)}</div><p>坐标显示位数不代表地图实测精度；原始数值完整参与保存与核对。</p></div>
  </Drawer>
 </div>;
}
