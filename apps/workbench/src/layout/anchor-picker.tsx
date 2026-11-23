import type {GeometryFocus,GeometryMarker} from './geometry-preview-canvas';
import React from 'react';
import {EngineeringModelCanvas,type EngineeringSource} from './engineering-model-canvas';
import type {XYZ} from './real-space-data';
import './geometry-preview.css';
export function AnchorPicker({source,onPick,disabled,markers,selected,onSelect,focus,editing,anchor,onAccessLost}:{source:EngineeringSource;onPick:(index:number)=>void;disabled:boolean;markers?:GeometryMarker[];selected?:string;onSelect?:(id:string)=>void;focus?:GeometryFocus;editing?:boolean;anchor?:XYZ;onAccessLost?:()=>void}){
 return <section aria-label="三维画面选点" className="geometry-preview"><h4>三维模型</h4><p>{editing?'双击可见点查询局部原始点，核对并确认后更新对象位置。':'点击对象标记查看属性；从清单可定位到模型。'}</p>
 <EngineeringModelCanvas source={source} markers={markers} selected={selected} onSelect={onSelect} focus={focus} anchor={anchor} contextKey={selected} onConfirmPoint={disabled?undefined:point=>onPick(point.point_index)} onAccessLost={onAccessLost}/>
 </section>;
}
