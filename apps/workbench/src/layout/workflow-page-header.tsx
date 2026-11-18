import React from 'react';
import {useSceneDirectory} from './use-scene-directory';
import './workflow-page-header.css';

export function WorkflowPageHeader({space,icon,process,stage,version,revision,status,details,actions}:{space:string;icon:React.ReactNode;process:string;stage:string;version?:string;revision?:number;status?:React.ReactNode;details?:React.ReactNode;actions?:React.ReactNode}){
 const {spaces,loading}=useSceneDirectory();
 const scene=spaces.find(item=>item.id===space);
 const sceneTitle=scene?.name||(space?(loading?'正在读取场景':'场景信息不可用'):'未选择场景');
 return <header className="workflow-page-header">
  <span className="workflow-page-icon" aria-hidden="true">{icon}</span>
  <div className="workflow-page-copy">
   <div className="workflow-page-title"><h2><span>{process} · </span><span>{sceneTitle}</span>{version&&<span> · {version}</span>}</h2>{status}</div>
   <div className="workflow-page-meta"><strong>{stage}</strong>{scene?.scene_code&&<span>{scene.scene_code}</span>}{revision!==undefined&&<span>修订 R{String(revision).padStart(2,'0')}</span>}{details}</div>
  </div>
  {actions&&<div className="workflow-page-actions">{actions}</div>}
 </header>;
}
