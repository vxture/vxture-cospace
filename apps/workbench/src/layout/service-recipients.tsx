import React,{useEffect,useId,useRef,useState} from 'react';
import {Button,Checkbox,Drawer,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,Input,NativeSelect,StatusBadge,Tabs,TabsContent,TabsList,TabsTrigger} from '@vxture/design-system';
import {AirplaneTilt,PawPrint,Car,Robot,PersonSimpleWalk,Shapes,Plus,MagnifyingGlass,ArrowsClockwise,SquaresFour,ListBullets,Check,ArrowRight,X} from '@phosphor-icons/react';
import {businessEndpoint} from './business-endpoint';
import {usePlatformSession} from './platform-auth';
import './service-recipients.css';

const forms={aerial:{label:'飞行式',example:'无人机',icon:AirplaneTilt},quadruped:{label:'四足式',example:'机器狗、四足机器人',icon:PawPrint},wheeled:{label:'轮式',example:'轮式机器人、移动底盘',icon:Car},tracked:{label:'履带式',example:'履带机器人',icon:Robot},humanoid:{label:'人形式',example:'人形机器人',icon:PersonSimpleWalk},other:{label:'其他形态',example:'其他足式、复合移动等',icon:Shapes}};
type Morphology=keyof typeof forms;
type Purpose='collect'|'use';
type UsageMode='online'|'offline';
type Relation={space_id:string;purposes:Purpose[];usage_modes:UsageMode[]};
type Draft={name:string;morphology:Morphology|'';morphology_note:string;manufacturer:string;model:string;external_id:string;contact:string;relations:Relation[]};
type Recipient=Omit<Draft,'morphology'>&{morphology:Morphology;id:string;revision:number;created_at:string;updated_at:string;can_manage:boolean};
type Space={id:string;name:string;can_manage:boolean};
type Directory={recipients:Recipient[];spaces:Space[];can_create:boolean;total:number;offset:number;limit:number};
const purposeNames={collect:'空间数据采集',use:'空间服务使用'};
const blank=():Draft=>({name:'',morphology:'',morphology_note:'',manufacturer:'',model:'',external_id:'',contact:'',relations:[]});
const time=(value:string)=>new Date(value).toLocaleString('zh-CN',{hour12:false});

export function ServiceRecipients({spaceId='',revision=0}:{spaceId?:string;revision?:number}){
 const session=usePlatformSession();
 const scope=[session?.user?.org_id,session?.user?.workspace_id,session?.user?.subject].join(':');
 return <RecipientWorkspace key={scope+':'+spaceId} spaceId={spaceId} revision={revision} csrf={session?.csrf||''}/>;
}

function RecipientWorkspace({spaceId,revision,csrf}:{spaceId:string;revision:number;csrf:string}){
 const [data,setData]=useState<Directory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const [query,setQuery]=useState(''),[morphology,setMorphology]=useState(''),[purpose,setPurpose]=useState(''),[scene,setScene]=useState(''),[offset,setOffset]=useState(0);
 const [detail,setDetail]=useState<Recipient|null>(null),[editor,setEditor]=useState<{record?:Recipient;draft:Draft}|null>(null),[notice,setNotice]=useState('');
 const [linkExisting,setLinkExisting]=useState(false),[view,setView]=useState<'cards'|'list'>('list');
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');setDetail(null);
  const params=new URLSearchParams({offset:String(offset),limit:'20'});
  if(spaceId||scene)params.set('space_id',spaceId||scene);
  if(query)params.set('q',query);if(morphology)params.set('morphology',morphology);if(purpose)params.set('purpose',purpose);
  fetch(`${businessEndpoint}/api/service-recipients?${params}`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'当前账号无权查看这些服务对象。':'服务对象暂不可读取，请重试。');
   const value=await r.json();if(value.profile!=='cospace.service-recipients/0.1'||!Array.isArray(value.recipients)||!Array.isArray(value.spaces))throw Error('服务对象数据格式无法识别。');
   if(!controller.signal.aborted)setData(value);
  }).catch(e=>{if(!controller.signal.aborted){setData(null);setError(e.message);}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[spaceId,scene,query,morphology,purpose,offset,refresh,revision]);
 const fixedSpace=data?.spaces.find(s=>s.id===spaceId);
 const canCreate=!!data?.can_create&&(!spaceId||!!fixedSpace?.can_manage);
 const openCreate=()=>{setLinkExisting(false);setEditor({draft:{...blank(),relations:spaceId?[{space_id:spaceId,purposes:[],usage_modes:[]}]:[]}});setNotice('');};
 function edit(record:Recipient){setDetail(null);setEditor({record,draft:{name:record.name,morphology:record.morphology,morphology_note:record.morphology_note,manufacturer:record.manufacturer,model:record.model,external_id:record.external_id,contact:record.contact,relations:structuredClone(record.relations)}});}
 return <section className="recipient-workspace" aria-label={spaceId?'此场景的服务对象':'智能体服务对象'}>
  <div className="recipient-operation-bar">
   <div className="recipient-view-group"><div className="recipient-view-switch" role="group" aria-label="显示方式"><Button variant="outline" size="icon-xl" aria-label="卡片视图" aria-pressed={view==='cards'} onClick={()=>setView('cards')}><SquaresFour size={16}/></Button><Button variant="outline" size="icon-xl" aria-label="列表视图" aria-pressed={view==='list'} onClick={()=>setView('list')}><ListBullets size={16}/></Button></div><span className="recipient-count" aria-live="polite">{loading?'正在读取…':error?'暂不可读':`${data?.total||0} 个智能体`}</span></div>
   <div className="recipient-operation-right"><div className="recipient-filter-group">
    <div className="recipient-search"><MagnifyingGlass size={16}/><Input aria-label="搜索智能体" placeholder="搜索名称、标识或厂家" maxLength={160} value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/></div>
    <NativeSelect wrapperClassName="recipient-filter-select" aria-label="设备形态" value={morphology} onChange={e=>{setMorphology(e.target.value);setOffset(0);}}><option value="">全部设备形态</option>{Object.entries(forms).map(([key,value])=><option value={key} key={key}>{value.label}</option>)}</NativeSelect>
    <NativeSelect wrapperClassName="recipient-filter-select" aria-label="接入用途" value={purpose} onChange={e=>{setPurpose(e.target.value);setOffset(0);}}><option value="">全部接入用途</option><option value="collect">空间数据采集</option><option value="use">空间服务使用</option></NativeSelect>
    {!spaceId&&<NativeSelect wrapperClassName="recipient-filter-select recipient-scene-select" aria-label="关联场景" value={scene} onChange={e=>{setScene(e.target.value);setOffset(0);}}><option value="">全部关联场景</option>{data?.spaces.map(s=><option value={s.id} key={s.id}>{s.name}</option>)}</NativeSelect>}
   </div>
   <div className="recipient-actions"><Button variant="outline" size="icon-xl" aria-label="刷新服务对象" onClick={()=>setRefresh(v=>v+1)}><ArrowsClockwise size={16}/></Button>{canCreate&&<Button size="xl" onClick={()=>spaceId?setLinkExisting(true):openCreate()}><Plus size={16}/>{spaceId?'关联智能体':'添加智能体'}</Button>}</div></div>
  </div>
  {notice&&<p role="status" className="recipient-notice">{notice}</p>}
  {loading?<p role="status" className="service-list-empty">正在读取服务对象…</p>:error?<div role="alert" className="service-list-empty"><p>{error}</p><Button variant="outline" onClick={()=>setRefresh(v=>v+1)}>重新加载</Button></div>:!data?.recipients.length?<div className="service-list-empty"><h2>{query||morphology||purpose||scene?'没有匹配的智能体':spaceId?'此场景尚未关联智能体':'尚未添加智能体'}</h2><p>登记设备形态与接入用途后，可继续配置厂家对接。登记不会自动开通服务权限。</p>{(query||morphology||purpose||scene||offset>0)&&<Button variant="outline" onClick={()=>{setQuery('');setMorphology('');setPurpose('');setScene('');setOffset(0);}}>清除筛选</Button>}</div>:<div className={view==='cards'?'recipient-card-grid':'recipient-list'}>{data.recipients.map(record=>{
   const links=record.relations.filter(r=>!spaceId||r.space_id===spaceId),purposes=[...new Set(links.flatMap(r=>r.purposes))];const Shape=forms[record.morphology].icon;
   const sceneNames=links.map(r=>data.spaces.find(s=>s.id===r.space_id)?.name||r.space_id).join('、');
   if(view==='cards')return <article className="recipient-tile" key={record.id}><div className="recipient-device-icon"><Shape size={24}/></div><div className="recipient-tile-body"><div className="recipient-card-heading"><strong title={record.name}>{record.name}</strong><span className="recipient-form-label">{forms[record.morphology].label}</span><span className="recipient-tile-status"><StatusBadge size="sm" tone="neutral">待厂家对接</StatusBadge></span></div><div className="recipient-card-summary"><span title={sceneNames}>{sceneNames||'未关联场景'}</span><div className="recipient-tags">{purposes.map(p=><StatusBadge size="sm" tone="neutral" key={p}>{purposeNames[p]}</StatusBadge>)}</div></div></div><Button variant="outline" size="icon-xl" aria-label={`查看${record.name}详情`} onClick={()=>setDetail(record)}><ArrowRight size={16}/></Button></article>;
   return <article className="recipient-row" key={record.id}>
    <div className="recipient-device-icon"><Shape size={24}/></div>
    <div className="recipient-card-content">
     <div className="recipient-card-heading"><strong title={record.name}>{record.name}</strong><span className="recipient-form-label">{forms[record.morphology].label}</span><div className="recipient-tags">{purposes.map(p=><StatusBadge size="sm" tone="neutral" key={p}>{purposeNames[p]}</StatusBadge>)}</div></div>
     <div className="recipient-card-summary"><span title={sceneNames}>{links.length?`关联场景：${sceneNames}`:'未关联场景'}</span>{(record.manufacturer||record.model)&&<span title={[record.manufacturer,record.model].filter(Boolean).join(' / ')}>{[record.manufacturer,record.model].filter(Boolean).join(' / ')}</span>}{record.external_id&&<span title={record.external_id}>设备标识：{record.external_id}</span>}</div>
    </div>
    <StatusBadge size="sm" tone="neutral">待厂家对接</StatusBadge>
    <Button variant="outline" size="xl" onClick={()=>setDetail(record)}>查看</Button>
   </article>;
  })}</div>}
  {!!data&&data.total>20&&!loading&&<div className="recipient-pagination"><Button variant="outline" size="sm" disabled={offset===0} onClick={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><span>{offset+1}–{Math.min(offset+20,data.total)} / {data.total}</span><Button variant="outline" size="sm" disabled={offset+20>=data.total} onClick={()=>setOffset(v=>v+20)}>下一页</Button></div>}
  <Drawer open={!!detail} onClose={()=>setDetail(null)} side="right" width="min(672px, 100vw)" title={detail?.name||'智能体详情'} closeLabel="关闭智能体详情">{detail&&<RecipientDetail record={detail} spaces={data?.spaces||[]} onEdit={()=>edit(detail)}/>}</Drawer>
  {editor&&<RecipientEditor key={editor.record?.id||'new'} initial={editor.draft} record={editor.record} spaces={data?.spaces||[]} csrf={csrf} onClose={()=>setEditor(null)} onSaved={()=>{setEditor(null);setNotice('已保存登记，接入尚未验证。');setRefresh(v=>v+1);}}/>}
  {linkExisting&&<LinkRecipient spaceId={spaceId} csrf={csrf} onCreate={openCreate} onClose={()=>setLinkExisting(false)} onSaved={()=>{setLinkExisting(false);setNotice('已关联智能体，接入用途已保存，实际授权仍需独立配置。');setRefresh(v=>v+1);}}/>}
 </section>;
}

function RecipientDetail({record,spaces,onEdit}:{record:Recipient;spaces:Space[];onEdit:()=>void}){
 const [tab,setTab]=useState('overview');
 return <div className="recipient-detail"><div className="recipient-actions"><StatusBadge tone="neutral">已登记</StatusBadge><StatusBadge tone="neutral">待厂家对接</StatusBadge>{record.can_manage&&<Button variant="outline" size="sm" onClick={onEdit}>编辑信息与关联</Button>}</div><p className="text-label-small text-muted-foreground">登记用途不授予实际服务权限，设备状态尚未验证。</p><Tabs value={tab} onValueChange={setTab}><TabsList aria-label="智能体详情"><TabsTrigger value="overview">概况</TabsTrigger><TabsTrigger value="spaces">关联空间</TabsTrigger><TabsTrigger value="integration">接入配置</TabsTrigger><TabsTrigger value="records">使用记录</TabsTrigger></TabsList><TabsContent value="overview"><dl className="recipient-facts">{[['智能体 ID',record.id],['设备形态',forms[record.morphology].label],['形态说明',record.morphology_note],['厂家',record.manufacturer],['型号',record.model],['外部设备标识',record.external_id],['负责人',record.contact],['登记时间',time(record.created_at)],['修改时间',time(record.updated_at)],['修订号',String(record.revision)]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||'未补充'}</dd></div>)}</dl></TabsContent><TabsContent value="spaces"><div className="recipient-relations">{!record.relations.length&&<p>尚未关联空间。</p>}{record.relations.map(r=><article key={r.space_id}><h3>{spaces.find(s=>s.id===r.space_id)?.name||r.space_id}</h3><div className="recipient-tags">{r.purposes.map(p=><StatusBadge key={p} tone="neutral">{purposeNames[p]}</StatusBadge>)}</div>{r.purposes.includes('use')&&<p>{r.usage_modes.length?r.usage_modes.map(m=>m==='online'?'在线服务':'离线成果').join('、'):'服务使用方式待配置'}</p>}<p className="text-label-small text-muted-foreground">用途已登记 · 接入授权未验证 · 实际使用版本未确认</p></article>)}</div></TabsContent><TabsContent value="integration"><h3>待厂家对接</h3><p>后续按厂家方案验证设备身份、数据格式、时间与坐标约定以及可用空间能力。</p><p className="text-body-small text-muted-foreground">外部设备标识当前为人工登记，尚未验证。现有平台调用身份不自动绑定为此智能体身份。</p></TabsContent><TabsContent value="records"><h3>暂无实例使用记录</h3><p>厂家接入并验证实例身份后，分别记录采集提交、在线请求、离线交付及应用版本。登记与下载不表示设备已使用成果。</p></TabsContent></Tabs></div>;
}

function CheckOption({checked,onChange,children}:{checked:boolean;onChange:(checked:boolean)=>void;children:React.ReactNode}){
 const id=useId();return <div className="recipient-check"><Checkbox id={id} checked={checked} onCheckedChange={value=>onChange(value===true)}/><label htmlFor={id}>{children}</label></div>;
}

function RelationChoices({relations,spaces,onChange}:{relations:Relation[];spaces:Space[];onChange:(value:Relation[])=>void}){
 const manageable=spaces.filter(s=>s.can_manage);
 const [activeId,setActiveId]=useState(relations[0]?.space_id||'');
 const active=manageable.find(s=>s.id===activeId),relation=relations.find(r=>r.space_id===activeId);
 function choose(id:string){setActiveId(id);if(!relations.some(r=>r.space_id===id))onChange([...relations,{space_id:id,purposes:[],usage_modes:[]}]);}
 function change(value:Relation){onChange(relations.map(r=>r.space_id===value.space_id?value:r));}
 function toggle(p:Purpose,enabled:boolean){if(!relation)return;change({...relation,purposes:enabled?[...relation.purposes,p]:relation.purposes.filter(v=>v!==p),usage_modes:p==='use'&&!enabled?[]:relation.usage_modes});}
 return <div className="recipient-scene-config">
  <section className="recipient-scene-picker" aria-label="选择关联场景"><div className="recipient-config-title"><strong>选择场景</strong><span>已选 {relations.length} 个</span></div><p>点击场景后，在右侧配置用途。</p><div className="recipient-scene-options">{manageable.map(s=>{const selected=relations.find(r=>r.space_id===s.id);return <Button type="button" variant="outline" className="recipient-scene-option" aria-pressed={activeId===s.id} key={s.id} onClick={()=>choose(s.id)}><span className="recipient-scene-name">{s.name}</span>{selected?<span className="recipient-scene-state"><Check size={14}/>{selected.purposes.length?'已配置':'待选用途'}</span>:<Plus size={16}/>}</Button>;})}</div>{!manageable.length&&<p>暂无可管理的场景，可先保存设备信息。</p>}</section>
  <section className="recipient-purpose-panel" aria-label="配置场景用途">{active&&relation?<><div className="recipient-config-title"><strong>{active.name}</strong><Button type="button" variant="ghost" size="sm" aria-label={`移除场景${active.name}`} onClick={()=>{onChange(relations.filter(r=>r.space_id!==activeId));setActiveId('');}}><X size={14}/>移除关联</Button></div><p>这个设备将在此场景做什么？可同时选择两项。</p><div className="recipient-purpose-cards">{(['collect','use'] as const).map(p=><div className="recipient-purpose-card" data-selected={relation.purposes.includes(p)} key={p}><CheckOption checked={relation.purposes.includes(p)} onChange={checked=>toggle(p,checked)}><strong>{purposeNames[p]}</strong><span>{p==='collect'?'设备 → CoSpace':'CoSpace → 设备'}</span><span>{p==='collect'?'回传观测数据，用于空间建图与更新。':'获取空间底图与查询服务，支撑定位、导航等作业。'}</span></CheckOption></div>)}</div>{relation.purposes.includes('use')&&<div className="recipient-service-modes"><div className="recipient-config-title"><strong>服务使用方式</strong><span>选填，可稍后配置</span></div><div className="recipient-mode-options">{(['online','offline'] as const).map(mode=><CheckOption key={mode} checked={relation.usage_modes.includes(mode)} onChange={checked=>change({...relation,usage_modes:checked?[...relation.usage_modes,mode]:relation.usage_modes.filter(m=>m!==mode)})}><strong>{mode==='online'?'在线服务':'离线成果'}</strong><span>{mode==='online'?'作业时请求空间服务':'预先获取成果，在设备侧使用'}</span></CheckOption>)}</div></div>}<p className="recipient-purpose-summary" role="status">{relation.purposes.length?`已选用途：${relation.purposes.map(p=>purposeNames[p]).join('、')}`:'请选择至少一项用途，或移除此场景关联。'}</p></>:<div className="recipient-config-empty"><Shapes size={32}/><strong>选择设备要作业的场景</strong><p>每个场景可配置不同用途，也可以暂不关联。</p></div>}</section>
 </div>;
}

function requestId(){return crypto.randomUUID().replaceAll('-','');}
async function saveRecipient(draft:Draft,record:Recipient|undefined,csrf:string,id:string){
 const response=await fetch(`${businessEndpoint}/api/service-recipients${record?'/'+record.id:''}`,{method:record?'PATCH':'POST',headers:{'Content-Type':'application/json','X-CoSpace-CSRF':csrf},body:JSON.stringify({...draft,request_id:id,expected_revision:record?.revision||0})});
 if(!response.ok)throw Error(response.status===409?'登记已发生变化或提交编号冲突。请关闭面板并刷新后重试。':response.status===403?'无权修改此智能体或所选场景，请刷新权限后重试。':response.status===422?'请检查名称、设备形态和每个场景的接入用途。':'保存暂未确认，请保留当前内容重试。');
 return await response.json() as Recipient;
}

function RecipientEditor({initial,record,spaces,csrf,onClose,onSaved}:{initial:Draft;record?:Recipient;spaces:Space[];csrf:string;onClose:()=>void;onSaved:()=>void}){
 const [draft,setDraft]=useState(initial),[step,setStep]=useState(1),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const prefix=useId(),pending=useRef<{body:string;id:string}|null>(null),mounted=useRef(true),saving=useRef(false);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 function set<K extends keyof Draft>(key:K,value:Draft[K]){setDraft(previous=>({...previous,[key]:value}));setError('');}
 function next(){if(!draft.morphology||!draft.name.trim()||draft.morphology==='other'&&!draft.morphology_note.trim()){setError('请选择设备形态，填写名称；其他形态需补充说明。');return;}setError('');setStep(2);}
 async function save(){
  if(saving.current)return;
  if(draft.relations.some(r=>!r.purposes.length)){setError('请为每个已关联场景至少选择一项接入用途，或取消该场景的关联。');return;}
  saving.current=true;setBusy(true);setError('');
  const body=JSON.stringify(draft);if(pending.current?.body!==body)pending.current={body,id:requestId()};
  try{await saveRecipient(draft,record,csrf,pending.current!.id);if(mounted.current)onSaved();}catch(e){if(mounted.current)setError((e as Error).message);}finally{saving.current=false;if(mounted.current)setBusy(false);}
 }
 return <Dialog open onOpenChange={open=>{if(!open&&!busy)onClose();}}><DialogContent className="recipient-editor-dialog" onEscapeKeyDown={e=>{if(busy)e.preventDefault();}} onInteractOutside={e=>e.preventDefault()}><DialogHeader><DialogTitle>{record?'编辑智能体':'添加智能体'}</DialogTitle><DialogDescription>登记设备形态与作业用途，厂家接口可在后续接入。</DialogDescription></DialogHeader>
  <form className="recipient-editor" onSubmit={e=>{e.preventDefault();if(step===1)next();else void save();}}>
   <ol className="recipient-steps" aria-label="登记步骤"><li aria-current={step===1?'step':undefined} data-complete={step>1}><span>{step>1?<Check size={16}/>:1}</span><div><strong>设备信息</strong><small>选择形态，填写基本信息</small></div></li><li aria-current={step===2?'step':undefined}><span>2</span><div><strong>场景与用途</strong><small>按场景配置，可稍后关联</small></div></li></ol>
   <div className="recipient-editor-body"><fieldset disabled={busy}>
   {step===1?<><legend className="sr-only">设备信息</legend><div className="recipient-field"><span id={prefix+'-shape'}>设备形态 <span aria-hidden="true">*</span></span><div className="recipient-morphologies" role="radiogroup" aria-labelledby={prefix+'-shape'}>{Object.entries(forms).map(([key,value])=>{const Shape=value.icon;return <Button type="button" variant="outline" role="radio" aria-checked={draft.morphology===key} className="recipient-morphology" key={key} onClick={()=>set('morphology',key as Morphology)}><Shape size={24}/><div><strong>{value.label}</strong><span>{value.example}</span></div>{draft.morphology===key&&<Check size={16}/>}</Button>;})}</div></div><div className="recipient-information-grid">{([['name','设备名称 *',100],...(draft.morphology==='other'?[['morphology_note','形态说明 *',200]]:[]),['manufacturer','厂家',100],['model','型号',100],['external_id','外部设备标识',160],['contact','负责人',100]] as [keyof Omit<Draft,'relations'>,string,number][]).map(([key,label,max])=><div className="recipient-field" key={key}><label htmlFor={prefix+'-'+key}>{label}</label><Input id={prefix+'-'+key} placeholder={key==='name'?'例如：园区巡检机器狗 01':'选填'} value={draft[key]} maxLength={max} required={key==='name'||key==='morphology_note'} onChange={e=>set(key,e.target.value)}/></div>)}</div></>:<><legend className="sr-only">场景与用途</legend><div className="recipient-device-summary"><strong>{draft.name}</strong><span>{draft.morphology?forms[draft.morphology].label:''}</span><span>场景关联为选填，后续可继续配置。</span></div><RelationChoices spaces={spaces} relations={draft.relations} onChange={value=>set('relations',value)}/></>}
   </fieldset></div>
   {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
   <div className="recipient-editor-footer"><span className="recipient-footer-note">{step===1?'* 为必填项':draft.relations.length?`已关联 ${draft.relations.length} 个场景 · 登记后待厂家对接`:'暂不关联场景，仅保存设备信息'}</span><Button size="xl" type="button" variant="outline" disabled={busy} onClick={onClose}>取消</Button>{step===2&&<Button size="xl" type="button" variant="outline" disabled={busy} onClick={()=>setStep(1)}>上一步</Button>}<Button size="xl" type="submit" disabled={busy}>{busy?'正在保存…':step===1?'下一步：场景与用途':draft.relations.length?'保存登记':'仅保存设备'}</Button></div>
  </form></DialogContent></Dialog>;

}

function LinkRecipient({spaceId,csrf,onCreate,onClose,onSaved}:{spaceId:string;csrf:string;onCreate:()=>void;onClose:()=>void;onSaved:()=>void}){
 const [items,setItems]=useState<Recipient[]>([]),[spaces,setSpaces]=useState<Space[]>([]),[query,setQuery]=useState(''),[selected,setSelected]=useState<Recipient|null>(null),[relations,setRelations]=useState<Relation[]>([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const pending=useRef<{body:string;id:string}|null>(null),saving=useRef(false),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');fetch(`${businessEndpoint}/api/service-recipients?${new URLSearchParams({q:query,limit:'100'})}`,{cache:'no-store',signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('智能体列表暂不可读取。');const value:Directory=await r.json();if(!controller.signal.aborted){setItems(value.recipients);setSpaces(value.spaces);}}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[query]);
 async function save(){if(!selected||saving.current)return;if(!relations.length||relations.some(r=>!r.purposes.length)){setError('请选择此场景的接入用途。');return;}saving.current=true;setBusy(true);setError('');const draft:Draft={name:selected.name,morphology:selected.morphology,morphology_note:selected.morphology_note,manufacturer:selected.manufacturer,model:selected.model,external_id:selected.external_id,contact:selected.contact,relations:[...selected.relations.filter(r=>r.space_id!==spaceId),...relations]};const body=JSON.stringify(draft);if(pending.current?.body!==body)pending.current={body,id:requestId()};try{await saveRecipient(draft,selected,csrf,pending.current!.id);if(mounted.current)onSaved();}catch(e){if(mounted.current)setError((e as Error).message);}finally{saving.current=false;if(mounted.current)setBusy(false);}}
 return <Drawer open onClose={()=>{if(!busy)onClose();}} side="right" width="min(672px, 100vw)" title="关联智能体" closeLabel="关闭关联面板"><div className="recipient-editor">{selected?<><h3>{selected.name}</h3><RelationChoices spaces={spaces.filter(s=>s.id===spaceId)} relations={relations} onChange={setRelations}/><p className="text-label-small text-muted-foreground">仅调整此场景的用途，其他场景登记保持不变。</p></>:<><div className="recipient-toolbar"><Input aria-label="搜索已登记智能体" placeholder="搜索已登记智能体" maxLength={160} value={query} onChange={e=>setQuery(e.target.value)}/><Button variant="outline" onClick={onCreate}>添加智能体</Button></div>{loading?<p role="status">正在读取…</p>:<div className="recipient-existing">{items.filter(r=>r.can_manage).map(record=><Button variant="outline" key={record.id} onClick={()=>{setSelected(record);setRelations(structuredClone(record.relations.filter(r=>r.space_id===spaceId)));}}>{record.name} · {forms[record.morphology].label}{record.relations.some(r=>r.space_id===spaceId)?' · 已关联，编辑用途':''}</Button>)}{!items.some(r=>r.can_manage)&&<p>暂无可管理的匹配智能体，可添加新智能体。</p>}<p className="text-label-small text-muted-foreground">最多展示 100 个匹配结果，请输入名称或标识缩小范围。修改共享智能体需具备其全部关联场景的管理权限。</p></div>}</>}{error&&<p role="alert" className="text-destructive text-body-small">{error}</p>}<div className="recipient-editor-footer"><Button variant="ghost" disabled={busy} onClick={onClose}>取消</Button>{selected&&<><Button variant="outline" disabled={busy} onClick={()=>setSelected(null)}>重新选择</Button><Button disabled={busy} onClick={()=>void save()}>{busy?'正在保存…':'保存关联'}</Button></>}</div></div></Drawer>;
}
