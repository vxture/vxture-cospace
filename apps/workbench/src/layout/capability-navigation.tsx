import {Database,Files,Paperclip,Cube,Stack,GitBranch,Clock,FileText,Archive,CaretLeft} from '@phosphor-icons/react';
import {runGuarded} from './unsaved-navigation';
import {CreateSceneButton} from './create-scene';
import {Button} from '@vxture/design-system';
import React from 'react';
import {NativeSelect} from '@vxture/design-system';
import {recordLink,useRecordNavigation} from './record-navigation';
import {moduleNames,ModuleRoute} from './product-navigation';
import {SceneSpace} from './scene-directory';
import './capability-navigation.css';
const dataIcons:Record<string,typeof Database>={inputs:Files,references:Paperclip,pointcloud:Cube,batches:Archive,versions:Stack,lineage:GitBranch};
const capabilities:Record<ModuleRoute,[string,string][]>={data:[['inputs','资料与预检'],['references','配套资料'],['pointcloud','场景点云'],['batches','采集批次'],['versions','场景版本'],['lineage','来源追溯']],build:[['flow','构建流程'],['tasks','构建任务'],['candidate','当前模型候选']],association:[['objects','语义与几何'],['ifc','IFC 构件资料'],['business','对象与业务'],['relations','对象间关系']],delivery:[['','发布与交付']],space:[['','固定发布预览']],ontology:[['','规则与版本']]};
export function CapabilityNavigation({route,view,onToggle}:{route:ModuleRoute;view?:string;onToggle?:()=>void}){
 const target=useRecordNavigation(),items=capabilities[route],active=view||target.tab||items[0][0];
 return <aside id="data-scene-sidebar" className="data-sidebar capability-sidebar"><header className="capability-heading">{route==='data'&&<Database size={18}/>}<strong>{moduleNames[route]}</strong>{onToggle&&<Button variant="ghost" size="icon-sm" aria-label="收起能力导航" onClick={onToggle}><CaretLeft size={14}/></Button>}</header><div className="capability-surface" onClick={event=>{if(innerWidth<1100&&(event.target as HTMLElement).closest('a'))onToggle?.();}}><nav aria-label={`${moduleNames[route]}能力导航`}>{items.map(([id,label])=><a key={id} id={`data-tab-${id}`} href={recordLink(route,{tab:id,...(route==='build'&&id!=='candidate'?{input:target.input||'',job:target.job||'',batch:target.batch||''}:{})})} aria-current={active===id?'page':undefined}>{route==='data'&&React.createElement(dataIcons[id],{size:18})}{label}</a>)}</nav>{route==='data'&&<a href={recordLink('data',{scope:'all'})}><Database size={18}/>共用数据目录</a>}</div></aside>;
}
export function SceneScope({spaces,current,onChoose,loading,error,onRefresh}:{spaces:SceneSpace[];current:string;onChoose:(id:string)=>void;loading:boolean;error:string;onRefresh:()=>void}){
 return <div className="scene-scope" aria-label="当前操作场景"><label htmlFor="workbench-scene">操作场景</label><NativeSelect id="workbench-scene" value={current} disabled={loading} onChange={e=>{const id=e.target.value;e.target.value=current;void runGuarded(()=>onChoose(id));}}><option value="">请选择场景空间</option>{current&&!spaces.some(s=>s.id===current)&&<option value={current}>场景不可访问</option>}{spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect><Button size="sm" variant="ghost" disabled={loading} onClick={()=>{void runGuarded(onRefresh);}}>刷新场景</Button><CreateSceneButton onCreated={id=>{void runGuarded(()=>{onRefresh();onChoose(id);});}}/>{loading&&<span role="status">正在读取场景…</span>}{error&&<span role="alert">{error}</span>}</div>;
}
