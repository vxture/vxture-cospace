import React,{useEffect,useMemo,useState} from 'react';
import {Button,ConfirmDestructive,Dialog,DialogContent,DialogDescription,DialogTitle,Input,StatusBadge} from '@vxture/design-system';
import {ArrowLeft,ArrowsInSimple,ArrowsOutSimple,Cube,FileText,ListBullets,SlidersHorizontal,X} from '@phosphor-icons/react';
import type {PreviewGeometry} from './geometry-preview-data';
import {displayCentimetres as centimetres,registrationPreview,type Point3,type RegistrationInput} from './registration-preview-data';
import {RegistrationComparison,RegistrationEvidenceDrawer,RegistrationModel,RegistrationPlan,RegistrationResidualChart,type PlanBuilding} from './registration-views';

type Props={input:RegistrationInput;geometry?:PreviewGeometry;buildings:PlanBuilding[];selected:string;onSelect:(id:string)=>void;onClose:()=>void;onApply:(input:RegistrationInput)=>void};
type Coordinates=Record<string,[string,string,string]>;
const validCoordinate=(value:string)=>value.trim()!==''&&Number.isFinite(Number(value))&&Math.abs(Number(value))<=10_000_000;

export function RegistrationEditor({input,geometry,buildings,selected,onSelect,onClose,onApply}:Props){
 const [coordinates,setCoordinates]=useState<Coordinates>(()=>Object.fromEntries(input.controls.map(p=>[p.id,p.target_m.map(String) as [string,string,string]])));
 const [compact,setCompact]=useState(()=>!window.matchMedia('(min-width: 1000px)').matches);
 const [listOpen,setListOpen]=useState(!compact),[inspectorOpen,setInspectorOpen]=useState(!compact),[modelOpen,setModelOpen]=useState(!compact);
 const [modelLarge,setModelLarge]=useState(false),[aligned,setAligned]=useState(true),[details,setDetails]=useState(false),[discard,setDiscard]=useState(false);
 useEffect(()=>{const query=window.matchMedia('(min-width: 1000px)');const change=()=>{setCompact(!query.matches);setListOpen(query.matches);setInspectorOpen(query.matches);setModelOpen(query.matches);};query.addEventListener('change',change);return()=>query.removeEventListener('change',change);},[]);
 const invalid=Object.values(coordinates).some(values=>!values.every(validCoordinate));
 const candidate=useMemo(()=>({...input,controls:input.controls.map(p=>({...p,target_m:coordinates[p.id].every(validCoordinate)?coordinates[p.id].map(Number) as Point3:p.target_m}))}),[input,coordinates]);
 const duplicate=new Set(candidate.controls.map(p=>p.target_m.join('/'))).size!==candidate.controls.length;
 const dirty=input.controls.some(p=>coordinates[p.id].some((value,i)=>!validCoordinate(value)||Number(value)!==p.target_m[i]));
 const report=useMemo(()=>registrationPreview(candidate),[candidate]),point=report.controls.find(p=>p.id===selected)||report.controls[0];
 const requestClose=()=>{if(dirty)setDiscard(true);else onClose();};
 useEffect(()=>{if(!dirty)return;const protect=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};window.addEventListener('beforeunload',protect);return()=>window.removeEventListener('beforeunload',protect);},[dirty]);
 const toggleList=()=>{setListOpen(v=>!v);if(compact){setInspectorOpen(false);setModelOpen(false);}};
 const toggleInspector=()=>{setInspectorOpen(v=>!v);if(compact){setListOpen(false);setModelOpen(false);}};
 const toggleModel=()=>{setModelOpen(v=>!v);if(compact){setListOpen(false);setInspectorOpen(false);}};
 const choose=(id:string)=>onSelect(id);
 const update=(axis:number,value:string)=>setCoordinates(current=>({...current,[point.id]:current[point.id].map((old,i)=>i===axis?value:old) as [string,string,string]}));
 const resetPoint=()=>{const original=input.controls.find(p=>p.id===point.id)!;setCoordinates(current=>({...current,[point.id]:original.target_m.map(String) as [string,string,string]}));};
 const leftInset=!compact&&listOpen?252:0,rightInset=!compact&&inspectorOpen?336:0;
 return <Dialog open onOpenChange={open=>{if(!open)requestClose();}}><DialogContent className="registration-editor" aria-describedby="registration-editor-description" onEscapeKeyDown={event=>{event.preventDefault();if(!details&&!discard)requestClose();}}>
  <header className="registration-editor-header"><div><Button variant="ghost" size="icon-md" aria-label="返回配准展示" onClick={requestClose}><ArrowLeft size={24}/></Button><DialogTitle>编辑配准</DialogTitle><span className="registration-editor-local">本地预览</span></div><div><Button size="sm" variant="outline" onClick={requestClose}>取消</Button><Button size="sm" disabled={!dirty||invalid||duplicate} onClick={()=>onApply(candidate)}>应用到预览</Button></div></header>
  <DialogDescription id="registration-editor-description" className="registration-editor-description">在全屏工程平面中核对控制点，修改目标坐标仅作用于本次本地预览。</DialogDescription>
  <div className="registration-editor-stage">
   <RegistrationPlan input={candidate} report={report} buildings={buildings} aligned={aligned} selected={point.id} onSelect={choose} interactive leftInset={leftInset} rightInset={rightInset}/>
   <div className="registration-editor-tools" role="group" aria-label="工作面板"><Button size="icon-md" variant="ghost" title="控制点清单" aria-label="切换控制点清单" aria-pressed={listOpen} onClick={toggleList}><ListBullets size={24}/></Button><Button size="icon-md" variant="ghost" title="模型小窗" aria-label="切换模型小窗" aria-pressed={modelOpen} onClick={toggleModel}><Cube size={24}/></Button><Button size="icon-md" variant="ghost" title="点位属性" aria-label="切换点位属性" aria-pressed={inspectorOpen} onClick={toggleInspector}><SlidersHorizontal size={24}/></Button></div>
   <div className="registration-editor-comparison" style={!compact?{left:`calc(50% + ${(leftInset-rightInset)/2}px)`}:undefined}><RegistrationComparison aligned={aligned} onChange={setAligned}/></div>
   {listOpen&&<aside className="registration-editor-points registration-floating-panel" aria-label="编辑控制点清单"><header><h2>控制点 <span>{report.controls.length}</span></h2><Button size="icon-md" variant="ghost" aria-label="收起控制点清单" onClick={()=>setListOpen(false)}><X size={24}/></Button></header><div>{report.controls.map(p=><button type="button" key={p.id} aria-label={`编辑控制点 ${p.id}`} aria-pressed={p.id===point.id} onClick={()=>choose(p.id)}><span className={`registration-point-key ${p.purpose}`}>{p.id}</span><span>{p.purpose==='check'?'检查点':'控制点'}</span><span className={p.horizontal_m>input.check_limits.horizontal_m?'registration-error':''}>{centimetres(p.horizontal_m)} cm</span></button>)}</div><footer>水平残差 · cm</footer></aside>}
   {modelOpen&&<section className="registration-editor-model registration-model registration-floating-panel" aria-label="模型对照小窗" data-expanded={modelLarge}><header><h2>模型对照</h2><div><Button size="icon-md" variant="ghost" aria-label={modelLarge?"缩小模型对照":"放大模型对照"} onClick={()=>setModelLarge(v=>!v)}>{modelLarge?<ArrowsInSimple size={24}/>:<ArrowsOutSimple size={24}/>}</Button><Button size="icon-md" variant="ghost" aria-label="收起模型小窗" onClick={()=>setModelOpen(false)}><X size={24}/></Button></div></header><RegistrationModel input={input} geometry={geometry} selected={point.id} onSelect={choose} fitPadding={1.08}/></section>}
   {inspectorOpen&&<aside className="registration-editor-inspector registration-floating-panel" aria-label="控制点属性"><header><h2><span className={`registration-point-key ${point.purpose}`}>{point.id}</span>{point.purpose==='check'?'检查点':'控制点'}</h2><Button size="icon-md" variant="ghost" aria-label="收起点位属性" onClick={()=>setInspectorOpen(false)}><X size={24}/></Button></header><div className="registration-inspector-content">
    <section><h3>模型坐标 <span>m · 只读</span></h3><dl className="registration-source-coordinates">{['X','Y','Z'].map((axis,i)=><div key={axis}><dt>{axis}</dt><dd>{point.source_m[i].toFixed(3)}</dd></div>)}</dl></section>
    <section><h3>目标坐标 <span>m</span></h3><div className="registration-coordinate-fields">{['E / 东向','N / 北向','U / 高程'].map((axis,i)=><label key={axis}><span>{axis}</span><Input type="number" step="0.001" min={-10_000_000} max={10_000_000} aria-label={`目标${axis}`} aria-invalid={!validCoordinate(coordinates[point.id][i])} value={coordinates[point.id][i]} onChange={event=>update(i,event.target.value)}/></label>)}</div>{(invalid||duplicate)&&<p role="alert" className="registration-error">{invalid?'请输入范围内的有限数值，不能留空。':'目标点坐标重复，请核对控制资料。'}</p>}<div className="registration-point-actions"><Button size="sm" variant="ghost" disabled={!input.controls.find(p=>p.id===point.id)!.target_m.some((value,i)=>String(value)!==coordinates[point.id][i])} onClick={resetPoint}>重置本点</Button><span>{invalid?'输入待修正':point.within_limits?'本点在门限内':'本点超出门限'}</span></div></section>
    <section className="registration-point-evidence"><h3>控制资料依据</h3><p>{point.evidence_ref}</p><Button size="sm" variant="outline" onClick={()=>setDetails(true)}><FileText size={16}/>依据与参数</Button></section>
    <RegistrationResidualChart input={candidate} report={report} selected={point.id} onSelect={choose}/>
   </div></aside>}
  </div>
  <footer className="registration-editor-status"><div><span className={`registration-point-key ${point.purpose}`}>{point.id}</span><span>{invalid||duplicate?'输入待修正':`水平残差 ${centimetres(point.horizontal_m)} cm · 高程残差 ${centimetres(point.vertical_m)} cm`}</span></div><div><StatusBadge tone={dirty?'warning':'neutral'}>{dirty?'未应用':'未修改'}</StatusBadge><span>米制工程平面 · 非地理底图</span></div></footer>
  <RegistrationEvidenceDrawer input={candidate} open={details} onClose={()=>setDetails(false)}/>
  <ConfirmDestructive open={discard} onOpenChange={setDiscard} verb="放弃" target="本地修改" consequence="未应用的目标坐标修改将被丢弃，展示页保留进入编辑前的资料。" cancelLabel="继续编辑" onConfirm={onClose}/>
 </DialogContent></Dialog>;
}
