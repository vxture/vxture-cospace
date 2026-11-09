import {subscribeAppLocation} from './app-router';
import {appNavigate} from './app-router';
import {useRecordNavigation} from './record-navigation';
import {businessEndpoint} from './business-endpoint';
import {OntologyAuthoring,type RuleDocument} from './ontology-authoring';
import {OntologyComparison} from './ontology-comparison';
import {OntologyUsage} from './ontology-usage';
import React,{useEffect,useRef,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent,NativeSelect,Textarea,StatusBadge,Table,TableHeader,TableBody,TableRow,TableHead,TableCell} from '@vxture/design-system';

const endpoint=businessEndpoint;
type Version={ontology_id:string;version:string;sha256:string;title:string;type_count:number;registered_at:string};
type Rule={title:string;type:'string';required:boolean;min_length:number;max_length:number};
type Definition={relations?:Record<string,{title:string;source_types:string[];target_types:string[];family:string;symmetric:boolean}>;title:string;description:string;types:Record<string,{title:string;description:string;properties:Record<string,Rule>}>};
type Loaded={record:Version;definition:Definition;integrity:string};
type Result={ontology_ref:{ontology_id:string;version:string;sha256:string};status:'passed'|'failed';object_count:number;checked_at:string;issues:{code:string;path:string;object_id:string|null;message:string}[]};
const key=(r:Pick<Version,'ontology_id'|'version'|'sha256'>)=>`${r.ontology_id}/${r.version}/${r.sha256}`;
function readReference(){
 const p=new URLSearchParams(location.search);
 return {ontology_id:p.get('ontology_id')||'',version:p.get('ontology_version')||'',sha256:p.get('ontology_sha256')||''};
}
function message(code:string){
 return ({ontology_not_found:'该本体版本不存在。',ontology_reference_mismatch:'本体摘要与固定引用不一致，请核对后重新选择。',ontology_integrity_changed:'已封存规则内容不完整或被修改，已停止读取和校验。',ontology_store_not_configured:'本体规则库尚未配置。',ontology_definition_invalid:'本体规则结构无效。'} as Record<string,string>)[code]||'本体服务读取失败，请检查本机服务后重试。';
}
export function OntologyWorkbench(){
 const target=useRecordNavigation();
 const rules=target.tab==='rules'||!target.tab&&new URLSearchParams(location.search).has('ontology_id');
 const [versions,setVersions]=useState<Version[]>([]),[reference,setReference]=useState(readReference),[loaded,setLoaded]=useState<Loaded|null>(null);
 const [listing,setListing]=useState(false),[reading,setReading]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [text,setText]=useState(''),[result,setResult]=useState<Result|null>(null),[checkError,setCheckError]=useState(''),[busy,setBusy]=useState(false);
 const validation=useRef<AbortController|null>(null);
 const referenceKey=key(reference);
 useEffect(()=>{const update=()=>setReference(readReference());return subscribeAppLocation(update);},[]);
 useEffect(()=>{
  const controller=new AbortController();setListing(true);setVersions([]);setError('');
  fetch(`${endpoint}/api/ontologies`,{signal:controller.signal}).then(async r=>{const body=await r.json();if(!r.ok)throw Error(message(body.detail));return body.ontologies as Version[];}).then(items=>{if(!controller.signal.aborted)setVersions(items);}).catch(e=>{if(!controller.signal.aborted){setError(e.message);setLoaded(null);setResult(null);}}).finally(()=>{if(!controller.signal.aborted)setListing(false);});
  return()=>controller.abort();
 },[revision]);
 useEffect(()=>{
  const controller=new AbortController();validation.current?.abort();setBusy(false);setResult(null);setCheckError('');setLoaded(null);setReading(false);setError('');
  if(!reference.ontology_id||!reference.version||!reference.sha256)return()=>controller.abort();
  if(!/^[a-z][a-z0-9-]{0,63}$/.test(reference.ontology_id)||!/^\d{1,4}\.\d{1,4}\.\d{1,4}$/.test(reference.version)||!/^[a-f0-9]{64}$/.test(reference.sha256)){setError('固定规则引用格式无效。');return()=>controller.abort();}
  if(!versions.length)return()=>controller.abort();
  const authorized=versions.find(v=>key(v)===referenceKey);
  if(!authorized){setError('固定规则不在当前授权版本目录中。');return()=>controller.abort();}
  setReading(true);
  fetch(`${endpoint}/api/ontologies/${encodeURIComponent(authorized.ontology_id)}/${encodeURIComponent(authorized.version)}?${new URLSearchParams({sha256:authorized.sha256})}`,{signal:controller.signal}).then(async r=>{const body=await r.json();if(!r.ok)throw Error(message(body.detail));if(key(body.record)!==referenceKey||body.integrity!=='verified')throw Error('规则响应与所选版本不一致。');return body as Loaded;}).then(body=>{if(!controller.signal.aborted)setLoaded(body);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setReading(false);});
  return()=>{controller.abort();validation.current?.abort();};
 },[referenceKey,revision,versions]);
 function choose(value:string){
  const record=versions.find(v=>key(v)===value);const params=new URLSearchParams(location.search);
  for(const name of ['ontology_id','ontology_version','ontology_sha256'])params.delete(name);
  if(record){params.set('ontology_id',record.ontology_id);params.set('ontology_version',record.version);params.set('ontology_sha256',record.sha256);}
  setError('');appNavigate('ontology'+(params.size?'?'+params:''));
 }
 function draft(value:string){validation.current?.abort();setBusy(false);setText(value);setResult(null);setCheckError('');}
 async function inspect(){
  if(!loaded||busy)return;setResult(null);setCheckError('');
  let objects:unknown;try{objects=JSON.parse(text);if(!Array.isArray(objects)||objects.length<1||objects.length>100)throw Error();}catch{setCheckError('请输入包含1至100个对象的JSON数组。');return;}
  const controller=new AbortController();validation.current?.abort();validation.current=controller;setBusy(true);
  try{
   const record=loaded.record;
   const r=await fetch(`${endpoint}/api/ontologies/${record.ontology_id}/${record.version}/validate`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({sha256:record.sha256,objects})});
   const body=await r.json();if(!r.ok){const detail=r.status===422?'草稿请求格式不符合要求，请检查对象结构。':message(body.detail);if(r.status!==422){setLoaded(null);setError(detail);}throw Error(detail);}
   if(key(body.ontology_ref)!==key(record))throw Error('校验结果的本体引用不一致。');
   if(!controller.signal.aborted)setResult(body);
  }catch(e){if(!controller.signal.aborted){setCheckError(e instanceof Error?e.message:'校验失败');setResult(null);}}
  finally{if(!controller.signal.aborted)setBusy(false);}
 }
 const current=loaded?.record;
 return <div className="flex flex-col gap-xl">
  <div hidden={rules}><OntologyAuthoring endpoint={endpoint} source={loaded?.definition as unknown as RuleDocument||null} onSealed={record=>{setRevision(v=>v+1);const params=new URLSearchParams(location.search);params.set('ontology_id',record.ontology_id);params.set('ontology_version',record.version);params.set('ontology_sha256',record.sha256);appNavigate('ontology?'+params);}}/>
  </div><div hidden={!rules} className="flex flex-col gap-xl"><div className="flex flex-wrap items-center justify-between gap-md"><p className="text-body-small text-muted-foreground">查看固定版本的类型与关系规则，校验对象草稿。预置模板及当前 Workspace 的规则可供其多个场景引用。</p><Button variant="outline" disabled={listing||reading||busy} onClick={()=>setRevision(n=>n+1)}>刷新规则库</Button></div>
  <Card className="module-surface" aria-label="本体版本"><CardHeader><CardTitle>本体版本</CardTitle></CardHeader><CardContent className="flex flex-col gap-md">
   <NativeSelect aria-label="选择本体版本" value={versions.some(v=>key(v)===referenceKey)?referenceKey:''} onChange={e=>choose(e.target.value)} disabled={listing||busy}><option value="">{listing?'读取版本中…':'请选择固定本体版本'}</option>{versions.map(v=><option key={key(v)} value={key(v)}>{v.title} · V{v.version}</option>)}</NativeSelect>
   {error&&<p role="alert">{error}</p>}{!listing&&!error&&!versions.length&&<p role="status" className="text-body-small text-muted-foreground">尚无封存本体版本，请由工程师配置规则源后启动服务。</p>}
   {reading&&<p role="status">正在核对规则摘要…</p>}
   {current&&!error&&<><div className="flex flex-wrap items-center gap-sm"><StatusBadge tone="success">规则完整性已核对</StatusBadge><span className="text-body-small">{current.ontology_id} · V{current.version} · {current.type_count} 种类型</span></div><p className="break-all text-label-small text-muted-foreground">SHA256：{current.sha256}</p><p className="text-label-small text-muted-foreground">封存于 {new Date(current.registered_at).toLocaleString('zh-CN',{hour12:false})} · 场景及模型显式引用固定版本</p></>}
  </CardContent></Card>
  {loaded&&!error&&<OntologyUsage key={referenceKey} endpoint={endpoint} reference={loaded.record}/>}
  {loaded&&!error&&<OntologyComparison key={referenceKey} endpoint={endpoint} current={loaded as unknown as Parameters<typeof OntologyComparison>[0]['current']} versions={versions}/>}
  {loaded&&!error&&<div className="grid min-w-0 grid-cols-1 items-start gap-xl xl:grid-cols-2">
   <Card aria-label="类型与属性规则"><CardHeader><CardTitle>类型与属性</CardTitle></CardHeader><CardContent className="flex min-w-0 flex-col gap-lg"><p className="text-body-small text-muted-foreground">{loaded.definition.description}</p>{Object.entries(loaded.definition.types).map(([id,type])=><section key={id} className="flex min-w-0 flex-col gap-sm border-b border-border pb-lg"><h3 className="text-body-small font-medium">{type.title} <span className="font-normal text-muted-foreground">{id}</span></h3><p className="text-label-small text-muted-foreground">{type.description}</p><div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>属性</TableHead><TableHead>类型</TableHead><TableHead>要求</TableHead></TableRow></TableHeader><TableBody>{Object.entries(type.properties).map(([name,rule])=><TableRow key={name}><TableCell>{rule.title}<span className="ml-sm text-label-small text-muted-foreground">{name}</span></TableCell><TableCell>字符串</TableCell><TableCell>{rule.required?'必填':'选填'} · {rule.min_length}–{rule.max_length} 字</TableCell></TableRow>)}</TableBody></Table></div></section>)}<Button asChild variant="link" className="self-start"><a href={`${endpoint}/api/ontologies/${current!.ontology_id}/${current!.version}?sha256=${current!.sha256}`} target="_blank" rel="noopener noreferrer">查看规则JSON</a></Button></CardContent></Card>
   {loaded.definition.relations&&<Card aria-label="本体关系规则"><CardHeader><CardTitle>关系规则</CardTitle></CardHeader><CardContent className="flex min-w-0 flex-col gap-lg">{Object.entries(loaded.definition.relations).map(([id,r])=><section key={id} className="break-all border-b border-border pb-md"><h3 className="text-body-small font-medium">{r.title} · {id}</h3><p className="mt-sm text-label-small text-muted-foreground">来源：{r.source_types.map(t=>loaded.definition.types[t]?.title||t).join("、")}；目标：{r.target_types.map(t=>loaded.definition.types[t]?.title||t).join("、")}</p><p className="mt-sm text-label-small text-muted-foreground">{r.symmetric?"无向连接，反向重复拒绝；不表示可通行。":"有向归属；包含与位于统一检查单一父空间、循环及反向等价重复。"}</p></section>)}<p className="text-label-small text-muted-foreground">通用规则：端点存在、类型匹配、禁止自身关系。实例在空间关联创建，规则通过不代表现场语义已确认。</p></CardContent></Card>}
   <Card aria-label="对象草稿校验"><CardHeader><CardTitle>对象草稿校验</CardTitle></CardHeader><CardContent className="flex flex-col gap-md"><p className="text-body-small text-muted-foreground">仅检查类型、ID及属性规则，不保存对象，不确认位置或现场语义。草稿校验不修改已有模型或发布。</p><label htmlFor="ontology-draft" className="text-body-small">对象数组 JSON</label><Textarea id="ontology-draft" aria-label="对象草稿JSON" rows={12} className="font-mono text-body-small" maxLength={64000} value={text} onChange={e=>draft(e.target.value)} placeholder="输入对象草稿，或填入下方校验示例"/><div className="flex flex-wrap gap-sm"><Button disabled={busy||!text.trim()} onClick={inspect}>{busy?'校验中…':'校验草稿'}</Button><Button variant="outline" disabled={busy} onClick={()=>draft(JSON.stringify([{object_id:'draft-cabinet-01',type_id:'cabinet',properties:{name:'待确认柜体（校验草稿）'}}],null,2))}>填入校验示例</Button></div>{checkError&&<p role="alert">{checkError}</p>}{result&&<section aria-label="草稿校验结果" className="flex flex-col gap-md border-t border-border pt-md"><div className="flex flex-wrap items-center gap-sm"><StatusBadge tone={result.status==='passed'?'success':'danger'}>{result.status==='passed'?'规则校验通过':'规则校验未通过'}</StatusBadge><span className="text-label-small text-muted-foreground">{result.object_count} 个草稿 · {result.issues.length} 个问题</span></div><p className="text-label-small text-muted-foreground">{new Date(result.checked_at).toLocaleString('zh-CN',{hour12:false})} · V{result.ontology_ref.version} · 未保存，现场语义未确认</p>{result.issues.map((issue,i)=><div key={i} className="flex flex-col gap-xs border-b border-border pb-sm"><p className="text-body-small">{issue.object_id||'ID未填写'}：{issue.message}</p><p className="break-all text-label-small text-muted-foreground">{issue.path} · {issue.code}</p></div>)}</section>}</CardContent></Card>
  </div>}
 </div></div>;
}
