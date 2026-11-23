import {getJSON,previewEndpoint,type PublishedModel,type ModelObject,type ObjectRelation} from './real-space-data';
import {validateDisplay,modelBase,xyz,type ModelRef} from './model-display-contract';
export type {ModelRef} from './model-display-contract';

export class DisplayAccessError extends Error {}
export async function loadDisplayScene(ref:ModelRef,signal:AbortSignal){
 const response=await fetch(previewEndpoint+modelBase(ref)+'api/display',{signal,cache:'no-store'});
 if([401,403,409].includes(response.status))throw new DisplayAccessError('当前模型的访问或版本状态已变化，请重新打开。');
 if(!response.ok)throw new Error('显示资料暂不可读，请重试。');
 return validateDisplay(await response.json(),ref);
}

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
