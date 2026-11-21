import React,{useEffect,useRef,useState} from 'react';
import {ArrowDown,ArrowUp,CheckCircle,Compass,DownloadSimple,DotsThreeVertical,FloppyDisk,UploadSimple,XCircle} from '@phosphor-icons/react';
import {Button,Drawer,DropdownMenu,DropdownMenuContent,DropdownMenuItem,DropdownMenuSeparator,DropdownMenuTrigger,Input,StatusBadge,Textarea} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {readPreview,validatePreview,type PreviewGeometry} from './geometry-preview-data';
import {type Point3,type RegistrationInput} from './registration-preview-data';
import {RegistrationWorkbench} from './registration-workbench';
import {useUnsavedNavigation} from './unsaved-navigation';
import {RegistrationMap} from './registration-map';
import {RegistrationGeographicBinding,type GeographicBinding} from './registration-geographic-binding';
import {RegistrationSourceRecovery} from './registration-source-recovery';
import './scene-registration.css';

type Action='save'|'submit'|'approve'|'reject'|'adopt'|'clear_adoption';
type Approval={evidence_note:string;valid_from:string;valid_until:string;bounds_m:[Point3,Point3];control_evidence_verified:boolean;independent_checks_verified:boolean;datum_verified:boolean;extent_verified:boolean};
type Snapshot={revision:number;document:RegistrationInput|null;report:{calculation_status:string}|null;review_status:'empty'|'draft'|'submitted'|'approved'|'rejected';authored_by:string|null;reviewed_by:string|null;reviewed_at:string|null;approval:Approval|null;approved_revision:number|null;adopted_revision:number|null;action:string|null;actor:string|null;changed_at:string|null;reason:string|null};
type State=Snapshot&{profile:string;space_id:string;candidate_id:string;source_sha256:string;model_source:RegistrationInput['source'];adopted:Snapshot|null;can_edit:boolean;can_review:boolean;geographic_binding:GeographicBinding|null;can_focus_geographic_map:boolean;enabled_adapters:string[]};
const labels={empty:'未录入',draft:'草稿',submitted:'待审核',approved:'已核准',rejected:'已退回'};
const actionLabels:Record<Action,string>={save:'保存资料',submit:'提交审核',approve:'核准配准',reject:'退回资料',adopt:'采用核准修订',clear_adoption:'撤下当前采用'};
const explanations:Record<Action,string>={save:'保存为新草稿；原已采用修订继续保留。',submit:'检查通过的真实资料提交独立审核。',approve:'核实控制资料、独立检查、基准和适用范围后核准。录入者不能审核自己的资料。',reject:'填写退回依据，录入者修改并重新提交。',adopt:'固定采用此核准修订。此操作不改变已有服务发布。',clear_adoption:'后续消费停止使用当前采用；历史修订和已有发布继续保留。'};
const errors:Record<string,string>={registration_source_axes_unsupported:'来源模型缺少可核验的右手轴向声明。请先在资料与构建阶段明确坐标后重新构建。',registration_source_unit_unsupported:'来源模型未明确米制单位。请先修订资料坐标并重新构建。',registration_source_geometry_invalid:'来源模型的三维范围无效，暂不能进入此配准路线。',registration_source_changed:'资料绑定的模型已变化，请重新读取并核对来源。',registration_revision_changed:'资料已由其他人修改，请保留本地资料后重新读取。',registration_independent_reviewer_required:'录入者不能审核自己的资料，请由另一位场景管理员审核。',registration_synthetic_not_approvable:'合成算例不能提交真实成果审核。',registration_checks_failed:'独立检查点超限，请修正资料后再提交。',registration_outside_valid_time:'当前不在核准有效期内，不能采用。',registration_extent_outside_model:'核准范围必须位于来源模型范围内。',registration_approval_expired:'核准有效期已经结束。',registration_invalid_document:'刚体参数、控制点或独立检查不符合要求，请核对资料。',registration_invalid_request:'资料格式不符合合同，请核对字段、数值、至少各三个非共线控制点与检查点。',registration_source_inactive:'来源模型已归档，请恢复后再修改。',registration_store_integrity:'配准记录完整性检查失败，请联系管理员。',registration_already_adopted:'此核准修订已采用。'};
const endpoint=businessEndpoint+'/api/scene-registrations';
class RegistrationRequestError extends Error{constructor(message:string,readonly code:string){super(message);}}
async function value(response:Response){
 if(!response.ok){let code='';try{code=(await response.json()).detail;}catch{}
  throw new RegistrationRequestError(response.status===401?'请先登录。':response.status===403?'当前身份无权执行此操作。':errors[code]||'配准资料暂不可用，请重新核对后重试。',code);
 }
 return response.json();
}
function download(name:string,data:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

export function SceneRegistration({spaceId,candidateId}:{spaceId:string;candidateId:string}){
 const [state,setState]=useState<State|null>(null),[draft,setDraft]=useState<RegistrationInput|null>(null),[geometry,setGeometry]=useState<PreviewGeometry>();
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[geometryError,setGeometryError]=useState('');
 const [sourceBlocked,setSourceBlocked]=useState(false);
 const [action,setAction]=useState<Action|null>(null),[reason,setReason]=useState(''),[reviewOpen,setReviewOpen]=useState(false),[refresh,setRefresh]=useState(0);
 const [start,setStart]=useState(''),[end,setEnd]=useState(''),[bounds,setBounds]=useState<string[][]>([[],[]]),[checks,setChecks]=useState([false,false,false,false]);
 const [binding,setBinding]=useState<GeographicBinding|null>(null),[mapOpen,setMapOpen]=useState(false);
 const [bindingOpen,setBindingOpen]=useState(false);
 const file=useRef<HTMLInputElement>(null),mounted=useRef(true),gate=useRef(false),request=useRef<Record<string,unknown>|null>(null);
 const current=draft||state?.document;
 const dirty=!!draft&&(JSON.stringify(draft)!==JSON.stringify(state?.document)||JSON.stringify(binding)!==JSON.stringify(state?.geographic_binding));
 const releaseDraft=useUnsavedNavigation(dirty||busy||!!action&&!!reason,'空间基准资料',{discard:()=>{setDraft(null);setAction(null);}});
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 async function read(signal?:AbortSignal):Promise<State>{
  const result:State=await value(await fetch(endpoint+'?'+new URLSearchParams({space_id:spaceId,candidate_id:candidateId}),{signal,cache:'no-store'}));
  if(result.profile!=='cospace.scene-registration/0.1'||result.space_id!==spaceId||result.candidate_id!==candidateId||result.model_source.manifest_sha256!==result.source_sha256)throw Error('配准记录与当前模型来源不一致。');
  return result;
 }
 useEffect(()=>{const abort=new AbortController();setLoading(true);setError('');setState(null);setSourceBlocked(false);
  read(abort.signal).then(result=>{if(!abort.signal.aborted)setState(result);}).catch(e=>{if(!abort.signal.aborted){setError(e.message);setSourceBlocked(e instanceof RegistrationRequestError&&['registration_source_axes_unsupported','registration_source_unit_unsupported'].includes(e.code));}}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
  return()=>abort.abort();
 },[spaceId,candidateId,refresh]);
 useEffect(()=>{const abort=new AbortController();setGeometry(undefined);setGeometryError('');if(!state)return()=>abort.abort();
  readPreview(endpoint+'/geometry?'+new URLSearchParams({space_id:spaceId,candidate_id:candidateId}),abort.signal).then(raw=>{
   const result=validatePreview(raw,{space:spaceId,candidate:candidateId,manifest:state.source_sha256,source:state.model_source.model_sha256});
   if(!abort.signal.aborted)setGeometry(result);
  }).catch(e=>{if(!abort.signal.aborted)setGeometryError(e.message);});return()=>abort.abort();
 },[spaceId,candidateId,state?.source_sha256]);
 async function check(document:unknown,geographicBinding=draft?binding:state?.geographic_binding){
  if(!state||gate.current)return;gate.current=true;setBusy(true);setError('');setNotice('');
  try{const checked=await value(await fetch(endpoint+'/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({space_id:spaceId,candidate_id:candidateId,source_sha256:state.source_sha256,document,geographic_binding:geographicBinding||null})}));
   if(mounted.current){setDraft(checked.document);setBinding(checked.geographic_binding);setNotice('服务端已完成参数核对，资料尚未保存。');}
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:'资料核对失败。');}finally{gate.current=false;if(mounted.current)setBusy(false);}
 }
 async function importFile(selected?:File){
  if(!selected||busy)return;if(selected.size>1_000_000){setError('资料不能超过 1 MB。');return;}
  try{const imported=JSON.parse(await selected.text());await check(imported.document||imported,imported.document?imported.geographic_binding:null);}catch{setError('无法读取 JSON 资料，请核对文件。');}
 }
 function template(){if(!state)return;download('配准资料空白模板.json',{profile:'cospace.spatial-registration-input/0.1',synthetic:false,source:state.model_source,target:{frame_id:'',title:'',kind:'engineering',horizontal_reference:'',definition_ref:'',evidence_ref:'',unit:'m',axes:'east_north_up',vertical_reference:'',geographic_adapter:'not_connected'},method:'provided_rigid_3d',direction:'source_to_target',matrix:null,controls:[],check_limits:{horizontal_m:null,vertical_m:null}});}
 function open(next:Action){if(!state||busy)return;request.current=null;setAction(next);setReason('');setError('');setChecks([false,false,false,false]);setStart('');setEnd('');setBounds(state.model_source.bounds_m.map(point=>point.map(String)));}
 function close(){if(!gate.current){setAction(null);request.current=null;}}
 const approvalValid=checks.every(Boolean)&&!!start&&!!end&&new Date(start)<new Date(end)&&bounds.every(row=>row.length===3&&row.every(n=>n.trim()!==''&&Number.isFinite(Number(n))));
 async function execute(){
  if(!state||!action||!reason.trim()||gate.current||action==='approve'&&!approvalValid)return;
  gate.current=true;setBusy(true);setError('');
  if(!request.current){request.current={space_id:spaceId,candidate_id:candidateId,source_sha256:state.source_sha256,expected_revision:state.revision,request_id:crypto.randomUUID().replaceAll('-',''),action,reason};
   if(action==='save')Object.assign(request.current,{document:current,geographic_binding:binding});
   if(action==='approve')request.current.approval={evidence_note:reason,valid_from:new Date(start).toISOString(),valid_until:new Date(end).toISOString(),bounds_m:bounds.map(row=>row.map(Number)),control_evidence_verified:checks[0],independent_checks_verified:checks[1],datum_verified:checks[2],extent_verified:checks[3]};
  }
  try{await value(await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request.current)}));
   const result=await read();if(mounted.current){setState(result);setDraft(null);setBinding(null);setAction(null);request.current=null;setNotice(`${actionLabels[action]}完成 · 修订 ${result.revision}`);releaseDraft();}
  }catch(e){if(mounted.current)setError(e instanceof Error?e.message:'操作失败。');}
  finally{gate.current=false;if(mounted.current)setBusy(false);}
 }
 const adopted=state?.adopted;
 return <section className="scene-registration" aria-label="场景空间基准">
  <header className="scene-registration-toolbar"><div>{state&&<><span>修订 {state.revision}</span><StatusBadge tone="neutral">{dirty?'未保存':labels[state.review_status]}</StatusBadge></>}</div><div>
   {state&&<><Button size="sm" variant="outline" disabled={busy} onClick={()=>download('配准资料.json',{document:current,geographic_binding:draft?binding:state.geographic_binding})}><DownloadSimple size={16}/>导出资料</Button>{state.can_edit&&<><Button size="sm" variant="outline" disabled={busy} onClick={()=>file.current?.click()}><UploadSimple size={16}/>导入资料</Button><Button size="sm" disabled={busy||!dirty} onClick={()=>open('save')}><FloppyDisk size={16}/>保存</Button><DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-md" variant="ghost" aria-label="配准资料更多操作" disabled={busy||dirty}><DotsThreeVertical size={24}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end">
    <DropdownMenuItem disabled={!['draft','rejected'].includes(state.review_status)||state.report?.calculation_status!=='checks_passed'||state.document?.synthetic} onSelect={()=>open('submit')}><ArrowUp size={16}/>提交审核</DropdownMenuItem>
    {state.can_review&&<><DropdownMenuSeparator/><DropdownMenuItem disabled={state.review_status!=='submitted'} onSelect={()=>open('approve')}><CheckCircle size={16}/>核准配准</DropdownMenuItem><DropdownMenuItem disabled={state.review_status!=='submitted'} onSelect={()=>open('reject')}><XCircle size={16}/>退回资料</DropdownMenuItem></>}
    <DropdownMenuSeparator/><DropdownMenuItem disabled={state.review_status!=='approved'||state.approved_revision===state.adopted_revision} onSelect={()=>open('adopt')}><CheckCircle size={16}/>采用核准修订</DropdownMenuItem><DropdownMenuItem disabled={!adopted} onSelect={()=>open('clear_adoption')}><ArrowDown size={16}/>撤下当前采用</DropdownMenuItem>
   </DropdownMenuContent></DropdownMenu></>}</>}
  </div></header>
  <input ref={file} type="file" accept=".json,application/json" hidden aria-label="导入配准资料文件" onChange={event=>{void importFile(event.target.files?.[0]);event.target.value='';}}/>
  {loading&&<output>正在读取配准资料…</output>}{busy&&<output>正在核对并处理配准资料…</output>}{sourceBlocked?<RegistrationSourceRecovery spaceId={spaceId} candidateId={candidateId}/>:error&&!action&&<div className="scene-registration-message" role="alert"><p>{error}</p><Button size="sm" variant="outline" disabled={busy||dirty} onClick={()=>setRefresh(n=>n+1)}>重新读取</Button></div>}{notice&&<output>{notice}</output>}
  {state&&!loading&&<>
   <div className="scene-registration-adoption"><span>{adopted?`当前采用核准修订 ${adopted.revision}`:'尚未采用核准修订'}</span>{adopted&&<><Button size="sm" variant="ghost" onClick={()=>setReviewOpen(true)}>查看核准依据</Button><Button size="sm" variant="outline" onClick={()=>setMapOpen(true)}>查看对象地图</Button></>}<span>已有服务发布保持固定</span></div>
   {current?<>{state.can_edit&&<div><Button size="sm" variant="outline" disabled={busy} onClick={()=>setBindingOpen(true)}>维护地理基准</Button></div>}<RegistrationWorkbench key={state.source_sha256} production input={current} geometry={geometry} buildings={[]} reviewStatus={dirty?'未保存':labels[state.review_status]} onPreviewChange={state.can_edit&&!busy?input=>void check(input):undefined}/>{geometryError&&<p role="status">三维预览暂不可用：{geometryError} 坐标清单仍可核对。</p>}</>:<div className="scene-registration-empty"><Compass size={36}/><h3>录入模型与目标基准的配准资料</h3><p>准备已知三维刚体参数、至少三个控制点和三个独立检查点，以及水平与高程基准依据。</p>{state.can_edit&&<><Button size="sm" variant="outline" onClick={template}><DownloadSimple size={16}/>下载空白资料模板</Button><p>模板绑定当前模型，参数、点位与门限需按实际控制资料填写，再导入核对。</p></>}</div>}
   {state.changed_at&&<p className="scene-registration-audit">{labels[state.review_status]} · {state.actor} · {new Date(state.changed_at).toLocaleString('zh-CN')}<br/>{state.reason}</p>}
  </>}
  <Drawer open={!!action} onClose={close} side="right" width="md" title={action?actionLabels[action]:''} description={action?explanations[action]:''} closeLabel="关闭配准操作" footer={<div className="scene-registration-footer"><Button size="sm" variant="outline" disabled={busy} onClick={close}>取消</Button><Button size="sm" disabled={busy||!reason.trim()||action==='approve'&&!approvalValid} onClick={()=>void execute()}>{action?actionLabels[action]:''}</Button></div>}>
   <div className="scene-registration-form"><label><span>{action==='approve'?'审核依据':'操作依据'}</span><Textarea maxLength={2000} value={reason} disabled={busy||!!request.current} onChange={event=>setReason(event.target.value)} aria-label="配准操作依据"/></label>
    {action==='approve'&&<><label><span>生效时间（本地时区）</span><Input type="datetime-local" value={start} disabled={busy||!!request.current} onChange={event=>setStart(event.target.value)}/></label><label><span>结束时间（本地时区）</span><Input type="datetime-local" value={end} disabled={busy||!!request.current} onChange={event=>setEnd(event.target.value)}/></label><fieldset><legend>适用模型范围（m）</legend>{['下界','上界'].map((title,row)=><div className="scene-registration-bounds" key={title}><span>{title}</span>{['X','Y','Z'].map((axis,i)=><label key={axis}><span>{axis}</span><Input type="number" step="any" aria-label={`${title} ${axis}`} value={bounds[row][i]??''} disabled={busy||!!request.current} onChange={event=>setBounds(old=>old.map((line,r)=>r===row?line.map((n,c)=>c===i?event.target.value:n):line))}/></label>)}</div>)}</fieldset>
    <fieldset><legend>独立审核确认</legend>{['已核实控制资料来源与责任','已核实检查点未用于同次拟合','已核实水平与高程基准','已核实适用范围及用途'].map((text,i)=><label className="scene-registration-check" key={text}><input type="checkbox" checked={checks[i]} disabled={busy||!!request.current} onChange={event=>setChecks(old=>old.map((n,index)=>index===i?event.target.checked:n))}/><span>{text}</span></label>)}</fieldset><p>以上确认需有实际资料支持，计算残差不替代现场精度验收。</p></>}
    {error&&<p role="alert">{error}</p>}{!!request.current&&!busy&&error&&<Button size="sm" variant="outline" onClick={()=>{request.current=null;setError('');}}>修订操作内容</Button>}
   </div>
  </Drawer>
  <RegistrationMap open={mapOpen} onClose={()=>setMapOpen(false)} url={endpoint+'/map?'+new URLSearchParams({space_id:spaceId,candidate_id:candidateId})}/>
  {bindingOpen&&current&&state&&<RegistrationGeographicBinding input={current} binding={draft?binding:state.geographic_binding} enabled={state.enabled_adapters.includes('wgs84_local_enu/1')} onClose={()=>setBindingOpen(false)} onApply={(document,reference)=>{setBindingOpen(false);void check(document,reference);}}/>}
  <Drawer open={reviewOpen} onClose={()=>setReviewOpen(false)} side="right" width="md" title="当前采用的核准依据" description={adopted?`固定修订 ${adopted.revision}`:''} closeLabel="关闭核准依据" footer={<div className="scene-registration-footer"><Button size="sm" onClick={()=>setReviewOpen(false)}>关闭</Button></div>}>
   {adopted&&<div className="scene-registration-form"><dl><dt>审核人</dt><dd>{adopted.reviewed_by}</dd><dt>审核时刻</dt><dd>{adopted.reviewed_at}</dd><dt>有效期</dt><dd>{adopted.approval?.valid_from}<br/>{adopted.approval?.valid_until}</dd><dt>审核依据</dt><dd>{adopted.approval?.evidence_note}</dd></dl><Button size="sm" variant="outline" onClick={()=>download('核准配准修订.json',adopted)}>导出核准修订</Button></div>}
  </Drawer>
 </section>;
}
