import React,{useEffect,useId,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {ViewModeSwitch,Button,Checkbox,Drawer,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,Input,NativeSelect,StatusBadge} from '@vxture/design-system';
import {AirplaneTilt,PawPrint,Car,Robot,PersonSimpleWalk,Shapes,Plus,MagnifyingGlass,ArrowsClockwise,Check,Info,LinkSimple,PlugsConnected,ClockCounterClockwise,X} from '@phosphor-icons/react';
import {WorkspaceHeading} from './workspace-frame';
import {businessEndpoint} from './business-endpoint';
import {usePlatformSession} from './platform-auth';
import {ServiceDirectoryRow} from './service-directory-row';
import {DeviceArtwork} from './device-artwork';
import {ServiceCard,ServiceCardActions} from './service-card';
import {devicePageHref,deviceTabs,type DeviceTab} from './service-workspace-contract';
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
type EditSection='information'|'relations';
const blank=():Draft=>({name:'',morphology:'',morphology_note:'',manufacturer:'',model:'',external_id:'',contact:'',relations:[]});
const time=(value:string)=>new Date(value).toLocaleString('zh-CN',{hour12:false});

export function ServiceRecipients({spaceId='',revision=0}:{spaceId?:string;revision?:number}){
 const session=usePlatformSession();
 const scope=[session?.user?.org_id,session?.user?.workspace_id,session?.user?.subject].join(':');
 return <RecipientWorkspace key={scope+':'+spaceId} spaceId={spaceId} revision={revision} csrf={session?.csrf||''}/>;
}

function RecipientWorkspace({spaceId,revision,csrf}:{spaceId:string;revision:number;csrf:string}){
 const [params]=useSearchParams();
 const deviceId=params.get('device')||'';
 const requestedTab=params.get('deviceTab')||'overview';
 const deviceTab:DeviceTab=Object.hasOwn(deviceTabs,requestedTab)?requestedTab as DeviceTab:'overview';
 const [data,setData]=useState<Directory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const [query,setQuery]=useState(''),[morphology,setMorphology]=useState(''),[purpose,setPurpose]=useState(''),[scene,setScene]=useState(''),[offset,setOffset]=useState(0);
 const [detail,setDetail]=useState<Recipient|null>(null),[overviewOpen,setOverviewOpen]=useState(false),[editor,setEditor]=useState<{record?:Recipient;draft:Draft;section?:EditSection}|null>(null),[notice,setNotice]=useState('');
 const [linkExisting,setLinkExisting]=useState(false),[view,setView]=useState<'cards'|'list'>('cards');
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');setOverviewOpen(false);setDetail(null);
  const request=new URLSearchParams({offset:String(deviceId?0:offset),limit:'20'});
  if(spaceId||(!deviceId&&scene))request.set('space_id',spaceId||scene);
  if(deviceId)request.set('q',deviceId.slice(0,160));
  else{if(query)request.set('q',query);if(morphology)request.set('morphology',morphology);if(purpose)request.set('purpose',purpose);}
  fetch(`${businessEndpoint}/api/service-recipients?${request}`,{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'当前账号无权查看这些设备。':'设备列表暂不可读取，请重试。');
   const value=await r.json();if(value.profile!=='cospace.service-recipients/0.1'||!Array.isArray(value.recipients)||!Array.isArray(value.spaces))throw Error('设备数据格式无法识别。');
   if(!controller.signal.aborted)setData(value);
  }).catch(e=>{if(!controller.signal.aborted){setData(null);setError(e.message);}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[spaceId,scene,query,morphology,purpose,offset,refresh,revision,deviceId]);
 const fixedSpace=data?.spaces.find(s=>s.id===spaceId);
 const canCreate=!!data?.can_create&&(!spaceId||!!fixedSpace?.can_manage);
 const openCreate=()=>{setLinkExisting(false);setEditor({draft:{...blank(),relations:spaceId?[{space_id:spaceId,purposes:[],usage_modes:[]}]:[]}});setNotice('');};
 function edit(record:Recipient,section:EditSection){setDetail(null);setOverviewOpen(false);setEditor({record,section,draft:{name:record.name,morphology:record.morphology,morphology_note:record.morphology_note,manufacturer:record.manufacturer,model:record.model,external_id:record.external_id,contact:record.contact,relations:structuredClone(record.relations)}});}
 const deviceActions=(record:Recipient)=>Object.entries(deviceTabs).map(([key,label])=>{const Icon={overview:Info,spaces:LinkSimple,integration:PlugsConnected,records:ClockCounterClockwise}[key as DeviceTab];return {key,label,icon:<Icon size={16}/>,href:devicePageHref(record.id,key as DeviceTab,'/services?'+params)};});
 const editorPanel=editor&&<RecipientEditor key={editor.record?.id||'new'} initial={editor.draft} record={editor.record} section={editor.section} spaces={data?.spaces||[]} csrf={csrf} onClose={()=>setEditor(null)} onSaved={()=>{setEditor(null);setNotice('已保存登记，接入尚未验证。');setRefresh(v=>v+1);}}/>;
 if(deviceId){
  const record=data?.recipients.find(value=>value.id===deviceId);
  const Shape=record?forms[record.morphology].icon:Robot;
  return <section className="recipient-workspace recipient-device-page" aria-label="设备管理">
   {!spaceId&&<WorkspaceHeading icon={Shape} title={record?.name||'设备详情'} description={record?`智能设备 · ${forms[record.morphology].label}`:'智能设备'} secondary={record&&<StatusBadge size="sm" icon={false} tone="neutral">已登记</StatusBadge>}/>}
   {loading?<p role="status">正在读取设备…</p>:error?<div role="alert"><p>{error}</p><Button variant="outline" onClick={()=>setRefresh(value=>value+1)}>重试</Button></div>:record?<RecipientDetail record={record} spaces={data?.spaces||[]} onEdit={section=>edit(record,section)} activeSection={deviceTab}/>:<p role="alert">设备不可访问或已不存在。</p>}
   {notice&&<p role="status">{notice}</p>}{editorPanel}
  </section>;
 }
 return <section className="recipient-workspace" aria-label={spaceId?'此场景关联的设备':'智能设备'}>
  <div className="recipient-operation-bar">
   <div className="recipient-view-group"><ViewModeSwitch value={view} onChange={setView} ariaLabel="显示方式" labels={{cards:'卡片视图',list:'列表视图'}}/><span className="recipient-count" aria-live="polite">{loading?'正在读取…':error?'暂不可读':`${data?.total||0} 台设备`}</span></div>
   <div className="recipient-operation-right"><div className="recipient-filter-group">
    <div className="recipient-search"><MagnifyingGlass size={16}/><Input aria-label="搜索设备" placeholder="搜索名称、标识或厂家" maxLength={160} value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/></div>
    <NativeSelect wrapperClassName="recipient-filter-select" aria-label="设备形态" value={morphology} onChange={e=>{setMorphology(e.target.value);setOffset(0);}}><option value="">全部设备形态</option>{Object.entries(forms).map(([key,value])=><option value={key} key={key}>{value.label}</option>)}</NativeSelect>
    <NativeSelect wrapperClassName="recipient-filter-select" aria-label="接入用途" value={purpose} onChange={e=>{setPurpose(e.target.value);setOffset(0);}}><option value="">全部接入用途</option><option value="collect">空间数据采集</option><option value="use">空间服务使用</option></NativeSelect>
    {!spaceId&&<NativeSelect wrapperClassName="recipient-filter-select recipient-scene-select" aria-label="关联场景" value={scene} onChange={e=>{setScene(e.target.value);setOffset(0);}}><option value="">全部关联场景</option>{data?.spaces.map(s=><option value={s.id} key={s.id}>{s.name}</option>)}</NativeSelect>}
   </div>
   <div className="recipient-actions"><Button variant="outline" size="icon-xl" aria-label="刷新设备列表" onClick={()=>setRefresh(v=>v+1)}><ArrowsClockwise size={16}/></Button>{canCreate&&<Button size="xl" onClick={()=>spaceId?setLinkExisting(true):openCreate()}><Plus size={16}/>{spaceId?'关联设备':'添加设备'}</Button>}</div></div>
  </div>
  {notice&&<p role="status" className="recipient-notice">{notice}</p>}
  {loading?<p role="status" className="service-list-empty">正在读取设备…</p>:error?<div role="alert" className="service-list-empty"><p>{error}</p><Button variant="outline" onClick={()=>setRefresh(v=>v+1)}>重新加载</Button></div>:!data?.recipients.length?<div className="service-list-empty"><h2>{query||morphology||purpose||scene?'没有匹配的设备':spaceId?'此场景尚未关联设备':'尚未添加设备'}</h2><p>登记设备形态与接入用途后，可继续配置厂家对接。登记不会自动开通服务权限。</p>{(query||morphology||purpose||scene||offset>0)&&<Button variant="outline" onClick={()=>{setQuery('');setMorphology('');setPurpose('');setScene('');setOffset(0);}}>清除筛选</Button>}</div>:<div className={view==='cards'?'recipient-card-grid':'service-directory-list'}>{data.recipients.map(record=>{
   const links=record.relations.filter(r=>!spaceId||r.space_id===spaceId),purposes=[...new Set(links.flatMap(r=>r.purposes))];const Shape=forms[record.morphology].icon;
   const sceneNames=links.map(r=>data.spaces.find(s=>s.id===r.space_id)?.name||r.space_id).join('、');
   const controls=<ServiceCardActions label={record.name} items={deviceActions(record)}/>;
   if(view==='cards')return <ServiceCard key={record.id} label={record.name} symbol={<Shape size={26} weight="duotone"/>} artwork={<DeviceArtwork morphology={record.morphology}/>}
    heading={<><div className="service-card-title-line"><h3 title={record.name}>{record.name}</h3><StatusBadge size="sm" icon={false} tone="neutral">待厂家对接</StatusBadge></div><span className="recipient-form-label">{forms[record.morphology].label}</span></>}
    metadata={<><span>更新：{time(record.updated_at)}</span></>} actions={controls} onOverview={()=>{setDetail(record);setOverviewOpen(true);}}>
    <p title={sceneNames}>{sceneNames||'未关联场景'}</p><div className="recipient-tags">{purposes.length?purposes.map(p=><StatusBadge size="sm" tone="neutral" key={p}>{purposeNames[p]}</StatusBadge>):<span className="recipient-form-label">未配置用途</span>}</div>
   </ServiceCard>;
   return <ServiceDirectoryRow key={record.id} label={record.name} symbol={<Shape size={36} weight="duotone"/>}
    heading={<><h3 className="service-entry-name">{record.name}</h3><span className="service-project">{forms[record.morphology].label}{(record.manufacturer||record.model)&&` · ${[record.manufacturer,record.model].filter(Boolean).join(' / ')}`}</span></>}
    capabilities={<><span className="service-entry-label">接入用途</span><div className="recipient-tags">{purposes.length?purposes.map(p=><StatusBadge size="sm" tone="neutral" key={p}>{purposeNames[p]}</StatusBadge>):<span className="service-project">未配置用途</span>}</div></>}
    metadata={<><div className="service-release-primary"><StatusBadge size="sm" icon={false} tone="neutral">待厂家对接</StatusBadge></div><div className="service-project">{sceneNames?`关联场景：${sceneNames}`:'未关联场景'}</div>{record.external_id&&<div className="service-project">设备标识：{record.external_id}</div>}</>}
    action={controls}/>;
  })}</div>}
  {!!data&&data.total>20&&!loading&&<div className="recipient-pagination"><Button variant="outline" size="sm" disabled={offset===0} onClick={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><span>{offset+1}–{Math.min(offset+20,data.total)} / {data.total}</span><Button variant="outline" size="sm" disabled={offset+20>=data.total} onClick={()=>setOffset(v=>v+20)}>下一页</Button></div>}
  <Drawer open={overviewOpen} onClose={()=>setOverviewOpen(false)} side="right" width="md" title="设备概要" description={detail?.name} closeLabel="关闭设备概要">{detail&&<div className="service-card-overview"><div><StatusBadge tone="neutral">待厂家对接</StatusBadge></div><dl>{[['设备形态',forms[detail.morphology].label],['厂家 / 型号',[detail.manufacturer,detail.model].filter(Boolean).join(' / ')||'未补充'],['关联场景',detail.relations.map(r=>data?.spaces.find(s=>s.id===r.space_id)?.name||r.space_id).join('、')||'未关联'],['接入用途',[...new Set(detail.relations.flatMap(r=>r.purposes))].map(p=>purposeNames[p]).join('、')||'未配置'],['最近修改',time(detail.updated_at)]].map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><div className="service-card-overview-actions"><ServiceCardActions label={detail.name} items={[{key:'device',label:'设备管理',icon:<Info size={16}/>,href:devicePageHref(detail.id,'overview','/services?'+params)}]}/></div></div>}</Drawer>
  {editorPanel}
  {linkExisting&&<LinkRecipient spaceId={spaceId} csrf={csrf} onCreate={openCreate} onClose={()=>setLinkExisting(false)} onSaved={()=>{setLinkExisting(false);setNotice('已关联设备，接入用途已保存，实际授权仍需独立配置。');setRefresh(v=>v+1);}}/>}
 </section>;
}

function RecipientDetail({record,spaces,onEdit,activeSection}:{record:Recipient;spaces:Space[];onEdit:(section:EditSection)=>void;activeSection:DeviceTab}){
 const root=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(activeSection!=='overview')root.current?.querySelector<HTMLElement>(`[data-device-section="${activeSection}"]`)?.scrollIntoView({block:'start'});},[activeSection]);
 const facts=(items:[string,string][])=> <dl className="recipient-detail-facts">{items.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||'—'}</dd></div>)}</dl>;
 return <div ref={root} className="recipient-detail">
  <section className="recipient-detail-section" aria-labelledby="device-information-title" data-device-section="overview">
   <header><h2 id="device-information-title">设备信息</h2>{record.can_manage&&<Button variant="outline" size="xl" onClick={()=>onEdit('information')}>编辑设备信息</Button>}</header>
   <div className="recipient-detail-information">
    <div><h3>设备属性</h3>{facts([['设备形态',forms[record.morphology].label],['厂家',record.manufacturer],['型号',record.model],['负责人',record.contact]])}{record.morphology_note&&<p className="recipient-detail-note">{record.morphology_note}</p>}</div>
    <div><h3>设备标识</h3>{facts([['外部设备标识',record.external_id]])}<dl className="recipient-detail-facts recipient-detail-identity"><div><dt>设备 ID</dt><dd>{record.id}</dd></div></dl><p className="recipient-detail-note">外部设备标识尚未验证。</p></div>
   </div>
   <div className="recipient-detail-audit"><span>登记：{time(record.created_at)}</span><span>更新：{time(record.updated_at)}</span><span>修订 {record.revision}</span></div>
  </section>
  <section className="recipient-detail-section" aria-labelledby="device-spaces-title" data-device-section="spaces">
   <header><h2 id="device-spaces-title">关联场景 <span>{record.relations.length}</span></h2>{record.can_manage&&<Button variant="outline" size="xl" onClick={()=>onEdit('relations')}>编辑关联场景</Button>}</header>
   {record.relations.length?<div className="recipient-detail-relations"><div className="recipient-detail-relation-head" aria-hidden="true"><span>场景</span><span>接入用途</span><span>服务使用方式</span></div>{record.relations.map(r=><div className="recipient-detail-relation" key={r.space_id}><h3>{spaces.find(s=>s.id===r.space_id)?.name||r.space_id}</h3><div className="recipient-tags">{r.purposes.map(p=><StatusBadge key={p} size="sm" tone="neutral">{purposeNames[p]}</StatusBadge>)}</div><span>{!r.purposes.includes('use')?'—':r.usage_modes.length?r.usage_modes.map(m=>m==='online'?'在线服务':'离线成果').join('、'):'待配置'}</span></div>)}</div>:<p className="recipient-detail-empty">尚未关联场景。</p>}
   <p className="recipient-detail-note">用途登记不授予实际服务权限。</p>
  </section>
  <section className="recipient-detail-section" aria-labelledby="device-integration-title" data-device-section="integration">
   <header><h2 id="device-integration-title">接入配置</h2><StatusBadge size="sm" icon={false} tone="neutral">待厂家对接</StatusBadge></header>
   <div className="recipient-detail-integration">{facts([['设备身份','未验证'],['通信接口','待厂家提供'],['数据约定','待配置']])}</div><p className="recipient-detail-note">厂家对接后，验证设备身份、数据格式及时间与坐标约定。</p>
  </section>
  <section className="recipient-detail-section" aria-labelledby="device-records-title" data-device-section="records">
   <header><h2 id="device-records-title">使用记录</h2></header>
   <div className="recipient-detail-empty"><ClockCounterClockwise size={24} aria-hidden="true"/><div><h3>暂无使用记录</h3><p>完成厂家接入后，记录采集提交、服务调用与离线交付。</p></div></div>
  </section>
 </div>;
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
 if(!response.ok)throw Error(response.status===409?'登记已发生变化或提交编号冲突。请关闭面板并刷新后重试。':response.status===403?'无权修改此设备或所选场景，请刷新权限后重试。':response.status===422?'请检查名称、设备形态和每个场景的接入用途。':'保存暂未确认，请保留当前内容重试。');
 return await response.json() as Recipient;
}

function RecipientEditor({initial,record,section,spaces,csrf,onClose,onSaved}:{initial:Draft;record?:Recipient;section?:EditSection;spaces:Space[];csrf:string;onClose:()=>void;onSaved:()=>void}){
 const [draft,setDraft]=useState(initial),[step,setStep]=useState(section==='relations'?2:1),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const prefix=useId(),pending=useRef<{body:string;id:string}|null>(null),mounted=useRef(true),saving=useRef(false);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 function set<K extends keyof Draft>(key:K,value:Draft[K]){setDraft(previous=>({...previous,[key]:value}));setError('');}
 function validInformation(){if(!draft.morphology||!draft.name.trim()||draft.morphology==='other'&&!draft.morphology_note.trim()){setError('请选择设备形态，填写名称；其他形态需补充说明。');return false;}return true;}
 function next(){if(!validInformation())return;setError('');setStep(2);}
 async function save(){
  if(saving.current||!validInformation())return;
  if(draft.relations.some(r=>!r.purposes.length)){setError('请为每个已关联场景至少选择一项接入用途，或取消该场景的关联。');return;}
  saving.current=true;setBusy(true);setError('');
  const body=JSON.stringify(draft);if(pending.current?.body!==body)pending.current={body,id:requestId()};
  try{await saveRecipient(draft,record,csrf,pending.current!.id);if(mounted.current)onSaved();}catch(e){if(mounted.current)setError((e as Error).message);}finally{saving.current=false;if(mounted.current)setBusy(false);}
 }
 return <Dialog open onOpenChange={open=>{if(!open&&!busy)onClose();}}><DialogContent className="recipient-editor-dialog" onEscapeKeyDown={e=>{if(busy)e.preventDefault();}} onInteractOutside={e=>e.preventDefault()}><DialogHeader><DialogTitle>{record?section==='relations'?'编辑关联场景':'编辑设备信息':'添加设备'}</DialogTitle><DialogDescription>{record?section==='relations'?'调整关联场景与接入用途。':'更新设备形态、名称与厂家信息。':'登记设备形态与作业用途，厂家接口可在后续接入。'}</DialogDescription></DialogHeader>
  <form className="recipient-editor" onSubmit={e=>{e.preventDefault();if(!record&&step===1)next();else void save();}}>
   {!record&&<ol className="recipient-steps" aria-label="登记步骤"><li aria-current={step===1?'step':undefined} data-complete={step>1}><span>{step>1?<Check size={16}/>:1}</span><div><strong>设备信息</strong><small>选择形态，填写基本信息</small></div></li><li aria-current={step===2?'step':undefined}><span>2</span><div><strong>场景与用途</strong><small>按场景配置，可稍后关联</small></div></li></ol>}
   <div className="recipient-editor-body"><fieldset disabled={busy}>
   {step===1?<><legend className="sr-only">设备信息</legend><div className="recipient-field"><span id={prefix+'-shape'}>设备形态 <span aria-hidden="true">*</span></span><div className="recipient-morphologies" role="radiogroup" aria-labelledby={prefix+'-shape'}>{Object.entries(forms).map(([key,value])=>{const Shape=value.icon;return <Button type="button" variant="outline" role="radio" aria-checked={draft.morphology===key} className="recipient-morphology" key={key} onClick={()=>set('morphology',key as Morphology)}><Shape size={24}/><div><strong>{value.label}</strong><span>{value.example}</span></div>{draft.morphology===key&&<Check size={16}/>}</Button>;})}</div></div><div className="recipient-information-grid">{([['name','设备名称 *',100],...(draft.morphology==='other'?[['morphology_note','形态说明 *',200]]:[]),['manufacturer','厂家',100],['model','型号',100],['external_id','外部设备标识',160],['contact','负责人',100]] as [keyof Omit<Draft,'relations'>,string,number][]).map(([key,label,max])=><div className="recipient-field" key={key}><label htmlFor={prefix+'-'+key}>{label}</label><Input id={prefix+'-'+key} placeholder={key==='name'?'例如：园区巡检机器狗 01':'选填'} value={draft[key]} maxLength={max} required={key==='name'||key==='morphology_note'} onChange={e=>set(key,e.target.value)}/></div>)}</div></>:<><legend className="sr-only">场景与用途</legend><div className="recipient-device-summary"><strong>{draft.name}</strong><span>{draft.morphology?forms[draft.morphology].label:''}</span><span>场景关联为选填，后续可继续配置。</span></div><RelationChoices spaces={spaces} relations={draft.relations} onChange={value=>set('relations',value)}/></>}
   </fieldset></div>
   {error&&<p role="alert" className="text-body-small text-destructive">{error}</p>}
   <div className="recipient-editor-footer"><span className="recipient-footer-note">{step===1?'* 为必填项':draft.relations.length?`已关联 ${draft.relations.length} 个场景 · 登记后待厂家对接`:'暂不关联场景，仅保存设备信息'}</span><Button size="xl" type="button" variant="outline" disabled={busy} onClick={onClose}>取消</Button>{!record&&step===2&&<Button size="xl" type="button" variant="outline" disabled={busy} onClick={()=>setStep(1)}>上一步</Button>}<Button size="xl" type="submit" disabled={busy}>{busy?'正在保存…':record?'保存更改':step===1?'下一步：场景与用途':draft.relations.length?'保存登记':'仅保存设备'}</Button></div>
  </form></DialogContent></Dialog>;

}

function LinkRecipient({spaceId,csrf,onCreate,onClose,onSaved}:{spaceId:string;csrf:string;onCreate:()=>void;onClose:()=>void;onSaved:()=>void}){
 const [items,setItems]=useState<Recipient[]>([]),[spaces,setSpaces]=useState<Space[]>([]),[query,setQuery]=useState(''),[selected,setSelected]=useState<Recipient|null>(null),[relations,setRelations]=useState<Relation[]>([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const pending=useRef<{body:string;id:string}|null>(null),saving=useRef(false),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');fetch(`${businessEndpoint}/api/service-recipients?${new URLSearchParams({q:query,limit:'100'})}`,{cache:'no-store',signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('设备列表暂不可读取。');const value:Directory=await r.json();if(!controller.signal.aborted){setItems(value.recipients);setSpaces(value.spaces);}}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[query]);
 async function save(){if(!selected||saving.current)return;if(!relations.length||relations.some(r=>!r.purposes.length)){setError('请选择此场景的接入用途。');return;}saving.current=true;setBusy(true);setError('');const draft:Draft={name:selected.name,morphology:selected.morphology,morphology_note:selected.morphology_note,manufacturer:selected.manufacturer,model:selected.model,external_id:selected.external_id,contact:selected.contact,relations:[...selected.relations.filter(r=>r.space_id!==spaceId),...relations]};const body=JSON.stringify(draft);if(pending.current?.body!==body)pending.current={body,id:requestId()};try{await saveRecipient(draft,selected,csrf,pending.current!.id);if(mounted.current)onSaved();}catch(e){if(mounted.current)setError((e as Error).message);}finally{saving.current=false;if(mounted.current)setBusy(false);}}
 return <Drawer open onClose={()=>{if(!busy)onClose();}} side="right" width="min(672px, 100vw)" title="关联设备" closeLabel="关闭关联面板"><div className="recipient-editor">{selected?<><h3>{selected.name}</h3><RelationChoices spaces={spaces.filter(s=>s.id===spaceId)} relations={relations} onChange={setRelations}/><p className="text-label-small text-muted-foreground">仅调整此场景的用途，其他场景登记保持不变。</p></>:<><div className="recipient-toolbar"><Input aria-label="搜索已登记设备" placeholder="搜索已登记设备" maxLength={160} value={query} onChange={e=>setQuery(e.target.value)}/><Button variant="outline" onClick={onCreate}>添加设备</Button></div>{loading?<p role="status">正在读取…</p>:<div className="recipient-existing">{items.filter(r=>r.can_manage).map(record=><Button variant="outline" key={record.id} onClick={()=>{setSelected(record);setRelations(structuredClone(record.relations.filter(r=>r.space_id===spaceId)));}}>{record.name} · {forms[record.morphology].label}{record.relations.some(r=>r.space_id===spaceId)?' · 已关联，编辑用途':''}</Button>)}{!items.some(r=>r.can_manage)&&<p>暂无可管理的匹配设备，可添加新设备。</p>}<p className="text-label-small text-muted-foreground">最多展示 100 个匹配结果，请输入名称或标识缩小范围。修改共享设备需具备其全部关联场景的管理权限。</p></div>}</>}{error&&<p role="alert" className="text-destructive text-body-small">{error}</p>}<div className="recipient-editor-footer"><Button variant="ghost" disabled={busy} onClick={onClose}>取消</Button>{selected&&<><Button variant="outline" disabled={busy} onClick={()=>setSelected(null)}>重新选择</Button><Button disabled={busy} onClick={()=>void save()}>{busy?'正在保存…':'保存关联'}</Button></>}</div></div></Drawer>;
}
