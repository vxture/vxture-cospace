import {businessEndpoint} from './business-endpoint';
// Fixed publication display data. Parse the saved JSON assignment; never execute views.js.
export const previewEndpoint=businessEndpoint;
export type XYZ=[number,number,number];
export type FixedPublication={display_code?:string;version_code?:string;build_code?:string;lifecycle_state?:string;id:string;candidate_id:string;space_id?:string;created_at:string;preview_url:string;model_manifest_sha256:string;source_model_sha256:string};
export type DirectorySpace={publication_id:string|null;state:string;id:string;name:string;project_id:string;publications:FixedPublication[]};
export type ObjectRelation={relation_id:string;type_id:string;source_id:string;target_id:string;note:string;confirmation:string};
export type ModelObject={object_id:string;type_id:string;properties:Record<string,string>;anchor_m:XYZ;confirmation:string;business_links?:{ref:{record_id:string;sha256:string};record:{title:string;source_system:string;external_id:string;version:string;fields:Record<string,string>}}[];evidence:{kind:string;member:string;sha256:string;point_index:number}};
export type PublishedModel={id:string;label:string;space_id:string;frame_id:string;axes:string[];unit:string;data_kind:string;publication?:FixedPublication;inspection_files?:string[];
 construction:{input_frames:number;used_frames:number;model_points:number};agent_view:{surface_cells:number;resolution_m:number;source_model_sha256:string};
 human_view:{appearance?:string;source_model_sha256:string};members:Record<string,{sha256:string;bytes:number}>;
 semantic_annotation?:{object_count:number};bounds_m:[XYZ,XYZ];limitations:string[]};
export type SceneData={model:PublishedModel;positions:Float32Array;colors:Float32Array;agent_points:XYZ[];objects:ModelObject[];relations:ObjectRelation[]};
export function realScreenHref(space:string,publication:string){return `/space?screen=space&preview=1&space=${encodeURIComponent(space)}&publication=${encodeURIComponent(publication)}`;}
export async function getJSON<T>(path:string,signal?:AbortSignal):Promise<T>{const response=await fetch(`${previewEndpoint}${path}`,{signal});if(!response.ok)throw Error(`读取失败（${response.status}），请核对空间与发布记录。`);return response.json();}
function xyz(value:unknown):value is XYZ{return Array.isArray(value)&&value.length===3&&value.every(v=>typeof v==='number'&&Number.isFinite(v));}
export function candidateScreenHref(space:string,job:string){return `/space?${new URLSearchParams({screen:'space',preview:'1',space,job})}`;}
export function loadPublishedScene(space:string,publication:string,signal:AbortSignal){return loadModelScene(space,publication,'publication',signal);}
export function loadCandidateScene(space:string,candidate:string,signal:AbortSignal){return loadModelScene(space,candidate,'candidate',signal);}
async function loadModelScene(space:string,identity:string,kind:'candidate'|'publication',signal:AbortSignal):Promise<SceneData>{
 const publication=kind==='publication'?identity:'';
 const base=`/${kind==='publication'?'publications':'candidates'}/${encodeURIComponent(identity)}/`;
 const model=await getJSON<PublishedModel>(base+'api/preview',signal);
 const sha=model.members?.['spatial.npz']?.sha256;
 if(!sha||model.space_id!==space||(publication?(!model.publication||model.publication.id!==publication||model.publication.space_id!==space||model.publication.candidate_id!==model.id||model.publication.source_model_sha256!==sha):model.id!==identity)||model.human_view.source_model_sha256!==sha||model.agent_view.source_model_sha256!==sha)throw Error('空间、发布或双视图来源绑定不一致。');
 async function member(name:string){
  const response=await fetch(`${previewEndpoint}${base}${name}`,{signal});if(!response.ok)throw Error('真实几何读取失败。');
  const bytes=await response.arrayBuffer();
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  if(bytes.byteLength!==model.members[name].bytes||digest!==model.members[name].sha256)throw Error('显示几何摘要不匹配，请核对固定发布。');
  return bytes;
 }
 const [bytes,ply]=await Promise.all([member('views.js'),member('human.ply')]);
 const text=new TextDecoder().decode(bytes),prefix='window.PREVIEW_VIEWS=';
 if(!text.startsWith(prefix)||!text.endsWith(';'))throw Error('不支持的显示数据格式。');
 const data=JSON.parse(text.slice(prefix.length,-1));
 if(!Array.isArray(data.agent_points)||data.agent_points.length!==model.agent_view.surface_cells||!data.agent_points.every(xyz))throw Error('表面单元数量或坐标无效。');
 // Existing NYU views.js is sampled. Load the full frozen PLY for the human view.
 const {PLYLoader}=await import('three/addons/loaders/PLYLoader.js');
 const parsed=new PLYLoader().parse(ply),position=parsed.getAttribute('position'),color=parsed.getAttribute('color');
 const positions=new Float32Array(position.count*3),colors=new Float32Array(position.count*3);
 try{
  if(position.count!==model.construction.model_points||!color||color.count!==position.count)throw Error('人视图点数与固定模型不一致。');
  for(let i=0;i<position.count;i++){positions.set([position.getX(i),position.getY(i),position.getZ(i)],i*3);colors.set([color.getX(i),color.getY(i),color.getZ(i)],i*3);}
  if(!positions.every(Number.isFinite)||!colors.every(v=>Number.isFinite(v)&&v>=0&&v<=1))throw Error('人视图坐标或颜色无效。');
 }finally{parsed.dispose();}
 let objects:ModelObject[]=[],relations:ObjectRelation[]=[];
 if(model.semantic_annotation){
  const result=await getJSON<{model_id:string;publication_id:string;publication_model_manifest_sha256:string;source_model_sha256:string;frame_id:string;objects:ModelObject[];relations?:ObjectRelation[]}>(base+'api/objects',signal);
  if(result.model_id!==model.id||(publication&&(result.publication_id!==publication||result.publication_model_manifest_sha256!==model.publication?.model_manifest_sha256))||result.source_model_sha256!==sha||result.frame_id!==model.frame_id||!Array.isArray(result.objects)||result.objects.length!==model.semantic_annotation.object_count||!result.objects.every(o=>xyz(o.anchor_m)&&o.evidence.sha256===sha))throw Error('对象快照与当前发布不一致。');
  objects=result.objects;relations=result.relations||[];
  if(!Array.isArray(relations)||relations.some(r=>!objects.some(o=>o.object_id===r.source_id)||!objects.some(o=>o.object_id===r.target_id)))throw Error("关系端点与固定对象不一致。");
 }
 return {model,positions,colors,agent_points:data.agent_points,objects,relations};
}
