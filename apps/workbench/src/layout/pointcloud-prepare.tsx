import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Input,Textarea,NativeSelect,Switch,DialogFooter,StatusBadge} from '@vxture/design-system';
import {checkCloud,preparePackage,Declaration,CheckedCloud} from './pointcloud-package';
import {UploadCapabilities,canPreparePointcloud} from './input-format';
import {GeometryPreview} from './geometry-preview';

type Prepared=Awaited<ReturnType<typeof preparePackage>>&{cloud:CheckedCloud};
export function PointcloudPrepare({endpoint,spaceId,capabilities,capabilityError,onRetry,onRegistered,onCancel,onBusyChange}:{endpoint:string;spaceId:string;capabilities:UploadCapabilities|null;capabilityError:string;onRetry:()=>void;onRegistered:(id:string,created:boolean)=>void;onCancel:()=>void;onBusyChange:(busy:boolean)=>void}){
 const [file,setFile]=useState<File|null>(null),[name,setName]=useState(''),[frame,setFrame]=useState(''),[axes,setAxes]=useState<[string,string,string]>(['','','']),[scope,setScope]=useState(''),[description,setDescription]=useState('');
 const [metres,setMetres]=useState(false),[confirmed,setConfirmed]=useState(false),[prepared,setPrepared]=useState<Prepared|null>(null),[busy,setBusy]=useState<'checking'|'uploading'|null>(null),[error,setError]=useState(''),[download,setDownload]=useState('');
 const [checked,setChecked]=useState<CheckedCloud|null>(null);
 const generation=useRef(0),request=useRef<AbortController|null>(null),gate=useRef(false);
 useEffect(()=>{onBusyChange(!!busy);return()=>onBusyChange(false);},[busy,onBusyChange]);
 useEffect(()=>{return()=>{generation.current++;request.current?.abort();};},[spaceId,endpoint]);
 useEffect(()=>{if(!prepared){setDownload('');return;}const url=URL.createObjectURL(prepared.bundle);setDownload(url);return()=>URL.revokeObjectURL(url);},[prepared]);
 const enabled=canPreparePointcloud(capabilities);
 const geometry=useMemo(()=>checked?{...checked.display,unit:metres?'m':'',frame_id:frame.trim()||'原文件局部坐标',axes}:null,[checked,metres,frame,axes]);
 function invalidate(){generation.current++;setPrepared(null);setConfirmed(false);setError('');}
 async function inspectFile(){
  if(gate.current||!file||!enabled)return;gate.current=true;const run=++generation.current,controller=new AbortController();request.current=controller;setPrepared(null);setConfirmed(false);setBusy('checking');setError('');setChecked(null);
  try{const cloud=await checkCloud(file,controller.signal);if(run===generation.current)setChecked(cloud);}catch(e){if(run===generation.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'文件检查失败。');}finally{gate.current=false;if(run===generation.current)setBusy(null);}
 }
 async function inspect(event:React.FormEvent){
  event.preventDefault();if(gate.current||!file||!enabled)return;
  if(!metres){setError('请先确认原文件数值单位为米；系统不会换算坐标。');return;}
  gate.current=true;const run=++generation.current,controller=new AbortController();request.current=controller;setBusy('checking');setError('');setPrepared(null);setConfirmed(false);
  try{const cloud=checked||await checkCloud(file,controller.signal);if(run===generation.current)setChecked(cloud);const declaration:Declaration={frame_id:frame.trim(),axes:axes.map(v=>v.trim()) as [string,string,string],scope:scope as Declaration['scope'],description:description.trim()};const value=await preparePackage(cloud,declaration);controller.signal.throwIfAborted();
   if(value.bundle.size>capabilities!.max_upload_bytes||value.bundle.size>capabilities!.max_expanded_bytes)throw Error('准备后的资料超过当前服务上传预算。');
   if(run===generation.current)setPrepared({...value,cloud});
  }catch(e){if(run===generation.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'本机检查失败，请核查文件后重试。');}finally{gate.current=false;if(run===generation.current)setBusy(null);}
 }
 async function register(){
  if(gate.current||!prepared||!confirmed||!name.trim()||!enabled)return;
  gate.current=true;const run=generation.current,controller=new AbortController();request.current=controller;setBusy('uploading');setError('');
  try{const r=await fetch(`${endpoint}/api/input-uploads?${new URLSearchParams({space_id:spaceId,label:name.trim()})}`,{method:'POST',headers:{'Content-Type':'application/zip'},body:prepared.bundle,signal:controller.signal});const body=await r.json();
   if(!r.ok){const messages:Record<string,string>={upload_content_validation_failed:'服务端复核未通过，请核查原文件和声明后重新准备。',upload_scene_storage_budget:'当前场景上传存储预算已满，请联系管理员。',upload_existing_evidence_invalid:'原登记资料已变化，请核查历史资料。',space_access_denied:'当前账户无权向此场景登记资料。',authentication_required:'登录会话已失效，请重新登录。'};throw Error(messages[body.detail]||'登记未完成，请重试相同准备包或刷新资料列表核查。');}
   if(body.input?.space_id!==spaceId||body.input?.format!=='ply_pointcloud'||!body.input?.id||body.upload?.sha256!==prepared.sha256)throw Error('入库回执与当前场景或准备包不一致，请刷新核查。');
   if(run===generation.current)onRegistered(body.input.id,body.created);
  }catch(e){if(run===generation.current&&!controller.signal.aborted)setError(e instanceof TypeError?'连接中断，登记结果未确认。可重试相同准备包，系统会复用已登记记录。':e instanceof SyntaxError?'登记回执无法确认，请刷新列表或重试相同准备包。':e instanceof Error?e.message:'登记未完成，请重试。');}finally{gate.current=false;if(run===generation.current)setBusy(null);}
 }
 if(!enabled)return <div className="flex flex-col gap-md"><p role={capabilityError?'alert':'status'} className="text-body-small">{capabilityError||(!capabilities?'正在读取准备能力…':'当前服务未开放浏览器PLY准备，可使用已有资料包或已配置来源。')}</p>{capabilityError&&<Button size="sm" variant="outline" onClick={onRetry}>重试读取入口</Button>}<DialogFooter><Button variant="outline" onClick={onCancel}>取消</Button></DialogFooter></div>;
 return <form onSubmit={inspect} className="pointcloud-prepare-form" aria-label="本机PLY准备">
  <p className="text-label-small text-muted-foreground">支持二进制小端 XYZ／XYZRGB，最大32MiB、100万点。原文件保持不变；坐标不做转换。</p>
  <fieldset disabled={!!busy} className="pointcloud-fields">
   <label>PLY文件<Input aria-label="原始PLY文件" type="file" accept=".ply" required onChange={e=>{invalidate();setChecked(null);const next=e.target.files?.[0]||null;setFile(next);setName(next?.name.replace(/\.ply$/i,'').slice(0,100)||'');}}/></label>
   <Button type="button" size="sm" variant="outline" className="self-start" disabled={!file||!!busy} onClick={inspectFile}>检查文件并预览</Button>
   {geometry&&<GeometryPreview data={geometry} label="本机资料预览"/>}
   <label>资料名称<Input aria-label="PLY资料名称" value={name} required maxLength={100} onChange={e=>setName(e.target.value)}/></label>
   <div className="pointcloud-coordinate-grid"><label>局部坐标系<Input aria-label="PLY局部坐标系" placeholder="例如 os1_16/os_sensor" value={frame} maxLength={100} required onChange={e=>{invalidate();setFrame(e.target.value);}}/></label><label>坐标范围<NativeSelect aria-label="PLY坐标范围" value={scope} required onChange={e=>{invalidate();setScope(e.target.value);}}><option value="" disabled>明确选择范围</option><option value="sensor_local">传感器局部</option><option value="scene_local">场景局部</option></NativeSelect></label></div>
   <div className="pointcloud-axes">{['X','Y','Z'].map((axis,i)=><label key={axis}>{axis}轴语义<Input aria-label={`PLY ${axis}轴语义`} placeholder={`如 sensor_${axis.toLowerCase()}`} value={axes[i]} maxLength={40} required onChange={e=>{invalidate();setAxes(values=>values.map((v,index)=>index===i?e.target.value:v) as [string,string,string]);}}/></label>)}</div>
   <label>来源说明<Textarea aria-label="PLY来源说明" placeholder="说明文件来自哪里、包含什么范围，以及已知处理情况。" value={description} required maxLength={500} onChange={e=>{invalidate();setDescription(e.target.value);}}/></label>
   <label className="pointcloud-confirm"><Switch aria-label="确认原文件单位为米" checked={metres} onCheckedChange={value=>{invalidate();setMetres(value);}}/><span>确认原文件数值单位为米（m）</span></label>
  </fieldset>
  {prepared&&<section className="pointcloud-prepared" aria-label="PLY准备结果"><div className="flex items-center justify-between gap-sm"><StatusBadge tone="success">本机检查通过 · 尚未登记</StatusBadge><span>{prepared.cloud.points.toLocaleString('zh-CN')} 点</span></div><p>{prepared.cloud.colored?'含原始RGB':'无RGB，使用中性显示'} · {(prepared.cloud.raw.length/1024/1024).toFixed(2)} MiB</p><p>{prepared.receipt.coordinates.frame_id} · {prepared.receipt.coordinates.axes.join(' / ')} · 场景对齐未核验</p><p>来源由你声明：{prepared.receipt.description}</p><details className="data-technical-details"><summary>原文件与资料包摘要</summary><p>原文件：{prepared.receipt.original_name}</p><p className="break-all">SHA-256 {prepared.cloud.sha256}</p><p className="break-all">资料包 SHA-256 {prepared.sha256}</p>{download&&<a className="text-primary" href={download} download="cospace-pointcloud.zip">保存准备好的资料包</a>}</details><label className="pointcloud-confirm"><Switch aria-label="确认坐标与来源声明" disabled={!!busy} checked={confirmed} onCheckedChange={setConfirmed}/><span>已核对坐标与来源声明；服务端将重新校验后登记</span></label></section>}
  {busy&&<p role="status" className="text-body-small">{busy==='checking'?'正在本机检查并准备资料包…':'正在上传并由服务端复核…'}</p>}
  {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
  <DialogFooter><Button type="button" variant="outline" disabled={!!busy} onClick={onCancel}>取消</Button><Button type="submit" variant={prepared?'outline':'default'} disabled={!!busy||!file}>{prepared?'重新检查':'检查并准备'}</Button>{prepared&&<Button type="button" disabled={!!busy||!confirmed||!name.trim()} onClick={register}>确认并登记</Button>}</DialogFooter>
 </form>;
}
