import {getJSON,previewEndpoint,type PublishedModel,type ModelObject,type ObjectRelation,type XYZ} from './real-space-data';
import {validateDisplay,modelBase,xyz,type ModelRef} from './model-display-contract';
export type {ModelRef} from './model-display-contract';

export async function loadDisplayScene(ref:ModelRef,signal:AbortSignal){return validateDisplay(await getJSON(modelBase(ref)+'api/display',signal),ref);}

export async function loadSceneObjects(ref:ModelRef,model:PublishedModel,signal:AbortSignal){
 if(!model.semantic_annotation)return {objects:[] as ModelObject[],relations:[] as ObjectRelation[]};
 const result=await getJSON<{model_id:string;publication_id?:string;publication_model_manifest_sha256?:string;source_model_sha256:string;frame_id:string;objects:ModelObject[];relations?:ObjectRelation[]}>(modelBase(ref)+'api/objects',signal);
 const canonical=model.members['spatial.npz'].sha256;
 if(result.model_id!==model.id||result.source_model_sha256!==canonical||result.frame_id!==model.frame_id||
  ref.kind==='publication'&&(result.publication_id!==ref.identity||result.publication_model_manifest_sha256!==model.publication?.model_manifest_sha256)||
  !Array.isArray(result.objects)||result.objects.length!==model.semantic_annotation.object_count||!result.objects.every(o=>xyz(o.anchor_m)&&o.evidence.sha256===canonical))throw Error('对象快照与当前固定模型不一致。');
 const relations=result.relations||[];
 if(!Array.isArray(relations)||relations.some(r=>!result.objects.some(o=>o.object_id===r.source_id)||!result.objects.some(o=>o.object_id===r.target_id)))throw Error('对象关系来源无效。');
 return {objects:result.objects,relations};
}
export async function loadAgentPoints(ref:ModelRef,model:PublishedModel,signal:AbortSignal){
 const response=await fetch(previewEndpoint+modelBase(ref)+'views.js',{signal,cache:'no-store'});
 if(!response.ok)throw Error('计算表达读取失败，请核对权限与版本状态。');
 const raw=await response.arrayBuffer(),member=model.members['views.js'];
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),n=>n.toString(16).padStart(2,'0')).join('');
 if(raw.byteLength!==member?.bytes||digest!==member.sha256)throw Error('计算表达摘要与固定模型不一致。');
 const text=new TextDecoder().decode(raw),prefix='window.PREVIEW_VIEWS=';
 if(!text.startsWith(prefix)||!text.endsWith(';'))throw Error('计算表达格式无效。');
 const values=JSON.parse(text.slice(prefix.length,-1));
 if(!Array.isArray(values.agent_points)||values.agent_points.length!==model.agent_view.surface_cells||!values.agent_points.every(xyz))throw Error('计算单元来源无效。');
 return values.agent_points as XYZ[];
}
