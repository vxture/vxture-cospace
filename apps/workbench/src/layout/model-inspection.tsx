import React,{useEffect,useRef,useState} from 'react';
import {Button,Input} from '@vxture/design-system';
import {previewEndpoint,type SceneData} from './real-space-data';
import {recordLink} from './record-navigation';

export function ModelInspection({data,space,candidate,publication}:{data:SceneData;space:string;candidate:string;publication:string}){
 const base=`${previewEndpoint}/${candidate?'candidates':'publications'}/${encodeURIComponent(candidate||publication)}/`;
 const [point,setPoint]=useState('0, 0, 0'),[result,setResult]=useState<unknown>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const controller=useRef<AbortController|null>(null);
 useEffect(()=>()=>controller.current?.abort(),[]);
 async function query(event:React.FormEvent){
  event.preventDefault();const values=point.split(',').map(v=>v.trim());
  if(values.length!==3||values.some(v=>!v||!Number.isFinite(Number(v)))){setError('请输入三个有效坐标，以逗号分隔。');return;}
  controller.current?.abort();const request=new AbortController();controller.current=request;setBusy(true);setError('');setResult(null);
  try{const response=await fetch(base+'api/query',{method:'POST',signal:request.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({point_m:values.map(Number)})});const body=await response.json();if(!response.ok)throw Error('查询失败，请核对查询权限、坐标与版本状态。');if(body.space_id!==space||body.model_id!==data.model.id||body.source_model_sha256!==data.model.members['spatial.npz'].sha256||body.frame_id!==data.model.frame_id||publication&&(body.publication_id!==publication||body.publication_model_manifest_sha256!==data.model.publication?.model_manifest_sha256))throw Error('查询响应与当前版本不一致。');setResult(body);}catch(e){if(!request.signal.aborted)setError((e as Error).message);}finally{if(!request.signal.aborted)setBusy(false);}
 }
 return <section aria-label="模型查询与文件" className="flex flex-col gap-md border-t border-border pt-md"><h3>坐标查询</h3><form onSubmit={query} className="flex flex-col gap-sm"><label htmlFor="viewer-query-point">模型坐标 · 米<Input id="viewer-query-point" value={point} onChange={e=>setPoint(e.target.value)} placeholder="X, Y, Z"/></label><div className="flex flex-wrap gap-sm"><Button type="button" size="sm" variant="ghost" disabled={!data.agent_points.length} onClick={()=>{setPoint(data.agent_points[0].join(', '));setResult(null);setError('');}}>表面示例点</Button><Button type="submit" size="sm" disabled={busy}>{busy?'查询中…':'查询状态'}</Button></div></form>{error&&<p role="alert">{error}</p>}{result!==null&&<pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-label-small" aria-label="坐标查询结果">{JSON.stringify(result,null,2)}</pre>}
 <h3>成果文件</h3><div className="flex flex-wrap gap-sm">{['model.json','human.ply','agent.npz','offline-checks.json','objects.json','ontology.json','relations.json','business.json'].filter(name=>data.model.inspection_files?data.model.inspection_files.includes(name):name==='model.json'||!!data.model.members[name]).map(name=><Button asChild size="sm" variant="ghost" key={name}><a href={base+name} target="_blank" rel="noopener noreferrer">{name}</a></Button>)}</div>
 <Button asChild size="sm" variant="secondary"><a href={recordLink(candidate?'association':'delivery',{space,...(candidate?{job:candidate,tab:'objects'}:{publication,tab:'offline'})})}>{candidate?'维护对象与关系':'离线交付'}</a></Button>
 </section>;
}
