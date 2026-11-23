import {businessEndpoint} from './business-endpoint';
import {validateDisplay,type ModelRef} from './model-display-contract';
import type {SceneData,XYZ} from './real-space-data';
import {validateExact,ModelAccessChanged,type EngineeringSource} from './model-exact-contract';
export {validateExact,ModelAccessChanged,type EngineeringSource,type ExactPoint} from './model-exact-contract';
export async function boundedJSON(path:string,signal:AbortSignal,budget=64*1024){
 const response=await fetch(businessEndpoint+path,{signal,cache:'no-store'});
 if([401,403,409].includes(response.status))throw new ModelAccessChanged('模型的访问或版本状态已变化，请重新打开。');
 if(!response.ok)throw Error('原始模型数据暂不可读，请重试。');
 const reader=response.body?.getReader();if(!reader)throw Error('模型数据响应为空。');
 const parts:Uint8Array[]=[];let length=0;
 try{while(true){const next=await reader.read();if(next.done)break;length+=next.value.byteLength;if(length>budget)throw Error('模型数据超过读取预算。');parts.push(next.value);}}
 catch(error){await reader.cancel();throw error;}finally{reader.releaseLock();}
 const raw=new Uint8Array(length);let offset=0;for(const part of parts){raw.set(part,offset);offset+=part.length;}
 return JSON.parse(new TextDecoder().decode(raw));
}
export async function engineeringScene(ref:ModelRef,signal:AbortSignal,expected?:EngineeringSource):Promise<SceneData>{
 const data=validateDisplay(await boundedJSON('/candidates/'+encodeURIComponent(ref.identity)+'/api/display',signal),ref);
 if(expected&&(data.display?.source_manifest_sha256!==expected.manifest||data.display.source_model_sha256!==expected.source||data.model.frame_id!==expected.frame))throw new ModelAccessChanged('显示模型与当前工程资料不一致，请重新读取。');
 return data;
}
export function waitForModel(signal:AbortSignal,ms=1000){return new Promise<void>((resolve,reject)=>{
 if(signal.aborted){reject(new DOMException('Aborted','AbortError'));return;}
 const abort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
 const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);signal.addEventListener('abort',abort,{once:true});
});}
export async function exactPoints(source:EngineeringSource,query:{point:XYZ;radius:number}|{index:number},signal:AbortSignal,onPreparing?:()=>void){
 const parameters=new URLSearchParams({manifest_sha256:source.manifest,source_sha256:source.source});
 if('index' in query)parameters.set('point_index',String(query.index));
 else{parameters.set('x',String(query.point[0]));parameters.set('y',String(query.point[1]));parameters.set('z',String(query.point[2]));parameters.set('radius_m',String(query.radius));}
 const deadline=performance.now()+60_000;
 while(true){
  const result=validateExact(await boundedJSON('/candidates/'+encodeURIComponent(source.candidate)+'/api/exact?'+parameters,signal),source);
  if(!['preparing','busy'].includes(result.state))return result;
  onPreparing?.();if(performance.now()>deadline)throw Error('精确数据仍在准备，请稍后重试；当前点位未改变。');await waitForModel(signal);
 }
}
export async function exactPoint(source:EngineeringSource,index:number,signal:AbortSignal){
 const value=await exactPoints(source,{index},signal);
 if(value.state!=='ready'||value.points.length!==1||value.points[0].point_index!==index)throw Error('此原始点暂不可确认，请稍后重试。');
 return value.points[0];
}
export async function exactObjects(source:EngineeringSource,signal:AbortSignal){
 const parameters=new URLSearchParams({manifest_sha256:source.manifest,source_sha256:source.source}),deadline=performance.now()+60_000;
 while(true){
  const value=await boundedJSON('/candidates/'+encodeURIComponent(source.candidate)+'/api/exact-objects?'+parameters,signal,2*1024*1024);
  if(['preparing','busy'].includes(value.state)){if(performance.now()>deadline)throw Error('对象的原始点依据仍在准备，请稍后重试。');await waitForModel(signal);continue;}
  if(value.state!=='ready')throw Error('对象的原始点依据暂不可用，请稍后重试。');
  if(value.model_id!==source.candidate||value.space_id!==source.space||value.frame_id!==source.frame||value.source_model_sha256!==source.source||value.source_manifest_sha256!==source.manifest||value.unit!=='m')throw new ModelAccessChanged('对象与当前固定模型不一致。');
  if(!Array.isArray(value.objects)||value.objects.length>100||value.objects.some((p:{anchor_m?:XYZ})=>!Array.isArray(p.anchor_m)||p.anchor_m.length!==3||!p.anchor_m.every(Number.isFinite)))throw Error('对象锚点响应无效。');
  return value;
 }
}
export async function engineeringObjects(space:string,candidate:string,signal:AbortSignal){
 const scene=await engineeringScene({space,identity:candidate,kind:'candidate'},signal);
 const manifest=scene.display!.source_manifest_sha256;
 const objects=await exactObjects({space,candidate,manifest,source:scene.display!.source_model_sha256,frame:scene.model.frame_id},signal);
 return {manifest,objects};
}
