import type {SceneData,PublishedModel,ModelDisplay,XYZ} from './real-space-data';

export type ModelRef={space:string;identity:string;kind:'candidate'|'publication'};
export const xyz=(v:unknown):v is XYZ=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n));
const sha=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export const modelBase=(ref:ModelRef)=>`/${ref.kind==='candidate'?'candidates':'publications'}/${encodeURIComponent(ref.identity)}/`;

export function validateDisplay(value:{model:PublishedModel;display:ModelDisplay},ref:ModelRef):SceneData {
 const {model,display}=value,canonical=model?.members?.['spatial.npz']?.sha256,pub=model?.publication;
 if(!sha(canonical)||model.space_id!==ref.space||model.unit!=='m'||model.human_view?.source_model_sha256!==canonical||model.agent_view?.source_model_sha256!==canonical||
  (ref.kind==='candidate'?model.id!==ref.identity:!pub||pub.id!==ref.identity||pub.space_id!==ref.space||pub.candidate_id!==model.id||pub.source_model_sha256!==canonical))throw Error('空间或固定模型的来源绑定不一致。');
 if(display?.profile!=='cospace.model-display/0.1'||display.provider!=='potree/1.8.2'||!sha(display.id)||!sha(display.source_manifest_sha256)||display.source_model_sha256!==canonical||!['ready','preparing','unavailable','failed'].includes(display.state)||
  (ref.kind==='publication'&&display.source_manifest_sha256!==pub?.model_manifest_sha256))throw Error('显示派生与固定模型不一致。');
 if(display.state==='ready'){
  const expected=modelBase(ref)+`display/${display.id}/metadata.json`;
  const basis=display.model_to_display;
  if(display.entry!==expected||!xyz(display.origin_m)||!basis||basis.length!==3||!basis.every(xyz)||
   basis.some((row,i)=>basis.some((other,j)=>Math.abs(row.reduce((s,n,k)=>s+n*other[k],0)-(i===j?1:0))>1e-12))||
   display.point_count!==model.construction.model_points||typeof display.encoding_error_m!=='number'||!Number.isFinite(display.encoding_error_m)||display.encoding_error_m<0||display.encoding_error_m>.001)throw Error('显示坐标契约或精度预算无效。');
 }
 // Unknown future strategies cannot change the mature display path.
 if(!['baseline','task','adaptive','governance','combined'].includes(display.strategy||''))display.strategy='baseline';
 return {model,display,positions:new Float32Array(),colors:new Float32Array(),agent_points:[],objects:[],relations:[]};
}
