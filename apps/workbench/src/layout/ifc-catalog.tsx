import React,{lazy,Suspense,useEffect,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent,Input,NativeSelect} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';
import {useRecordNavigation} from './record-navigation';
import {readPreview,type PreviewGeometry} from './geometry-preview-data';
const Canvas=lazy(()=>import('./geometry-preview-canvas'));
type Product={element_id:string;global_id:string;ifc_type:string;name:string;geometry_status:string;bounds_m?:number[][]};
type Catalog={configured:boolean;space_id:string;catalog_sha256:string;frame_id:string;product_count:number;geometry_counts:Record<string,number>;products:Product[];alignment_verified:boolean};
const xyz=(p:unknown):p is number[]=>Array.isArray(p)&&p.length===3&&p.every(v=>typeof v==='number'&&Number.isFinite(v));

export function IfcCatalog(){const target=useRecordNavigation();const [revision,setRevision]=useState(0);
 useEffect(()=>{const refresh=()=>setRevision(v=>v+1);window.addEventListener('cospace:session-confirmed',refresh);return()=>window.removeEventListener('cospace:session-confirmed',refresh);},[]);
 return <CatalogView key={`${target.space}:${revision}`} space={target.space} retry={()=>setRevision(v=>v+1)}/>;}
function CatalogView({space,retry}:{space:string;retry:()=>void}){
 const [catalog,setCatalog]=useState<Catalog|null>(null),[error,setError]=useState(''),[search,setSearch]=useState(''),[element,setElement]=useState(''),[geometry,setGeometry]=useState<PreviewGeometry|null>(null);
 useEffect(()=>{const controller=new AbortController();setError('');
  fetch(`${endpoint}/api/scene-ifc?${new URLSearchParams({space_id:space})}`,{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error('构件资料读取失败，请核对场景关联权限与资料配置。');const value=await r.json();
   if(value.space_id!==space||value.configured&&(!/^[a-f0-9]{64}$/.test(value.catalog_sha256)||value.alignment_verified!==false||!Array.isArray(value.products)))throw Error('IFC 场景绑定不一致。');
   if(!controller.signal.aborted){setCatalog(value);setElement(value.products?.[0]?.element_id||'');}
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[space]);
 const product=catalog?.products?.find(p=>p.element_id===element);
 useEffect(()=>{setGeometry(null);setError('');const controller=new AbortController();
  if(catalog?.configured&&product?.geometry_status==='extracted')readPreview(`${endpoint}/api/scene-ifc/element?${new URLSearchParams({space_id:space,element_id:element,catalog_sha256:catalog.catalog_sha256})}`,controller.signal).then((value:unknown)=>{
   const v=value as PreviewGeometry&{space_id:string;element_id:string;catalog_sha256:string;profile:string;alignment_verified:boolean;robot_ready:boolean};
   if(v.profile!=='cospace.ifc-element-preview/0.1'||v.space_id!==space||v.element_id!==element||v.catalog_sha256!==catalog.catalog_sha256||v.frame_id!==catalog.frame_id||v.alignment_verified!==false||v.robot_ready!==false||v.unit!=='m'||!Number.isSafeInteger(v.point_count)||v.point_count<1||v.sampling?.stride!==Math.max(1,Math.ceil(v.point_count/10000))||!Array.isArray(v.points)||v.points.length!==Math.ceil(v.point_count/v.sampling.stride)||!Array.isArray(v.colors)||v.colors.length!==v.points.length||!v.points.every(xyz)||!v.colors.every(p=>xyz(p)&&p.every(n=>Number.isInteger(n)&&n>=0&&n<=255))||!Array.isArray(v.bounds)||v.bounds.length!==2||!v.bounds.every(xyz))throw Error('构件几何响应不一致。');
   if(!controller.signal.aborted)setGeometry(v);
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();
 },[space,element,catalog,product]);
 const visible=catalog?.products?.filter(p=>`${p.name} ${p.ifc_type} ${p.global_id}`.toLowerCase().includes(search.toLowerCase()))||[];
 return <Card className="module-surface"><CardHeader><CardTitle>IFC 构件资料</CardTitle></CardHeader><CardContent className="flex flex-col gap-lg"><p className="text-body-small text-muted-foreground">查看本场景配套 IFC 的构件标识、类型和几何。构件使用 IFC 自身坐标；与点云的坐标关系尚未确认，当前保留为待关联资料。</p>{error&&<div><p role="alert">{error}</p><Button variant="outline" onClick={retry}>重新读取</Button></div>}{!catalog&&!error&&<p role="status">正在读取 IFC 资料…</p>}{catalog&&!catalog.configured&&<p>当前场景尚未配置经过解析的 IFC 构件目录。</p>}{catalog?.configured&&<><p className="text-body-small">{catalog.product_count} 个产品实体 · {catalog.geometry_counts.extracted||0} 个已提取几何 · {catalog.geometry_counts.extraction_failed||0} 个提取失败 · 坐标关系待确认</p><label>搜索构件<Input value={search} onChange={e=>setSearch(e.target.value)} placeholder="名称、IFC 类型或 GlobalId"/></label><label>IFC 构件<NativeSelect value={element} onChange={e=>setElement(e.target.value)}>{product&&!visible.some(p=>p.element_id===element)&&<option value={element}>{product.ifc_type} · {product.name||product.global_id}</option>}{visible.map(p=><option key={p.element_id} value={p.element_id}>{p.ifc_type} · {p.name||p.global_id}</option>)}</NativeSelect></label><p className="text-label-small text-muted-foreground">匹配 {visible.length} 个构件</p>{product&&<><dl className="grid grid-cols-1 md:grid-cols-2 gap-md text-body-small"><div><dt>GlobalId</dt><dd className="break-all">{product.global_id}</dd></div><div><dt>IFC 类型</dt><dd>{product.ifc_type}</dd></div><div><dt>几何状态</dt><dd>{product.geometry_status==='extracted'?'已提取':product.geometry_status==='no_representation'?'源文件未提供几何表示':'提取失败'}</dd></div><div><dt>坐标关系</dt><dd>待确认</dd></div></dl>{product.geometry_status==='extracted'&&<section className="geometry-preview" aria-label="IFC 构件几何预览"><h4>构件几何预览</h4><p>显示三角网格顶点，最多 10,000 点；不代表几何精度验收。</p>{!geometry&&!error&&<p role="status">正在读取构件几何…</p>}{geometry&&<Suspense fallback={<p>正在加载构件…</p>}><Canvas data={geometry}/></Suspense>}</section>}</>}<p className="text-label-small text-muted-foreground break-all">固定资料摘要：{catalog.catalog_sha256} · 坐标：{catalog.frame_id}</p></>}</CardContent></Card>;
}
