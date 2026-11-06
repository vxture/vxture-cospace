import React,{useEffect,useState} from 'react';
import {Button,Input,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter} from '@vxture/design-system';
import {Cube,Images,CheckCircle,Books} from '@phosphor-icons/react';

// Presentation only. Availability and registration permission always come from the server.
const presets=[
 {id:'nyu-office-short',format:'nyu_rgbd_with_existing_poses',name:'NYU 办公室短场景',kind:'RGB-D + 轨迹',size:'2 秒 · 60 帧 · 57 帧位姿',origin:'来自已提供的 offices / office_0001a',description:'适合跑通资料登记、空间构建、双视图预览及发布流程。',limit:'使用已有估计轨迹，精度未验收。',icon:Images},
 {id:'os1-single-frame',format:'ros1_lidar_single_frame',name:'OS1-16 激光短片段',kind:'ROS1 激光',size:'1 秒 · 10 帧点云 · 6.3 MB',origin:'来自已提供的 mutli / 1.bag',description:'适合验证激光日志接入及单帧局部空间构建流程。',limit:'构建仅使用首帧；未做多帧配准与传感器融合。',icon:Cube},
] as const;
type Source={id:string;format:string;enabled?:boolean;needs_confirmation?:boolean};
type Availability={sources:Source[];catalog?:Source[];can_manage?:boolean;space_id?:string};

export function SampleLibrary({endpoint,spaceId,spaceName,authorized,onRegistered,onManageSources}:{endpoint:string;spaceId:string;spaceName:string;authorized:boolean;onRegistered:(id:string,created:boolean)=>void;onManageSources:()=>void}){
 const [open,setOpen]=useState(false),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [data,setData]=useState<Availability|null>(null),[selected,setSelected]=useState(''),[label,setLabel]=useState('');
 useEffect(()=>{
  if(!open)return;
  const abort=new AbortController();setLoading(true);setError('');setData(null);setSelected('');setLabel('');
  const path=authorized?'/api/source-settings':'/api/registration-sources';
  fetch(`${endpoint}${path}?`+new URLSearchParams({space_id:spaceId}),{cache:'no-store',signal:abort.signal}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'无权查看当前场景的样本来源。':'样本来源读取失败，请关闭后重试。');
   const value:Availability=await r.json();
   if(authorized&&value.space_id!==spaceId)throw Error('场景已变化，请重新打开样本库。');
   if(!abort.signal.aborted)setData(value);
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
  return()=>abort.abort();
 },[open,endpoint,spaceId,authorized]);
 const visible=presets.filter(p=>(data?.catalog?.length?data.catalog:data?.sources||[]).some(s=>s.id===p.id&&s.format===p.format));
 const enabled=(id:string)=>!!data?.sources.some(s=>s.id===id&&s.format===presets.find(p=>p.id===id)?.format);
 async function submit(e:React.FormEvent){
  e.preventDefault();if(busy||!selected||!enabled(selected))return;
  setBusy(true);setError('');
  try{
   const r=await fetch(`${endpoint}/api/inputs`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:spaceId,source_id:selected,label:label.trim()})});
   const body=await r.json();
   if(!r.ok)throw Error(r.status===403?'当前场景已无登记权限。':body.detail==='registration_source_not_allowed'?'来源配置已变化，请重新打开样本库核对。':'样本文件校验未通过，未登记资料。请检查来源文件。');
   setOpen(false);onRegistered(body.input.id,body.created);
  }catch(e){setError(e instanceof Error?e.message:'样本登记失败。');}finally{setBusy(false);}
 }
 return <><Button variant="outline" size="sm" disabled={!spaceId} onClick={()=>setOpen(true)}><Books size={16}/>样本库</Button>
  <Dialog open={open} onOpenChange={next=>{if(!busy)setOpen(next);}}><DialogContent className="data-sample-dialog">
   <DialogHeader><DialogTitle>预置样本</DialogTitle><DialogDescription>按真实场景分别管理样本。不同场景应使用独立的场景空间。</DialogDescription></DialogHeader>
   <div className="data-sample-target"><span>当前场景空间</span><strong>{spaceName}</strong></div>
   {loading&&<p role="status" className="data-sample-note">正在核对可用样本…</p>}
   <form onSubmit={submit} className="data-sample-form">
    <div className="data-sample-options" role="group" aria-label="选择预置样本">{visible.map(p=>{
     const active=selected===p.id,available=enabled(p.id);
     return <button type="button" key={p.id} className={`data-sample-option ${active?'is-selected':''}`} disabled={!available||busy} aria-pressed={active} onClick={()=>{setSelected(p.id);setLabel(p.name);setError('');}}>
      <span className="data-sample-visual"><p.icon size={32} weight="duotone"/><span>{p.kind}</span>{active&&<CheckCircle className="data-sample-check" size={18} weight="fill"/>}</span>
      <span className="data-sample-copy"><strong>{p.name}</strong><small>{p.size}</small><span>{p.description}</span><small>{p.origin}</small><em>{p.limit}</em><small className={available?'data-sample-ready':''}>{available?'可登记':data?.catalog?.find(s=>s.id===p.id)?.needs_confirmation?'来源已变化，需重新确认':'当前场景未启用来源'}</small></span>
     </button>;
    })}</div>
    {!loading&&data&&!visible.length&&<p className="data-sample-note">当前场景暂无可用的预置样本。{data.can_manage?'请检查服务端来源配置。':'请联系空间管理员启用样本来源。'}</p>}
    {selected&&<label className="data-sample-label">资料名称<Input value={label} onChange={e=>setLabel(e.target.value)} required maxLength={100} disabled={busy}/></label>}
    <p className="data-sample-note">仅登记属于当前三维场景的资料；其他场景请先切换至对应场景空间。样本用于流程验证，质量未验收；重复登记定位已有资料。</p>
    {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
    <DialogFooter>{data?.can_manage&&<Button type="button" variant="ghost" disabled={busy} onClick={()=>{setOpen(false);onManageSources();}}>配置样本来源</Button>}<Button type="button" variant="outline" disabled={busy} onClick={()=>setOpen(false)}>取消</Button><Button type="submit" disabled={busy||loading||!selected||!enabled(selected)||!label.trim()}>{busy?'校验并登记中…':'使用此样本'}</Button></DialogFooter>
   </form>
  </DialogContent></Dialog>
 </>;
}
