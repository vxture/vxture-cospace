import React,{useEffect,useState} from 'react';
import {Button} from '@vxture/design-system';
import {businessEndpoint as endpoint} from './business-endpoint';

import {checked,relations,type Structure} from './ifc-structure-contract';
import {IfcOpeningObservation} from './ifc-opening-observation';
import {IfcTypeProposals} from './ifc-type-proposals';

export function IfcStructureSummary({space,catalogSha256,selectedId,onSelect}:Readonly<{space:string;catalogSha256:string;selectedId?:string;onSelect:(id:string)=>void}>){
 const [data,setData]=useState<Structure|null>(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setData(null);setError('');
  fetch(`${endpoint}/api/scene-ifc/structure?${new URLSearchParams({space_id:space,catalog_sha256:catalogSha256})}`,{signal:controller.signal,cache:'no-store'})
   .then(async response=>{if(!response.ok){throw new Error('结构声明读取失败，请重新读取资料。');}return checked(await response.json(),space,catalogSha256);})
   .then(value=>{if(!controller.signal.aborted)setData(value);})
   .catch(reason=>{if(!controller.signal.aborted)setError(reason.message);});
  return()=>controller.abort();
 },[space,catalogSha256,revision]);
 const entities=new Map(data?.entities.map(e=>[e.entity_id,e])||[]);
 const edges=data?.relations.filter(r=>r.source_id===selectedId||r.target_id===selectedId)||[];
 const node=(id:string)=>{const e=entities.get(id);return <Button variant="ghost" size="sm" className="max-w-full truncate" onClick={()=>e&&onSelect(e.element_id)}>{e?.name||id}</Button>;};
 return <section aria-label="IFC 结构声明" aria-busy={!data&&!error} className="flex flex-col gap-md border-t pt-lg">
  <header className="flex flex-wrap items-center justify-between gap-md"><h3 className="text-title-small">结构声明</h3><div className="flex items-center gap-md"><span className="text-label-small text-muted-foreground">设计资料 · 待核验</span>{data?.structure_available&&<Button variant="ghost" size="sm" asChild><a href={`${endpoint}/api/scene-ifc/structure-snapshot?${new URLSearchParams({space_id:space,catalog_sha256:catalogSha256})}`} download>导出声明</a></Button>}{data?.structure_available&&<Button variant="ghost" size="sm" asChild><a href={`${endpoint}/api/scene-ifc/design-package?${new URLSearchParams({space_id:space,catalog_sha256:catalogSha256})}`} download>下载资料包</a></Button>}</div></header>
  <dl className="grid grid-cols-2 md:grid-cols-4 gap-md text-body-small">{[['楼层','level'],['门','door'],['楼梯','stair'],['空间声明','space']].map(([label,key])=><div key={key}><dt className="text-muted-foreground">{label}</dt><dd>{data?.structure_available?data.declared_role_counts[key]||0:'—'}</dd></div>)}</dl>
  {error&&<div role="alert" className="flex items-center justify-between gap-md"><span>{error}</span><Button variant="outline" size="sm" onClick={()=>setRevision(v=>v+1)}>重新读取</Button></div>}
  {data&&!data.structure_available&&<p className="text-body-small text-muted-foreground">此目录尚未提供结构声明。</p>}
  {data?.structure_available&&<><p className="text-label-small text-muted-foreground">仅表示 IFC 原始归属与组成，不代表现场空间连接或本体关联。</p>
   {selectedId&&!entities.has(selectedId)&&<p className="text-body-small text-muted-foreground">该构件未纳入结构提取范围。</p>}
   {entities.has(selectedId||'')&&(edges.length?<ul className="flex flex-col gap-sm">{edges.slice(0,20).map((r,index)=><li key={`${r.ifc_relation_id}:${index}`} className="flex flex-wrap items-center gap-xs text-body-small">{node(r.source_id)}<span className="text-label-small text-muted-foreground">{relations[r.kind]} →</span>{node(r.target_id)}</li>)}</ul>:<p className="text-body-small text-muted-foreground">当前构件没有已提取的结构关系。</p>)}
   {edges.length>20&&<p className="text-label-small text-muted-foreground">显示前 20 项，共 {edges.length} 项。</p>}
   {selectedId&&entities.get(selectedId)?.geometry_status==='extracted'&&<Button variant="ghost" size="sm" className="self-start" asChild><a href={`${endpoint}/api/scene-ifc/element-geometry?${new URLSearchParams({space_id:space,catalog_sha256:catalogSha256,element_id:entities.get(selectedId)!.element_id})}`} download>导出构件网格</a></Button>}
   {selectedId&&entities.get(selectedId)?.source_role==='door'&&<IfcOpeningObservation key={`${space}:${catalogSha256}:${selectedId}`} space={space} pin={catalogSha256} element={entities.get(selectedId)!.element_id}/>}
   <IfcTypeProposals key={`${space}:${catalogSha256}`} space={space} pin={catalogSha256} sources={data.entities} selectedId={selectedId}/>
  </>}
 </section>;
}
