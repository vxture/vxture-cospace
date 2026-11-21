import React from 'react';
import {StatusBadge} from '@vxture/design-system';

export type AxisReadiness={status:string;title:string;action:string;axes:string[];resolved_axes:(string|null)[];unit:string};
const names:Record<string,string>={right:'右',left:'左',forward:'前',backward:'后',up:'上',down:'下',east:'东',west:'西',north:'北',south:'南'};
export function CoordinateReadiness({value}:{value:AxisReadiness}){
 return <div className="flex min-w-0 flex-col gap-sm text-body-small" aria-label="地图配准准备情况">
  <div><StatusBadge tone={value.status==='ready'?'success':'warning'}>{value.title}</StatusBadge></div>
  <dl className="flex flex-wrap gap-md">{value.axes.map((axis,i)=><div key={i} className="flex gap-xs"><dt>{'XYZ'[i]}</dt><dd className="break-words">{axis}{value.resolved_axes[i]&&<span className="text-muted-foreground"> · {names[value.resolved_axes[i]!]||value.resolved_axes[i]}</span>}</dd></div>)}</dl>
  <p className="text-muted-foreground">{value.action}</p>
 </div>;
}

export const axisConventions=[
 {id:'',label:'按来源资料选择坐标约定',axes:[]},
 {id:'rfu',label:'X右 · Y前 · Z上',axes:['right','forward','up']},
 {id:'flu',label:'FLU · X前 · Y左 · Z上',axes:['forward','left','up']},
 {id:'frd',label:'FRD · X前 · Y右 · Z下',axes:['forward','right','down']},
 {id:'rdf',label:'相机光学 · X右 · Y下 · Z前',axes:['right','down','forward']},
 {id:'enu',label:'ENU · X东 · Y北 · Z上',axes:['east','north','up']},
 {id:'ned',label:'NED · X北 · Y东 · Z下',axes:['north','east','down']},
];
