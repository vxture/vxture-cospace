import React,{useMemo,useState} from 'react';
import {Button,Table,TableHeader,TableBody,TableHead,TableRow,TableCell} from '@vxture/design-system';
import {ArrowsLeftRight,Compass,Cube,FileText,PencilSimple,Target} from '@phosphor-icons/react';
import type {PreviewGeometry} from './geometry-preview-data';
import {displayCentimetres as centimetres,registrationPreview,type RegistrationInput} from './registration-preview-data';
import './geometry-preview.css';
import './registration-workbench.css';

import {RegistrationComparison,RegistrationEvidenceDrawer,RegistrationMetrics,RegistrationModel,RegistrationPlan,RegistrationResidualChart,RegistrationStatus,type PlanBuilding} from './registration-views';
export type {PlanBuilding} from './registration-views';
type Props={input:RegistrationInput;geometry?:PreviewGeometry;buildings:PlanBuilding[];editorHref?:string;reviewStatus?:string};
const axisNames:Record<string,string>={right:'右',left:'左',forward:'前',backward:'后',up:'上',down:'下',east:'东',north:'北'};

export function RegistrationWorkbench({input,geometry,buildings,editorHref,reviewStatus}:Props){
 const report=useMemo(()=>registrationPreview(input),[input]);
 const [selected,setSelected]=useState(input.controls.find(p=>p.purpose==='check')?.id||input.controls[0]?.id||'');
 const [aligned,setAligned]=useState(true),[details,setDetails]=useState(false);
 const point=report.controls.find(p=>p.id===selected)||report.controls[0];
 const modelAxes=['X','Y','Z'].map((symbol,i)=>({symbol,name:axisNames[input.source.axes[i]]||input.source.axes[i]}));
 const targetAxes=[{symbol:'E',name:'东'},{symbol:'N',name:'北'},{symbol:'U',name:'高'}];
 return <section className="registration-workbench" aria-label="空间基准工作面">
  <header className="registration-heading"><div className="registration-heading-title"><Compass size={24}/><div><h1>模型与园区坐标对齐</h1><p>{input.source.frame_id} <ArrowsLeftRight size={14}/> {input.target.frame_id}<span>米制工程平面</span></p></div></div><div className="registration-heading-actions"><Button size="sm" variant="outline" onClick={()=>setDetails(true)}><FileText size={16}/>依据与参数</Button>{editorHref&&<Button asChild size="sm"><a href={editorHref+'&point='+encodeURIComponent(point.id)} target="_blank" rel="noopener noreferrer" title="在新标签页编辑配准"><PencilSimple size={16}/>编辑配准</a></Button>}</div></header>
  <div className="registration-summary" aria-label="参数核对状态"><RegistrationStatus report={report} reviewStatus={reviewStatus}/><RegistrationMetrics report={report}/><span className="registration-capability">地理定位能力另行核验</span></div>
  <div className="registration-views">
   <section className="registration-model" aria-label="源模型视图"><header className="registration-view-heading"><div><Cube size={18}/><h2>模型局部坐标</h2></div><span>X · Y · Z（m）</span></header>
    <RegistrationModel input={input} geometry={geometry} selected={point.id} onSelect={setSelected}/>
   </section>
   <section className="registration-target" aria-label="目标控制网视图"><header className="registration-view-heading"><div><Target size={18}/><h2>园区控制网</h2></div><RegistrationComparison aligned={aligned} onChange={setAligned}/></header>
    <RegistrationPlan input={input} report={report} buildings={buildings} aligned={aligned} selected={point?.id} onSelect={setSelected}/>
    <div className="registration-plan-caption"><span>米制工程平面 · 非地理底图</span><span>{aligned?'已应用候选参数':'原局部数值对照'}</span></div>
   </section>
  </div>

  <div className="registration-bottom"><section className="registration-controls" aria-label="控制点清单"><header className="registration-section-heading"><h2>控制点清单 <span>{report.controls.length}</span></h2><span>共 {report.controls.filter(p=>p.purpose==='fit').length} 个控制点，{report.controls.filter(p=>p.purpose==='check').length} 个检查点</span></header><div className="registration-table-scroll"><Table className="registration-coordinate-table"><TableHeader><TableRow><TableHead rowSpan={2} scope="col" className="registration-index">序号</TableHead><TableHead rowSpan={2} scope="col">点位 / 用途</TableHead><TableHead colSpan={3} scope="colgroup" className="registration-coordinate-group">模型坐标（m）</TableHead><TableHead colSpan={3} scope="colgroup" className="registration-coordinate-group">目标坐标（m）</TableHead><TableHead colSpan={2} scope="colgroup" className="registration-coordinate-group">计算残差（cm）</TableHead></TableRow><TableRow className="registration-axis-headings">{[...modelAxes,...targetAxes].map((axis,i)=><TableHead scope="col" key={axis.symbol} className={i===0||i===3?'registration-coordinate-group':undefined} title={`${axis.symbol}：${axis.name}`}><span>{axis.symbol}</span><small>{axis.name}</small></TableHead>)}<TableHead scope="col" className="registration-coordinate-group">水平</TableHead><TableHead scope="col">高程</TableHead></TableRow></TableHeader><TableBody>{report.controls.map((p,i)=><TableRow key={p.id} data-selected={point.id===p.id||undefined}><TableCell className="registration-index">{i+1}</TableCell><TableCell className="registration-name"><button type="button" aria-label={`选择控制点 ${p.id}`} aria-pressed={point.id===p.id} onClick={()=>setSelected(p.id)}><span className={`registration-point-key ${p.purpose}`}>{p.id}</span><span>{p.purpose==='check'?'检查点':'控制点'}</span></button></TableCell>{p.source_m.map((n,axis)=><TableCell key={`source-${axis}`} className={axis===0?'registration-coordinate-group':undefined} aria-label={`模型 ${modelAxes[axis].symbol} ${modelAxes[axis].name} ${n.toFixed(2)} 米`}>{n.toFixed(2)}</TableCell>)}{p.target_m.map((n,axis)=><TableCell key={`target-${axis}`} className={axis===0?'registration-coordinate-group':undefined} aria-label={`目标 ${targetAxes[axis].symbol} ${targetAxes[axis].name} ${n.toFixed(2)} 米`}>{n.toFixed(2)}</TableCell>)}<TableCell className="registration-coordinate-group"><span className={p.horizontal_m>input.check_limits.horizontal_m?'registration-error':''}>{centimetres(p.horizontal_m)}</span></TableCell><TableCell><span className={p.vertical_m>input.check_limits.vertical_m?'registration-error':''}>{centimetres(p.vertical_m)}</span></TableCell></TableRow>)}</TableBody></Table></div></section>
   <RegistrationResidualChart report={report} input={input} selected={point.id} onSelect={setSelected}/>
  </div>
  <p className="registration-footnote">坐标显示至厘米，计算残差显示至 0.1 cm；显示位数不代表地图实测精度。控制资料及成果精度待核验。</p>
  <RegistrationEvidenceDrawer input={input} open={details} onClose={()=>setDetails(false)} reviewStatus={reviewStatus}/>
 </section>;
}
