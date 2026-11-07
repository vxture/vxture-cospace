import React,{useEffect,useRef,useState} from 'react';
import {Button,Input,Table,TableHeader,TableBody,TableRow,TableHead,TableCell} from '@vxture/design-system';
import {ArrowClockwise,ArrowDown,FileText,Paperclip,UploadSimple} from '@phosphor-icons/react';

export type Attachment={id:string;space_id:string;name:string;bytes:number;sha256:string;actor:string;created_at:string;processing:'stored_original'};
type Props=Readonly<{endpoint:string;space:string;revision:number;onChanged:()=>void;onSelect:(item:Attachment|null)=>void}>;
const maxBytes=32*1024*1024;
const formatDate=(value:string)=>new Date(value).toLocaleString('zh-CN');

export function SceneAttachments({endpoint,space,revision,onChanged,onSelect}:Props){
 const [items,setItems]=useState<Attachment[]>([]),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[tick,setTick]=useState(0);
 const [file,setFile]=useState<File|null>(null),[search,setSearch]=useState('');
 const active=useRef(true),request=useRef<AbortController|null>(null),input=useRef<HTMLInputElement|null>(null);
 useEffect(()=>{active.current=true;return()=>{active.current=false;request.current?.abort();};},[]);
 useEffect(()=>{const refresh=()=>setTick(v=>v+1);window.addEventListener('cospace:session-confirmed',refresh);return()=>window.removeEventListener('cospace:session-confirmed',refresh);},[]);
 useEffect(()=>{
  const controller=new AbortController();setItems([]);setLoading(true);setError('');onSelect(null);
  fetch(`${endpoint}/api/scene-attachments?${new URLSearchParams({space_id:space})}`,{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok)throw new Error('配套资料暂时无法读取，请重新读取或检查场景权限。');
   const body=await r.json();
   if(body.profile!=='cospace.scene-attachments/0.1'||body.space_id!==space||!Array.isArray(body.attachments)||body.attachments.some((item:Attachment)=>item.space_id!==space||item.processing!=='stored_original'||!/^attachment-[a-f0-9]{16}$/.test(item.id)))throw new Error('配套资料与当前场景不一致。');
   if(!controller.signal.aborted)setItems(body.attachments);
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[endpoint,space,revision,tick,onSelect]);
 async function upload(event:React.FormEvent){
  event.preventDefault();if(!file||busy)return;
  if(!file.size||file.size>maxBytes){setError('请选择大于 0 字节且不超过 32 MiB 的文件。');return;}
  const controller=new AbortController();request.current=controller;setBusy(true);setError('');setNotice('');
  try{
   const response=await fetch(`${endpoint}/api/scene-attachments?${new URLSearchParams({space_id:space,name:file.name})}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file,signal:controller.signal});
   const body=await response.json();
   if(!response.ok)throw new Error(response.status===413?'文件超过 32 MiB。':response.status===422?'文件名或格式不支持。请选择 PDF、PNG、JPG、CSV、TXT 或 IFC。':'保存结果尚未确认，请重试同一文件或重新读取列表。');
   if(body.attachment?.space_id!==space||body.attachment?.processing!=='stored_original')throw new Error('保存结果与当前场景不一致。');
   if(active.current){setFile(null);if(input.current)input.current.value='';setNotice(body.created?'配套资料已保存。':'已定位当前场景中相同内容的资料，保留原文件名与登记记录。');onChanged();}
  }catch(e){if(active.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'保存结果尚未确认，请重试同一文件。');}
  finally{if(active.current)setBusy(false);}
 }
 const shown=items.filter(item=>item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
 return <>
  <div className="reference-intro"><div><h2><Paperclip size={18}/>配套资料</h2><p>保存图纸、说明、照片、表格与 IFC 原文件，供当前场景参考。</p></div><Button variant="ghost" size="sm" disabled={busy||loading} onClick={()=>setTick(v=>v+1)}><ArrowClockwise size={15}/>重新读取</Button></div>
  <form className="reference-upload" onSubmit={upload}><label>选择文件<Input ref={input} aria-label="配套资料文件" type="file" accept=".pdf,.png,.jpg,.jpeg,.csv,.txt,.ifc" disabled={busy} onChange={e=>{setFile(e.target.files?.[0]||null);setError('');}}/></label><Button type="submit" size="sm" disabled={!file||busy}><UploadSimple size={15}/>{busy?'正在保存…':'保存原文件'}</Button><p>单文件最多 32 MiB。配套资料不自动参与构建或发布；IFC 构件预览需另行解析。</p></form>
  {notice&&<p className="data-notice" role="status">{notice}</p>}{error&&<p className="data-notice" role="alert">{error}</p>}
  <div className="data-toolbar"><Input aria-label="搜索配套资料" placeholder="搜索文件名…" value={search} onChange={e=>setSearch(e.target.value)}/><span className="data-result-count">{shown.length} 项</span></div>
  <div className="data-table-scroll">{loading?<p className="data-loading" role="status">正在读取配套资料…</p>:<Table className="data-table"><TableHeader><TableRow><TableHead>文件名称</TableHead><TableHead>大小</TableHead><TableHead>登记时间</TableHead><TableHead>处理状态</TableHead></TableRow></TableHeader><TableBody>{shown.map(item=><TableRow key={item.id} onClick={()=>onSelect(item)}><TableCell><button className="data-record-name" onClick={()=>onSelect(item)}><span className="data-file-icon"><FileText size={20}/></span><strong>{item.name}</strong></button></TableCell><TableCell>{(item.bytes/1024).toFixed(1)} KiB</TableCell><TableCell>{formatDate(item.created_at)}</TableCell><TableCell>已保存原文件</TableCell></TableRow>)}</TableBody></Table>}{!loading&&!error&&!shown.length&&<div className="data-empty"><Paperclip size={32}/><h2>{search?'没有匹配的文件':'当前场景暂无配套资料'}</h2><p>选择本机文件并保存，即可在本场景中查看登记信息和下载原文件。</p></div>}</div>
 </>;
}

export function AttachmentSummary({item,endpoint}:{item:Attachment;endpoint:string}){
 return <><div className="data-detail-title"><span className="data-detail-symbol"><Paperclip size={25}/></span><h2>{item.name}</h2><p>已保存原文件</p></div><dl className="data-detail-facts"><div><dt>文件大小</dt><dd>{item.bytes.toLocaleString('zh-CN')} 字节</dd></div><div><dt>登记时间</dt><dd>{formatDate(item.created_at)}</dd></div><div><dt>登记人</dt><dd>{item.actor}</dd></div><div><dt>SHA256</dt><dd>{item.sha256}</dd></div></dl><p className="text-body-small text-muted-foreground">此文件仅作为场景配套资料，不自动进入构建或固定发布。</p><div className="data-detail-actions"><Button asChild size="sm"><a href={`${endpoint}/api/scene-attachments/${item.id}?${new URLSearchParams({space_id:item.space_id})}`} download><ArrowDown size={15}/>下载原文件</a></Button></div></>;
}
