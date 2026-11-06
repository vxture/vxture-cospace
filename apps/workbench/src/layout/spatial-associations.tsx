import React,{useEffect,useState} from 'react';
import {Button,Card,CardHeader,CardTitle,CardContent} from '@vxture/design-system';
import {SpaceContext} from './space-context';
import {ObjectAnnotations} from './object-annotations';
import {BusinessAssociations} from './business-associations';
import {ObjectRelations} from './object-relations';
import {recordLink,useRecordNavigation} from './record-navigation';
import {previewEndpoint} from './real-space-data';

export function SpatialAssociations(){
 const target=useRecordNavigation();
 const view=['business','relations'].includes(target.tab)?target.tab:'objects';
 const [visited,setVisited]=useState<string[]>([view]);
 useEffect(()=>{setVisited(old=>old.includes(view)?old:[...old,view]);},[view]);
 return <><nav className="module-subtabs" aria-label="空间关联视图">{[{id:'objects',label:'语义与几何'},{id:'business',label:'对象与业务'},{id:'relations',label:'对象间关系'}].map(item=><a key={item.id} href={recordLink('association',{tab:item.id})} aria-current={view===item.id?'page':undefined}>{item.label}</a>)}</nav><SpaceContext endpoint={previewEndpoint}/>{visited.map(id=><div key={id} className="module-subview" hidden={view!==id}>{id==='objects'?<ObjectAnnotations key={target.space}/>:id==='business'?<BusinessAssociations key={'business-'+target.space}/>:<ObjectRelations key={'relations-'+target.space}/>}</div>)}<p className="module-scope-note">关联变更形成当前场景的新候选。到构建中心核对，再到态势服务发布；已有发布保持固定。</p></>;
}
