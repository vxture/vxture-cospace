import React,{lazy,Suspense,useEffect,useMemo,useRef,useState} from 'react';
import {Button,Drawer,StatusBadge,Table,TableHeader,TableBody,TableHead,TableRow,TableCell} from '@vxture/design-system';
import {ArrowsLeftRight,Compass,Cube,FileText,Target} from '@phosphor-icons/react';
import type {PreviewGeometry} from './geometry-preview-data';
import {displayMetres as metres,registrationPreview,type RegistrationInput,type RegistrationPreview,type ControlResidual} from './registration-preview-data';
import './geometry-preview.css';
import './registration-workbench.css';

const ModelCanvas=lazy(()=>import('./geometry-preview-canvas'));
export type PlanBuilding={id:string;name:string;x:number;y:number;width:number;depth:number;height:number};
type Props={input:RegistrationInput;geometry?:PreviewGeometry;buildings:PlanBuilding[]};

export function RegistrationWorkbench({input,geometry,buildings}:Props){
 const report=useMemo(()=>registrationPreview(input),[input]);
 const [selected,setSelected]=useState(input.controls.find(p=>p.purpose==='check')?.id||input.controls[0]?.id||'');
 const [aligned,setAligned]=useState(true),[details,setDetails]=useState(false);
 const point=report.controls.find(p=>p.id===selected)||report.controls[0];
 const markers=useMemo(()=>input.controls.map(p=>({id:p.id,label:p.id,position:p.source_m,kind:p.purpose})),[input]);
 return <section className="registration-workbench" aria-label="空间基准工作面">
  <header className="registration-heading"><div className="registration-heading-title"><Compass size={32}/><div><h1>模型与园区坐标对齐</h1><p>固定模型 · {input.source.frame_id} <ArrowsLeftRight size={14}/> {input.target.frame_id} · 米制</p></div></div><Button size="sm" variant="outline" onClick={()=>setDetails(true)}><FileText size={16}/>依据与参数</Button></header>
  <div className="registration-summary" aria-label="参数核对状态"><div className="registration-status"><StatusBadge tone={report.passed?'success':'danger'}>{report.passed?'检查点通过':'检查点超限'}</StatusBadge><StatusBadge tone="warning">待审核</StatusBadge><span>地理定位未开放</span></div><dl><div><dt>水平 RMSE</dt><dd>{metres(report.horizontal_rmse_m)}<small>m</small></dd></div><div><dt>高程 RMSE</dt><dd>{metres(report.vertical_rmse_m)}<small>m</small></dd></div><div><dt>独立检查点</dt><dd>{report.controls.filter(p=>p.purpose==='check').length}<small>个</small></dd></div></dl></div>
  <div className="registration-views">
   <section className="registration-model" aria-label="源模型视图"><header className="registration-view-heading"><div><Cube size={18}/><h2>模型局部坐标</h2></div><span>X / Y / Z · m</span></header>
    {geometry?<Suspense fallback={<div className="registration-model-loading" role="status">正在加载三维画面…</div>}><ModelCanvas fitPadding={.84} data={geometry} markers={markers} selected={point?.id} onSelect={setSelected}/></Suspense>:<div className="registration-model-loading">没有可用模型预览，可从下方清单核对坐标。</div>}
   </section>
   <section className="registration-target" aria-label="目标控制网视图"><header className="registration-view-heading"><div><Target size={18}/><h2>园区控制网</h2></div><div className="registration-compare" role="group" aria-label="配准前后"><Button size="sm" variant={!aligned?'secondary':'ghost'} aria-pressed={!aligned} onClick={()=>setAligned(false)}>配准前</Button><Button size="sm" variant={aligned?'secondary':'ghost'} aria-pressed={aligned} onClick={()=>setAligned(true)}>参数变换后</Button></div></header>
    <TargetPlan input={input} report={report} buildings={buildings} aligned={aligned} selected={point?.id} onSelect={setSelected}/>
    <div className="registration-plan-caption"><span>米制工程平面 · 非地理底图</span><span>{aligned?'已应用候选参数':'原局部数值对照'}</span></div>
   </section>
  </div>
  <div className="registration-selection" aria-live="polite"><span className={`registration-point-key ${point.purpose}`}>{point.id}</span><strong>{point.purpose==='check'?'独立检查点':'参数控制点'}</strong><span>水平差 {metres(point.horizontal_m)} m</span><span>高程差 {metres(point.vertical_m)} m</span><span className={point.within_limits?'':'registration-error'}>{point.within_limits?'本点在门限内':'本点超出门限'}</span></div>
  <div className="registration-bottom"><section className="registration-controls" aria-label="控制点清单"><header className="registration-section-heading"><h2>控制点清单</h2><span>共 {report.controls.filter(p=>p.purpose==='fit').length} 个控制点，{report.controls.filter(p=>p.purpose==='check').length} 个检查点</span></header><div className="registration-table-scroll"><Table><TableHeader><TableRow><TableHead className="registration-index">序号</TableHead><TableHead>点位 / 用途</TableHead><TableHead>模型坐标（m）</TableHead><TableHead>目标坐标（m）</TableHead><TableHead>水平 / 高程差（m）</TableHead></TableRow></TableHeader><TableBody>{report.controls.map((p,i)=><TableRow key={p.id} data-selected={point.id===p.id||undefined}><TableCell className="registration-index">{i+1}</TableCell><TableCell className="registration-name"><button type="button" aria-label={`选择控制点 ${p.id}`} aria-pressed={point.id===p.id} onClick={()=>setSelected(p.id)}><span className={`registration-point-key ${p.purpose}`}>{p.id}</span><span>{p.purpose==='check'?'检查点':'控制点'}</span></button></TableCell><TableCell>{p.source_m.map(n=>n.toFixed(2)).join(' / ')}</TableCell><TableCell>{p.target_m.map(n=>n.toFixed(2)).join(' / ')}</TableCell><TableCell><span className={!p.within_limits?'registration-error':''}>{metres(p.horizontal_m)} / {metres(p.vertical_m)}</span></TableCell></TableRow>)}</TableBody></Table></div></section>
   <ResidualChart report={report} input={input} selected={point.id} onSelect={setSelected}/>
  </div>
  <p className="registration-footnote">参数检查通过不等于现场精度核准。控制资料及适用范围待责任人审核。</p>
  <Drawer open={details} onClose={()=>setDetails(false)} side="right" width="md" title="配准依据与参数" description="只读 · 当前候选" closeLabel="关闭配准依据" footer={<div className="registration-drawer-footer"><Button size="sm" onClick={()=>setDetails(false)}>关闭</Button></div>}><div className="registration-evidence"><section><h3>来源模型</h3><dl><div><dt>模型</dt><dd>{input.source.candidate_id}</dd></div><div><dt>坐标 / 单位</dt><dd>{input.source.frame_id} · {input.source.unit} · {input.source.axes.join(' / ')}</dd></div></dl></section><section><h3>目标基准</h3><dl><div><dt>名称</dt><dd>{input.target.title}</dd></div><div><dt>水平基准</dt><dd>{input.target.horizontal_reference}</dd></div><div><dt>高程基准</dt><dd>{input.target.vertical_reference}</dd></div><div><dt>定义 / 依据</dt><dd>{input.target.definition_ref}<br/>{input.target.evidence_ref}</dd></div></dl></section><section><h3>检查要求</h3><dl><div><dt>水平 / 高程门限</dt><dd>{metres(input.check_limits.horizontal_m)} / {metres(input.check_limits.vertical_m)} m</dd></div><div><dt>审核状态</dt><dd>未审核 · 现场依据未核实</dd></div><div><dt>允许用途</dt><dd>参数核对预览；尚不开放地理定位</dd></div></dl></section><details><summary>转换参数与来源摘要</summary><p>方向：模型 → 园区控制网；已知三维刚体参数，未估计尺度。</p><pre>{input.matrix.map(row=>row.map(n=>n.toFixed(6).padStart(12)).join(' ')).join('\n')}</pre><p>模型清单摘要</p><code>{input.source.manifest_sha256}</code><p>模型内容摘要</p><code>{input.source.model_sha256}</code></details></div></Drawer>
 </section>;
}

function TargetPlan({input,report,buildings,aligned,selected,onSelect}:{input:RegistrationInput;report:RegistrationPreview;buildings:PlanBuilding[];aligned:boolean;selected:string;onSelect:(id:string)=>void}){
 const host=useRef<HTMLDivElement>(null),[size,setSize]=useState({width:640,height:350});
 useEffect(()=>{const element=host.current!;const observer=new ResizeObserver(()=>setSize({width:Math.max(320,element.clientWidth),height:Math.max(280,element.clientHeight)}));observer.observe(element);return()=>observer.disconnect();},[]);
 // Display one metric plane. No supplied point is reinterpreted as longitude.
 const matrix=aligned?input.matrix:[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]];
 const positions=report.controls.flatMap(p=>[p.source_m,p.target_m,p.predicted_m]);
 const minX=Math.floor((Math.min(...positions.map(p=>p[0]))-14)/20)*20,maxX=Math.ceil((Math.max(...positions.map(p=>p[0]))+14)/20)*20;
 const minY=Math.floor((Math.min(...positions.map(p=>p[1]))-14)/20)*20,maxY=Math.ceil((Math.max(...positions.map(p=>p[1]))+14)/20)*20;
 const plot={x:42,y:24,width:size.width-74,height:size.height-94};
 const scale=Math.min(plot.width/(maxX-minX),plot.height/(maxY-minY));
 const originX=plot.x+(plot.width-(maxX-minX)*scale)/2-minX*scale,originY=plot.y+(plot.height-(maxY-minY)*scale)/2+maxY*scale;
 const x=(v:number)=>originX+v*scale,y=(v:number)=>originY-v*scale;
 const xticks=Array.from({length:(maxX-minX)/20+1},(_,i)=>minX+i*20),yticks=Array.from({length:(maxY-minY)/20+1},(_,i)=>minY+i*20);
 function predicted(p:ControlResidual){return aligned?p.predicted_m:p.source_m;}
 return <div ref={host} className="registration-plan"><svg viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label={`园区控制网米制平面，${aligned?'候选参数变换后':'配准前'}，选中 ${selected}`}><title>控制点与模型的平面位置对照</title><desc>方形为目标控制点，圆形为模型点。使用下方可聚焦按钮或控制点清单选择同一点。</desc>
  <g className="registration-grid">{xticks.map(v=><line key={'x'+v} x1={x(v)} x2={x(v)} y1={y(minY)} y2={y(maxY)}/>)}{yticks.map(v=><line key={'y'+v} x1={x(minX)} x2={x(maxX)} y1={y(v)} y2={y(v)}/>)}</g>
  <g className="registration-plan-axis">{xticks.filter((_,i)=>i%2===0).map(v=><text key={v} x={x(v)} y={size.height-48} textAnchor="middle">{v}</text>)}{yticks.filter((_,i)=>i%2===0).map(v=><text key={v} x={22} y={y(v)+4} textAnchor="end">{v}</text>)}<text x={size.width-12} y={15} textAnchor="end">E (m)</text><text x={14} y={15}>N (m)</text></g>
  <g transform={`translate(${originX} ${originY}) scale(${scale} ${-scale})`}><g className="registration-plan-model" transform={`matrix(${matrix[0][0]} ${matrix[1][0]} ${matrix[0][1]} ${matrix[1][1]} ${matrix[0][3]} ${matrix[1][3]})`}><rect className="registration-site-boundary" x={0} y={0} width={100} height={60}/>{buildings.map(b=><rect key={b.id} className="registration-building" x={b.x} y={b.y} width={b.width} height={b.depth}/>)}</g></g>
  <g>{buildings.map(b=>{const px=b.x+b.width/2,py=b.y+b.depth*.2,tx=matrix[0][0]*px+matrix[0][1]*py+matrix[0][3],ty=matrix[1][0]*px+matrix[1][1]*py+matrix[1][3];return <text key={b.id} className="registration-building-label" x={x(tx)} y={y(ty)} textAnchor="middle">{b.name}</text>;})}</g>
  {report.controls.map(p=>{const target=p.target_m,position=predicted(p),active=p.id===selected;return <g key={p.id} className="registration-plan-control" data-selected={active} data-purpose={p.purpose}><line className="registration-displacement" x1={x(target[0])} y1={y(target[1])} x2={x(position[0])} y2={y(position[1])}/>{active&&<circle className="registration-selection-ring" cx={x(target[0])} cy={y(target[1])} r={15}/>}<rect className="registration-target-mark" x={x(target[0])-6} y={y(target[1])-6} width={12} height={12}/><circle className="registration-predicted-mark" cx={x(position[0])} cy={y(position[1])} r={3.5}/><text className="registration-control-label" x={x(target[0])+10} y={y(target[1])-10}>{p.id}</text></g>;})}
  <g className="registration-scale"><line x1={size.width-120} x2={size.width-120+20*scale} y1={size.height-6} y2={size.height-6}/><line x1={size.width-120} x2={size.width-120} y1={size.height-10} y2={size.height-3}/><line x1={size.width-120+20*scale} x2={size.width-120+20*scale} y1={size.height-10} y2={size.height-3}/><text x={size.width-120+10*scale} y={size.height-14} textAnchor="middle">20 m</text></g>
 </svg><div className="registration-plan-markers" role="group" aria-label="目标控制点">{report.controls.map(p=><button type="button" key={p.id} style={{left:`${x(p.target_m[0])/size.width*100}%`,top:`${y(p.target_m[1])/size.height*100}%`}} aria-label={`选择目标点 ${p.id}`} aria-pressed={p.id===selected} onClick={()=>onSelect(p.id)}/>)}</div><div className="registration-plan-legend"><span><i className="registration-legend-square"/>目标点</span><span><i className="registration-legend-circle"/>模型点</span><span>F 控制 · K 检查</span></div></div>;
}

function ResidualChart({report,input,selected,onSelect}:{report:RegistrationPreview;input:RegistrationInput;selected:string;onSelect:(id:string)=>void}){
 const points=report.controls.filter(p=>p.purpose==='check');
 // One scale for both dimensions; an error exceeding the limit stays visible.
 const maximum=Math.max(input.check_limits.horizontal_m,input.check_limits.vertical_m,...points.flatMap(p=>[p.horizontal_m,p.vertical_m]))*1.18;
 return <section className="registration-residuals" aria-label="独立检查误差"><header className="registration-section-heading"><h2>独立检查误差</h2><span>m</span></header><div className="registration-error-legend"><span><i className="horizontal"/>水平</span><span><i className="vertical"/>高程</span><span>虚线为门限</span></div><div className="registration-error-points">{points.map(p=><button type="button" key={p.id} className="registration-error-point" aria-label={`查看 ${p.id} 误差`} aria-pressed={selected===p.id} onClick={()=>onSelect(p.id)}><strong>{p.id}</strong><div>{(['horizontal','vertical'] as const).map(kind=>{const value=kind==='horizontal'?p.horizontal_m:p.vertical_m,limit=kind==='horizontal'?input.check_limits.horizontal_m:input.check_limits.vertical_m;return <div className="registration-error-row" key={kind}><div className="registration-error-track"><i className={kind+(value>limit?' exceeded':'')} style={{width:`${value/maximum*100}%`}}/><span className="registration-error-threshold" style={{left:`${limit/maximum*100}%`}}/></div><span className={value>limit?'registration-error':''}>{metres(value)}</span></div>;})}</div></button>)}</div><dl className="registration-limits"><div><dt>水平门限</dt><dd>≤ {metres(input.check_limits.horizontal_m)} m</dd></div><div><dt>高程门限</dt><dd>≤ {metres(input.check_limits.vertical_m)} m</dd></div></dl></section>;
}
