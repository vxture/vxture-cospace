import {DataNavigation} from './data-navigation';
import {WorkspaceHeading} from './workspace-frame';
import {appNavigate} from './app-router';
import {runGuarded,navigateSafely} from './unsaved-navigation';
import {useSceneDirectory} from './use-scene-directory';
import React,{useEffect,useState} from 'react';
import {Button,Input,NativeSelect,StatusBadge,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,Table,TableHeader,TableHead,TableBody,TableRow,TableCell} from '@vxture/design-system';
import {Database,Cube,FolderOpen,FileText,GitBranch,MagnifyingGlass,ArrowClockwise,CaretRight,X,Stack,ArrowUpRight,LinkSimple,SlidersHorizontal,Clock,SidebarSimple,Info,WarningCircle} from '@phosphor-icons/react';
import {businessEndpoint as endpoint} from './business-endpoint';
import {usePlatformSession} from './platform-auth';
import {recordLink,useRecordNavigation} from './record-navigation';
import {InputRegistration} from './input-registration';
import {SampleLibrary} from './sample-library';
import {SceneProgress} from './scene-progress';
import {InputDetails} from './input-details';
import {InputDescription,InputPresentation} from './input-description';
import {InputPreview} from './input-preview';
import {DataIntake,InputCheckStatus,useDataIntake} from './data-intake';
import {inputCounts,inputFormat,inputRoute} from './input-format';
import {SourceSettings} from './source-settings';
import {AcquisitionBatches} from './acquisition-batches';
import {InputBatchLinks,VersionSource,useSceneHistory} from './scene-history';
import {ArtifactImpact} from './artifact-impact';
import {ArtifactControl} from './artifact-control';
import {SceneAttachments,AttachmentSummary,type Attachment} from './scene-attachments';
import {realScreenHref} from './real-space-data';
import './data-workspace.css';
import './module-workspace.css';
const SceneCloudWorkspace=React.lazy(()=>import('./scene-cloud-workspace').then(m=>({default:m.SceneCloudWorkspace})));

type Entry={cloud_sha256?:string;snapshot_sha256?:string;presentation?:InputPresentation;id:string;label:string;format:string;input_frames:number;used_frames:number;point_count?:number;verified_image_members?:number;verified_messages?:number};
type Kind='input'|'candidate'|'publication'|'offline_package';
type Artifact={key:string;kind:Kind;record_id:string;label:string;classification:string;state:string;created_at:string|null;integrity:string;problems:string[];resources:Record<string,string>;selected:boolean;format?:string;lifecycle_state?:string;model_manifest_sha256?:string};
type Relation={from:string;to:string|null;relation:string;status:string};
type Catalog={space_id?:string;profile:string;items:Artifact[];relations:Relation[];observed_at:string};
type View='inputs'|'batches'|'versions'|'lineage'|'pointcloud'|'references';
const kindNames:Record<Kind,string>={input:'资料',candidate:'模型版本',publication:'固定发布',offline_package:'离线交付'};
const relationNames:Record<string,string>={built_from:'构建输入',annotated_from:'修订基线',published_from:'发布来源',sourced_from:'输入来源',exported_from:'离线导出'};
const relationStates:Record<string,string>={matched:'绑定一致',missing:'来源缺失',mismatch:'绑定不一致',unrecorded:'未记录'};
const formatShort=(f:string)=>f==='ply_pointcloud'?'PLY 点云':f==='nyu_rgbd_with_existing_poses'?'RGB-D + 轨迹':f==='ros1_lidar_multiframe_icp'?'激光多帧建图':f==='ros1_lidar_single_frame'?'ROS1 激光':f;
const date=(s:string|null)=>s?new Date(s).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'未记录';

function Availability({item}:{item?:Artifact}){
 if(item?.lifecycle_state==='disabled')return <StatusBadge tone="warning">已停用</StatusBadge>;
 if(item?.lifecycle_state==='archived')return <StatusBadge tone="neutral">已归档</StatusBadge>;
 if(item?.lifecycle_state==='retired')return <StatusBadge tone="warning">已退役</StatusBadge>;
 if(item?.lifecycle_state==='paused')return <StatusBadge tone="warning">分发暂停</StatusBadge>;
 if(item?.integrity==='unavailable')return <StatusBadge tone="danger">需核查</StatusBadge>;
 if(item?.integrity==='snapshot_verified')return <StatusBadge tone="success">快照完整</StatusBadge>;
 return <StatusBadge tone="info">已登记</StatusBadge>;
}

export function InputDirectory(){
 const target=useRecordNavigation(),platform=usePlatformSession();
 const [reference,setReference]=useState<Attachment|null>(null);
 const [savedEntries,setEntries]=useState<Entry[]>([]),[savedCatalog,setCatalog]=useState<Catalog|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [search,setSearch]=useState(''),[filter,setFilter]=useState('all'),[revision,setRevision]=useState(0),[directoryRevision,setDirectoryRevision]=useState(0),[notice,setNotice]=useState('');
 const {spaces,loading:directoryBusy,error:directoryError}=useSceneDirectory(directoryRevision);
 const [importOpen,setImportOpen]=useState(false),[intakeRevision,setIntakeRevision]=useState(0),[historyRevision,setHistoryRevision]=useState(0);
 const [tools,setTools]=useState<'sources'|null>(null),[detailMode,setDetailMode]=useState<'summary'|'impact'|'control'>('summary');
 const view:View=target.tab==='references'?'references':target.tab==='pointcloud'?'pointcloud':target.tab==='versions'||target.tab==='artifacts'?'versions':target.tab==='batches'||target.batch&&!target.tab?'batches':target.tab==='lineage'||target.artifact&&!target.input?'lineage':'inputs';
 const scene=spaces.find(s=>s.id===target.space);
 const catalog=savedCatalog?.space_id===target.space?savedCatalog:null;
 const entries=catalog?savedEntries:[];
 const selectionKey=target.input?`input:${target.input}`:target.artifact;
 const selectedEntry=entries.find(e=>`input:${e.id}`===selectionKey);
 const selectedArtifact=catalog?.items.find(a=>a.key===selectionKey);
 const referenceSelected=view==='references'&&reference?.space_id===target.space?reference:null;
 const hasSelection=!!referenceSelected||view!=='batches'&&view!=='pointcloud'&&view!=='references'&&!!(selectedEntry||selectedArtifact);
 const history=useSceneHistory(scene?.id||'',revision+historyRevision,view==='versions'||selectedArtifact?.kind==='candidate');
 const selectedBatch=history.batches.find(b=>b.id===target.batch);
 const inputBatch=selectedEntry&&selectedBatch?.members.some(m=>m.input_id===selectedEntry.id)?selectedBatch:undefined;
 const intake=useDataIntake(scene?.id||'',selectedEntry?.id||'',revision+intakeRevision,!!platform&&view==='inputs',target.batch);
 const versions=(catalog?.items.filter(i=>i.kind==='candidate')||[]).sort((a,b)=>(b.created_at?Date.parse(b.created_at):0)-(a.created_at?Date.parse(a.created_at):0));
 const releases=catalog?.items.filter(i=>i.kind==='publication')||[];
 const issues=catalog?.items.filter(i=>i.integrity==='unavailable').length||0;

 useEffect(()=>{
  setEntries([]);setCatalog(null);setError('');setSearch('');setFilter('all');setDetailMode('summary');
  if(!target.space||!scene){setBusy(false);return;}
  const request=new AbortController();setBusy(true);
  const query='?'+new URLSearchParams({space_id:target.space});
  const read=async(path:string)=>{const r=await fetch(`${endpoint}${path}${query}`,{signal:request.signal});if(!r.ok)throw Error(r.status===403?'当前账户没有此场景的数据管理权限。':'数据暂时无法读取，请重试。');return r.json();};
  Promise.all([read('/api/inputs'),read('/api/artifacts')]).then(([inputs,artifacts])=>{
   if(artifacts.space_id!==target.space||artifacts.profile!=='cospace.preview-artifact-catalog/0.1'||!Array.isArray(inputs.inputs))throw Error('数据与当前场景不一致，请重新选择场景。');
   if(!request.signal.aborted){setEntries(inputs.inputs);setCatalog({...artifacts,items:artifacts.items.map((a:Artifact)=>a.kind==='input'?{...a,label:inputs.inputs.find((e:Entry)=>e.id===a.record_id)?.presentation?.display_name||a.label}:a)});}
  }).catch(e=>{if(!request.signal.aborted)setError(e.message);}).finally(()=>{if(!request.signal.aborted)setBusy(false);});
  return()=>request.abort();
 },[target.space,scene?.id,revision,platform?.user?.workspace_id]);
 useEffect(()=>{setDetailMode('summary');},[selectionKey]);
 useEffect(()=>{setImportOpen(false);},[target.space]);
 useEffect(()=>{if(target.tab==='sources')setTools('sources');},[target.tab,target.batch]);
 useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),5000);return()=>clearTimeout(timer);},[notice]);

 function navigate(values:Record<string,string>){void navigateSafely(recordLink('data',{space:target.space,tab:view,...((view==='versions'||view==='inputs')&&target.batch?{batch:target.batch}:{}),...values}));}
 function chooseSpace(id:string){setTools(null);setNotice('');setEntries([]);setCatalog(null);appNavigate(recordLink('data',{space:id,tab:view}));}
 function switchView(next:View){setSearch('');setFilter('all');appNavigate(recordLink('data',{space:target.space,tab:next}));}
 function select(item:Artifact|Entry){if('key' in item&&item.kind==='input')void navigateSafely(recordLink('data',{space:target.space,tab:'inputs',input:item.record_id}));else navigate('key' in item?{artifact:item.key}:{input:item.id});}
 function refresh(){setRevision(v=>v+1);if(directoryError)setDirectoryRevision(v=>v+1);}
 const matches=(s:string)=>s.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
 const inputRows=entries.filter(e=>matches(`${e.presentation?.display_name||e.label} ${e.presentation?.description||''} ${e.presentation?.intended_use||''} ${e.id} ${inputFormat(e.format)}`)&&(filter==='all'||e.format===filter||inputRoute(e.format)?.category===filter));
 const versionRows=versions.filter(v=>(!target.batch||history.jobs.some(j=>j.id===v.record_id&&j.batch_ref?.batch_id===target.batch))&&matches(`${v.label} ${v.record_id}`)&&(filter==='all'||(filter==='selected'?v.selected:filter==='published'?v.model_manifest_sha256&&releases.some(r=>r.model_manifest_sha256===v.model_manifest_sha256):v.integrity==='unavailable')));
 const relationRows=(catalog?.relations||[]).filter(r=>{const a=catalog?.items.find(i=>i.key===r.from),b=catalog?.items.find(i=>i.key===r.to);return matches(`${a?.label||''} ${b?.label||''} ${relationNames[r.relation]||r.relation}`)&&(filter==='all'||(filter==='issues'?r.status!=='matched':r.relation===filter));});
 const shown=view==='inputs'?inputRows.length:view==='versions'?versionRows.length:relationRows.length;
 const total=view==='inputs'?entries.length:view==='versions'?versions.length:catalog?.relations.length||0;
 const title=selectedEntry?.presentation?.display_name||selectedEntry?.label||selectedArtifact?.label||'';
 function descriptionSaved(value:InputPresentation){const id=selectedEntry?.id;setEntries(old=>old.map(e=>e.id===id?{...e,presentation:value}:e));setCatalog(old=>old?{...old,items:old.items.map(a=>a.kind==='input'&&a.record_id===id?{...a,label:value.display_name}:a)}:old);setIntakeRevision(v=>v+1);}
 function registered(id:string,created:boolean){void runGuarded(()=>{setNotice(created?'资料已登记，请在右侧执行预检。':'已定位当前场景的已有资料。');setRevision(v=>v+1);appNavigate(recordLink('data',{space:target.space,tab:'inputs',input:id}));});}

 return <div className={`data-workspace data-directory-workspace ${hasSelection?'data-has-detail':''}`}>
  <div className="data-workspace-decoration" aria-hidden="true">
   <svg className="data-space-lines" viewBox="0 0 640 400" fill="none">
    <g stroke="currentColor" strokeWidth="1">
     <path d="M40 260 330 95 680 295M-20 295 330 95M100 295 390 130M160 330 450 165M220 365 510 200M280 400 570 235M40 260 390 460M100 225 450 425M160 190 510 390M220 155 570 355M280 120 630 320" opacity=".45"/>
     <path d="m150 223 115-66 116 66-115 67Z M150 223v-85l115-66 116 66v85 M150 138l116 67 115-67M266 205v85M265 72v85"/>
     <path d="m364 270 79-45 80 45-80 46Z M364 270v-58l79-45 80 45v58M364 212l79 46 80-46M443 258v58M443 167v58"/>
     <path d="m270 352 58-33 58 33-58 34Z M270 352v-38l58-33 58 33v38M270 314l58 34 58-34M328 348v38" opacity=".7"/>
     <path d="m85 282 63 36 65-37 57 33M382 223l39-22 54 31" strokeDasharray="4 6"/>
    </g>
    <g fill="currentColor"><circle cx="150" cy="223" r="2.5"/><circle cx="381" cy="138" r="2.5"/><circle cx="443" cy="316" r="2.5"/><circle cx="85" cy="282" r="2.5"/></g>
   </svg>
  </div>
  <DataNavigation view={view}/>

  <section className="data-main" aria-label="数据管理工作区">
   {directoryError&&<p role="alert" className="data-notice">{directoryError}<Button variant="ghost" size="sm" onClick={()=>setDirectoryRevision(v=>v+1)}>重新读取</Button></p>}
   <WorkspaceHeading icon={Database} title="数据管理" description="按当前场景维护资料、采集批次、模型版本与来源引用。" actions={<><Button asChild size="sm" variant="secondary"><a href={recordLink('data',{scope:'all'})}>共用数据目录</a></Button><Button variant="secondary" size="sm" className="data-icon-button" aria-label="刷新数据" title="刷新数据" disabled={busy} onClick={()=>{void runGuarded(refresh);}}><ArrowClockwise size={16} className={busy?'data-spin':''}/></Button><SampleLibrary key={`samples-${target.space}`} endpoint={endpoint} spaceId={scene?.id||''} spaceName={scene?.name||''} authorized={!!platform} onRegistered={registered} onManageSources={()=>setTools('sources')}/><InputRegistration key={target.space} spaceId={scene?.id||''} endpoint={endpoint} triggerLabel="导入资料" spaceName={scene?.name} open={importOpen} onOpenChange={setImportOpen} onManageSources={()=>setTools('sources')} onRegistered={registered}/></>}/>


   <div className="data-overview" aria-label="当前场景数据概览"><div><FolderOpen size={17}/><span>资料</span><strong>{catalog?entries.length:'—'}</strong></div><div><Stack size={17}/><span>模型版本</span><strong>{catalog?versions.length:'—'}</strong></div><div><Cube size={17}/><span>固定发布</span><strong>{catalog?releases.length:'—'}</strong></div><span className="data-overview-note">{issues>0?<><WarningCircle size={14}/>{issues} 项成果需核查</>:<><Info size={14}/>样本流程 · 质量尚未验收</>}</span></div>
   {scene&&view==='inputs'&&<DataIntake space={scene.id} batchId={target.batch||undefined} {...intake} onSources={()=>setTools('sources')} onImport={()=>setImportOpen(true)} onInspect={()=>{document.querySelector<HTMLElement>('.data-input-preflight')?.focus();document.querySelector('.data-input-preflight')?.scrollIntoView({block:'nearest'});}} onChoose={()=>{setNotice('请从资料列表选择本次要构建的资料。');document.querySelector<HTMLElement>('.data-record-name')?.focus();}}/>}
   <div className="data-viewbar"><div className="data-secondary-tools">{platform&&<Button variant="ghost" size="sm" disabled={!scene} onClick={()=>setTools('sources')}><SlidersHorizontal size={14}/>来源配置</Button>}</div></div>
   {view==='inputs'&&inputBatch&&<div className="data-batch-context"><span>本次批次：{inputBatch.name}</span><Button asChild variant="ghost" size="sm"><a href={recordLink('data',{space:target.space,tab:'batches',batch:inputBatch.id})}>返回批次</a></Button></div>}
   {notice&&<p className="data-notice" role="status">{notice}</p>}
   {!busy&&catalog&&selectionKey&&!selectedEntry&&!selectedArtifact&&<p className="data-notice" role="alert">所选记录不存在于当前场景，请重新选择资料或版本。</p>}
   <div className="data-content">
    <section className="data-browser" id="data-view-panel" role="region" aria-label={({inputs:'资料与预检',references:'配套资料',pointcloud:'场景点云',batches:'采集批次',versions:'场景版本',lineage:'来源追溯'})[view]}>
    {view==='references'?scene?<SceneAttachments key={scene.id+(platform?.user?.workspace_id||'engineering')} endpoint={endpoint} space={scene.id} revision={revision} onChanged={refresh} onSelect={setReference}/>:<div className="data-empty">请先选择有权限的场景空间。</div>:view==='pointcloud'?scene?<React.Suspense fallback={<p role="status">正在打开场景点云…</p>}><SceneCloudWorkspace key={scene.id+(platform?.user?.workspace_id||'engineering')} endpoint={endpoint} space={scene.id} onRegistered={()=>setRevision(v=>v+1)}/></React.Suspense>:<div className="data-empty">请先选择有权限的场景空间。</div>:<>
    {scene&&!directoryBusy&&!directoryError&&!busy&&!error&&<SceneProgress key={[scene.id,target.input,target.job,target.publication].join(':')} space={scene.id} name={scene.name} input={target.input} revision={revision+intakeRevision+historyRevision}/>}
     {view!=='batches'&&<div className="data-toolbar"><div className="data-search"><MagnifyingGlass size={16}/><Input aria-label="搜索当前数据" placeholder={view==='inputs'?'搜索资料名称、格式…':view==='versions'?'搜索模型版本…':'搜索成果或来源关系…'} value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="清除搜索" onClick={()=>setSearch('')}><X size={13}/></button>}</div><NativeSelect aria-label="筛选当前数据" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">{view==='inputs'?'全部类别 / 格式':view==='versions'?'全部版本':'全部关系'}</option>{view==='inputs'?<><option value="acquisition">原始采集资料</option><option value="existing_product">已有空间成果</option>{Array.from(new Set(entries.map(e=>e.format))).map(f=><option key={f} value={f}>{formatShort(f)}</option>)}</>:view==='versions'?<><option value="selected">当前候选</option><option value="published">有关联发布</option><option value="issues">需核查</option></>:<><option value="issues">关系需核查</option>{Array.from(new Set(catalog?.relations.map(r=>r.relation))).map(r=><option key={r} value={r}>{relationNames[r]||r}</option>)}</>}</NativeSelect><span className="data-result-count">{busy?'读取中…':`${shown} 项`}</span></div>}
     {view==='versions'&&target.batch&&<div className="data-batch-context" aria-label="版本批次筛选"><span>批次：{selectedBatch?.name||'未找到可读批次'} · 仅显示显式绑定版本</span><Button asChild variant="ghost" size="sm"><a href={recordLink('data',{space:target.space,tab:'batches',batch:target.batch})}>返回批次</a></Button><Button asChild variant="ghost" size="sm"><a href={recordLink('data',{space:target.space,tab:'versions'})}>全部版本</a></Button></div>}
     {view==='versions'&&history.error&&<p className="data-notice" role="alert">{history.error}</p>}
     <div className="data-table-scroll" aria-busy={busy}>
      {(directoryError&&!scene)||error?<div className="data-empty" role="alert"><WarningCircle size={32} weight="duotone"/><h2>暂时无法读取</h2><p>{directoryError||error}</p><Button variant="outline" size="sm" onClick={refresh}>重试</Button></div>:!scene?<div className="data-empty"><Cube size={40} weight="duotone"/><h2>{directoryBusy?'正在连接场景…':'选择一个三维场景'}</h2><p>{target.space&&!directoryBusy?'所选场景无权访问或不存在，请从左侧重新选择。':'从左侧目录开始，管理该场景的资料与历史版本。'}</p></div>:busy||view==='versions'&&history.loading?<div className="data-loading" role="status"><ArrowClockwise size={20} className="data-spin"/><span>正在读取场景数据…</span></div>:<>
      {view==='batches'&&<AcquisitionBatches key={target.space} onChanged={()=>setHistoryRevision(v=>v+1)}/> }
      {view==='inputs'&&<Table className="data-table"><TableHeader><TableRow><TableHead>资料名称</TableHead><TableHead>格式</TableHead><TableHead>规模</TableHead><TableHead>记录情况</TableHead><TableHead className="data-table-action">操作</TableHead></TableRow></TableHeader><TableBody>{inputRows.map(entry=>{const a=catalog?.items.find(i=>i.key===`input:${entry.id}`);return <TableRow key={entry.id} data-selected={selectedEntry?.id===entry.id||undefined} onClick={()=>select(entry)}><TableCell><button className="data-record-name" onClick={e=>{e.stopPropagation();select(entry);}}><span className="data-file-icon"><FileText size={20} weight="duotone"/></span><span><strong>{entry.presentation?.display_name||entry.label}</strong><small>{entry.format==='ply_pointcloud'?'已有空间成果 · 声明局部坐标':entry.format==='ros1_lidar_multiframe_icp'?'激光观测 · 构建时估计轨迹':entry.format==='ros1_lidar_single_frame'?'激光观测 · 单帧局部资料':'彩色与深度观测 · 配套已有轨迹'}</small></span></button></TableCell><TableCell><span className="data-format">{formatShort(entry.format)}</span></TableCell><TableCell><span className="data-cell-main">{entry.format==='ply_pointcloud'?`${(entry.point_count??0).toLocaleString('zh-CN')} 点`:`${entry.input_frames} 帧${entry.format==='ros1_lidar_multiframe_icp'?'点云':''}`}</span><span className="data-cell-note">{entry.format==='ply_pointcloud'?'对齐未核验':entry.format==='ros1_lidar_multiframe_icp'?'纯激光配准路线':entry.format==='ros1_lidar_single_frame'?'未配准':`${entry.used_frames} 帧位姿`}</span></TableCell><TableCell><Availability item={a}/><InputCheckStatus item={intake.data?.inputs.find(i=>i.input_id===entry.id)}/></TableCell><TableCell className="data-table-action"><Button variant="ghost" size="sm" onClick={e=>{e.stopPropagation();select(entry);}}>详情<ArrowUpRight size={13}/></Button></TableCell></TableRow>;})}</TableBody></Table>}
      {view==='versions'&&<Table className="data-table"><TableHeader><TableRow><TableHead>模型版本</TableHead><TableHead>来源批次 / 资料</TableHead><TableHead>形成时间</TableHead><TableHead>关联发布</TableHead><TableHead>检查情况</TableHead><TableHead className="data-table-action">操作</TableHead></TableRow></TableHeader><TableBody>{versionRows.map(item=><TableRow key={item.key} data-selected={selectedArtifact?.key===item.key||undefined} onClick={()=>select(item)}><TableCell><button className="data-record-name" onClick={e=>{e.stopPropagation();select(item);}}><span className="data-file-icon"><Cube size={20} weight="duotone"/></span><span><strong>{item.label}</strong><small>{item.classification==='semantic_candidate'?'语义修订快照':'几何模型快照'}{item.selected?' · 当前候选':''}</small></span></button></TableCell><TableCell><VersionSource space={target.space} job={history.jobs.find(j=>j.id===item.record_id)} batches={history.batches} inputs={entries} available={!history.error&&!history.loading}/></TableCell><TableCell>{date(item.created_at)}</TableCell><TableCell>{releases.filter(r=>!!item.model_manifest_sha256&&r.model_manifest_sha256===item.model_manifest_sha256).length} 个</TableCell><TableCell><Availability item={item}/></TableCell><TableCell className="data-table-action"><Button variant="ghost" size="sm" onClick={e=>{e.stopPropagation();select(item);}}>详情<ArrowUpRight size={13}/></Button></TableCell></TableRow>)}</TableBody></Table>}
      {view==='lineage'&&<Table className="data-table data-lineage-table"><TableHeader><TableRow><TableHead>成果</TableHead><TableHead>关系</TableHead><TableHead>来源</TableHead><TableHead>记录检查</TableHead></TableRow></TableHeader><TableBody>{relationRows.map((r,i)=>{const a=catalog?.items.find(x=>x.key===r.from),b=catalog?.items.find(x=>x.key===r.to);return <TableRow key={`${r.from}-${r.relation}-${i}`}><TableCell><button className="data-relation-link" disabled={!a} onClick={()=>a&&select(a)}>{a?.label||'来源归属未确认'}</button><span className="data-cell-note">{a?kindNames[a.kind]:''}</span></TableCell><TableCell><span className="data-relation-kind"><LinkSimple size={14}/>{relationNames[r.relation]||r.relation}</span></TableCell><TableCell><button className="data-relation-link" disabled={!b} onClick={()=>b&&select(b)}>{b?.label||'未找到对应记录'}</button><span className="data-cell-note">{b?kindNames[b.kind]:''}</span></TableCell><TableCell><StatusBadge tone={r.status==='matched'?'neutral':'warning'}>{relationStates[r.status]||r.status}</StatusBadge></TableCell></TableRow>;})}</TableBody></Table>}
      {view!=='batches'&&!shown&&<div className="data-empty"><FolderOpen size={38} weight="duotone"/><h2>{search||filter!=='all'?'没有匹配的数据':view==='inputs'?'准备这个场景的第一份资料':view==='versions'?target.batch?'此批次尚无模型版本':'还没有模型版本':'暂无来源关系'}</h2><p>{search||filter!=='all'?'调整搜索或筛选条件后重试。':view==='inputs'?'上传资料包或从已配置来源导入，检查整理后进入构建。':view==='versions'?target.batch?'从封存批次选择成员构建；同资料的其他历史构建不会自动归入。':'资料经过构建后，模型快照与历史版本会出现在这里。':'处理和发布产生后，将在这里连接输入与成果。'}</p>{(search||filter!=='all')&&<Button variant="outline" size="sm" onClick={()=>{setSearch('');setFilter('all');}}>清除筛选</Button>}</div>}
      </>}
     </div>
     <footer className="data-table-footer"><span>{scene?view==='batches'?`当前场景 · ${history.batches.length} 个采集批次`:`当前场景 · ${shown} / ${total} 项`:'请选择有权限的场景'}</span><span>{catalog?<><Clock size={12}/>{date(catalog.observed_at)} 读取</>:null}</span></footer>
    </>}
    </section>

   </div>
  </section>
    {hasSelection&&!referenceSelected&&<aside className="data-detail" id="data-detail-panel" aria-label={selectedEntry?"资料详情面板":"数据详情面板"} onKeyDown={e=>{if(e.key==='Escape')navigate({});}}>
     <header className="data-detail-heading"><span>{selectedEntry?'资料详情':selectedArtifact?kindNames[selectedArtifact.kind]+'详情':'详情'}</span><Button variant="ghost" size="sm" className="data-icon-button" aria-label="关闭数据详情" onClick={()=>navigate({})}><X size={17}/></Button></header>
     <div className="data-detail-scroll"><div className="data-detail-title"><span className="data-detail-symbol">{selectedEntry?<FileText size={26} weight="duotone"/>:<Cube size={26} weight="duotone"/>}</span><h2>{title}</h2><Availability item={selectedArtifact}/></div>
      <dl className="data-detail-facts"><div><dt>所属场景</dt><dd>{scene?.name}</dd></div><div><dt>资料类别</dt><dd>{selectedEntry?(selectedEntry.format==='ply_pointcloud'?'已有空间成果':'原始采集资料'):selectedArtifact?kindNames[selectedArtifact.kind]:''}</dd></div>{selectedEntry&&<><div><dt>格式</dt><dd>{formatShort(selectedEntry.format)}</dd></div><div><dt>规模</dt><dd>{inputCounts(selectedEntry)}</dd></div></>}{selectedArtifact&&!selectedEntry&&<div><dt>形成时间</dt><dd>{date(selectedArtifact.created_at)}</dd></div>}</dl>
      {selectedEntry&&platform&&<InputPreview key={`preview-${target.space}-${selectedEntry.id}-${revision}`} endpoint={endpoint} space={target.space} input={selectedEntry}/>}
      {selectedEntry&&platform&&<InputDescription key={`${target.space}-${selectedEntry.id}`} endpoint={endpoint} space={target.space} identity={selectedEntry.id} onSaved={descriptionSaved} onCoordinatesSaved={()=>setIntakeRevision(v=>v+1)}/>}
      {selectedEntry?<InputDetails preparation={intake.data} key={`${target.space}-${selectedEntry.id}-${revision}`} endpoint={endpoint} identity={selectedEntry.id} batchId={target.batch||undefined} showBuild lifecycleState={selectedArtifact?.lifecycle_state} onChecked={()=>setIntakeRevision(v=>v+1)}/>:selectedArtifact&&<div className="data-detail-section"><h3>查看与使用</h3>{selectedArtifact.integrity==='unavailable'?<p>快照不可用，请先核查原始记录。</p>:<div className="data-detail-actions">{selectedArtifact.kind==='candidate'&&<Button asChild size="sm" variant="outline"><a href={recordLink('build',{space:target.space,job:selectedArtifact.record_id})}>查看构建记录<ArrowUpRight size={14}/></a></Button>}{(selectedArtifact.kind==='publication'||selectedArtifact.kind==='offline_package')&&<Button asChild size="sm" variant="outline"><a href={recordLink('delivery',{space:target.space,publication:selectedArtifact.record_id})}>查看固定发布<ArrowUpRight size={14}/></a></Button>}{selectedArtifact.kind==='publication'&&selectedArtifact.integrity==='snapshot_verified'&&(!selectedArtifact.lifecycle_state||selectedArtifact.lifecycle_state==='active')&&<Button asChild size="sm"><a href={realScreenHref(target.space,selectedArtifact.record_id)} target="_blank" rel="noopener noreferrer">打开空间<ArrowUpRight size={14}/></a></Button>}</div>}</div>}
      {selectedEntry&&<InputBatchLinks space={target.space} input={selectedEntry.id} batches={history.batches} available={!history.error&&!history.loading}/>}
      {selectedArtifact?.kind==='candidate'&&<section className="data-detail-section"><h3>构建来源</h3><VersionSource space={target.space} job={history.jobs.find(j=>j.id===selectedArtifact.record_id)} batches={history.batches} inputs={entries} available={!history.error&&!history.loading}/></section>}
      {selectedArtifact&&<div className="data-detail-section"><h3>来源与引用</h3>{catalog?.relations.filter(r=>r.from===selectedArtifact.key||r.to===selectedArtifact.key).map((r,i)=>{const other=catalog.items.find(a=>a.key===(r.from===selectedArtifact.key?r.to:r.from));return <button className="data-related-record" key={i} disabled={!other} onClick={()=>other&&select(other)}><span><small>{r.from===selectedArtifact.key?'上游':'下游'} · {relationNames[r.relation]||r.relation}</small><strong>{other?.label||relationStates[r.status]||'记录不可用'}</strong></span><CaretRight size={13}/></button>;})}{!catalog?.relations.some(r=>r.from===selectedArtifact.key||r.to===selectedArtifact.key)&&<p>暂无关联记录。</p>}</div>}
      {selectedArtifact&&<details className="data-technical-details"><summary>标识与使用管理</summary><code>{selectedArtifact.record_id}</code>{selectedArtifact.model_manifest_sha256&&<code>{selectedArtifact.model_manifest_sha256}</code>}<div className="data-detail-actions"><Button variant="outline" size="sm" onClick={()=>setDetailMode('impact')}>查看使用影响</Button><Button variant="outline" size="sm" onClick={()=>setDetailMode('control')}>管理使用状态</Button></div></details>}
      {selectedArtifact&&detailMode==='impact'&&<ArtifactImpact space={target.space} artifact={selectedArtifact.kind==='offline_package'?`publication:${selectedArtifact.record_id}`:selectedArtifact.key} revision={revision} onClose={()=>setDetailMode('summary')}/>}
      {selectedArtifact&&detailMode==='control'&&<ArtifactControl space={target.space} artifact={selectedArtifact.kind==='offline_package'?`publication:${selectedArtifact.record_id}`:selectedArtifact.key} onClose={()=>setDetailMode('summary')} onCommitted={()=>setRevision(v=>v+1)}/>}
     </div>
    </aside>}
  {referenceSelected&&<aside className="data-detail" aria-label="配套资料详情面板"><header className="data-detail-heading"><span>配套资料详情</span><Button variant="ghost" size="sm" className="data-icon-button" aria-label="关闭配套资料详情" onClick={()=>setReference(null)}><X size={17}/></Button></header><div className="data-detail-scroll"><AttachmentSummary item={referenceSelected} endpoint={endpoint}/></div></aside>}
  <Dialog open={!!tools} onOpenChange={open=>{if(!open)void runGuarded(()=>{setTools(null);if(target.tab==='sources')navigate({tab:'inputs'});});}}><DialogContent className="data-management-dialog"><DialogHeader><DialogTitle>资料来源配置</DialogTitle><DialogDescription>管理当前场景允许登记的来源。</DialogDescription></DialogHeader>{tools==='sources'&&<SourceSettings key={target.space} spaceId={target.space} onSaved={()=>setIntakeRevision(v=>v+1)} onImport={()=>{setTools(null);if(target.tab==='sources')navigate({tab:'inputs'});setImportOpen(true);}}/>}</DialogContent></Dialog>
 </div>;
}
