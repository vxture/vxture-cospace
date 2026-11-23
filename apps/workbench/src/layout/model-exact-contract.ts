import type {XYZ} from './real-space-data';
const xyz=(v:unknown):v is XYZ=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n));
export type EngineeringSource={space:string;candidate:string;manifest:string;source:string;frame:string};
export type ExactPoint={point_id:string;point_index:number;anchor_m:XYZ};
export class ModelAccessChanged extends Error{}
export function validateExact(value:any,source:EngineeringSource):{state:string;points:ExactPoint[]}{
 if(value?.profile!=='cospace.model-exact/0.1'||value.space_id!==source.space||value.model_id!==source.candidate||value.source_manifest_sha256!==source.manifest||value.source_model_sha256!==source.source||value.frame_id!==source.frame||value.unit!=='m'||value.quality!=='source_precision_not_survey_acceptance'||!['ready','preparing','busy','unavailable','narrow_query'].includes(value.state)||!Array.isArray(value.points)||value.points.length>32||value.state!=='ready'&&value.points.length||value.points.some((p:ExactPoint)=>!p||!Number.isSafeInteger(p.point_index)||p.point_index<0||p.point_id!==source.source+':'+p.point_index||!xyz(p.anchor_m))||new Set(value.points.map((p:ExactPoint)=>p.point_index)).size!==value.points.length)throw new ModelAccessChanged('原始点与当前固定模型不一致。');
 return value;
}
