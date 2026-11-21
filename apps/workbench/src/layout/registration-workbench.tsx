import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Button,Table,TableHeader,TableBody,TableHead,TableRow,TableCell} from '@vxture/design-system';
import {ArrowsLeftRight,Compass,Cube,FileText,PencilSimple,Target} from '@phosphor-icons/react';
import type {PreviewGeometry} from './geometry-preview-data';
import {displayMetres as metres,registrationPreview,type RegistrationInput} from './registration-preview-data';
import './geometry-preview.css';
import './registration-workbench.css';

import {RegistrationComparison,RegistrationEvidenceDrawer,RegistrationMetrics,RegistrationModel,RegistrationPlan,RegistrationResidualChart,RegistrationStatus,type PlanBuilding} from './registration-views';
import {RegistrationEditor} from './registration-editor';
export type {PlanBuilding} from './registration-views';
type Props={input:RegistrationInput;geometry?:PreviewGeometry;buildings:PlanBuilding[];onPreviewChange?:(input:RegistrationInput)=>void};

export function RegistrationWorkbench({input,geometry,buildings,onPreviewChange}:Props){
 const report=useMemo(()=>registrationPreview(input),[input]);
 const [selected,setSelected]=useState(input.controls.find(p=>p.purpose==='check')?.id||input.controls[0]?.id||'');
 const [aligned,setAligned]=useState(true),[details,setDetails]=useState(false),[editing,setEditing]=useState(false);
 const point=report.controls.find(p=>p.id===selected)||report.controls[0];
 const editButton=useRef<HTMLButtonElement>(null),previousEditing=useRef(false);
 useEffect(()=>{if(previousEditing.current&&!editing)editButton.current?.focus();previousEditing.current=editing;},[editing]);
 if(editing&&onPreviewChange)return <RegistrationEditor input={input} geometry={geometry} buildings={buildings} selected={point.id} onSelect={setSelected} onClose={()=>setEditing(false)} onApply={draft=>{onPreviewChange(draft);setEditing(false);}}/>;
 return <section className="registration-workbench" aria-label="空间基准工作面">
  <header className="registration-heading"><div className="registration-heading-title"><Compass size={24}/><div><h1>模型与园区坐标对齐</h1><p>{input.source.frame_id} <ArrowsLeftRight size={14}/> {input.target.frame_id}<span>米制工程平面</span></p></div></div><div className="registration-heading-actions"><Button size="sm" variant="outline" onClick={()=>setDetails(true)}><FileText size={16}/>依据与参数</Button>{onPreviewChange&&<Button ref={editButton} size="sm" onClick={()=>setEditing(true)}><PencilSimple size={16}/>编辑配准</Button>}</div></header>
  <div className="registration-summary" aria-label="参数核对状态"><RegistrationStatus report={report}/><RegistrationMetrics report={report}/><span className="registration-capability">地理定位未开放</span></div>
  <div className="registration-views">
   <section className="registration-model" aria-label="源模型视图"><header className="registration-view-heading"><div><Cube size={18}/><h2>模型局部坐标</h2></div><span>X / Y / Z · m</span></header>
    <RegistrationModel input={input} geometry={geometry} selected={point.id} onSelect={setSelected}/>
   </section>
   <section className="registration-target" aria-label="目标控制网视图"><header className="registration-view-heading"><div><Target size={18}/><h2>园区控制网</h2></div><RegistrationComparison aligned={aligned} onChange={setAligned}/></header>
    <RegistrationPlan input={input} report={report} buildings={buildings} aligned={aligned} selected={point?.id} onSelect={setSelected}/>
    <div className="registration-plan-caption"><span>米制工程平面 · 非地理底图</span><span>{aligned?'已应用候选参数':'原局部数值对照'}</span></div>
   </section>
  </div>

  <div className="registration-bottom"><section className="registration-controls" aria-label="控制点清单"><header className="registration-section-heading"><h2>控制点清单 <span>{report.controls.length}</span></h2><span>共 {report.controls.filter(p=>p.purpose==='fit').length} 个控制点，{report.controls.filter(p=>p.purpose==='check').length} 个检查点</span></header><div className="registration-table-scroll"><Table><TableHeader><TableRow><TableHead className="registration-index">序号</TableHead><TableHead>点位 / 用途</TableHead><TableHead>模型坐标（m）</TableHead><TableHead>目标坐标（m）</TableHead><TableHead>水平 / 高程差（m）</TableHead></TableRow></TableHeader><TableBody>{report.controls.map((p,i)=><TableRow key={p.id} data-selected={point.id===p.id||undefined}><TableCell className="registration-index">{i+1}</TableCell><TableCell className="registration-name"><button type="button" aria-label={`选择控制点 ${p.id}`} aria-pressed={point.id===p.id} onClick={()=>setSelected(p.id)}><span className={`registration-point-key ${p.purpose}`}>{p.id}</span><span>{p.purpose==='check'?'检查点':'控制点'}</span></button></TableCell><TableCell>{p.source_m.map(n=>n.toFixed(2)).join(' / ')}</TableCell><TableCell>{p.target_m.map(n=>n.toFixed(2)).join(' / ')}</TableCell><TableCell><span className={!p.within_limits?'registration-error':''}>{metres(p.horizontal_m)} / {metres(p.vertical_m)}</span></TableCell></TableRow>)}</TableBody></Table></div></section>
   <RegistrationResidualChart report={report} input={input} selected={point.id} onSelect={setSelected}/>
  </div>
  <p className="registration-footnote">参数检查通过不等于现场精度核准。控制资料及适用范围待责任人审核。</p>
  <RegistrationEvidenceDrawer input={input} open={details} onClose={()=>setDetails(false)}/>
 </section>;
}
