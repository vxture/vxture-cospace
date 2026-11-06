export type XYZ=[number,number,number];
export type PreviewGeometry={point_count:number;bounds:[XYZ,XYZ];sampling:{method:string;stride:number;limit:number;count:number};points:XYZ[];colors:XYZ[];unit:string;frame_id:string;axes:string[];appearance:string};
export type PreviewResponse=PreviewGeometry&{profile:string;format?:string;space_id:string;input_id:string;candidate_id?:string;job_id?:string;kind?:string;task_id?:string|null;source_sha256:string;snapshot_sha256?:string;manifest_sha256?:string;quality:string;robot_ready:boolean};
const xyz=(p:unknown):p is XYZ=>Array.isArray(p)&&p.length===3&&p.every(v=>typeof v==='number'&&Number.isFinite(v));
export function validatePreview(value:unknown,expected:{space:string;input?:string;candidate?:string;source?:string;snapshot?:string;job?:string;kind?:string;manifest?:string;task?:string}){
 const v=value as PreviewResponse,sha=(s:unknown)=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
 if(!v||v.profile!==(expected.candidate?'cospace.anchor-preview/0.1':expected.job?'cospace.build-preview/0.1':'cospace.input-preview/0.1')||v.space_id!==expected.space||expected.input&&v.input_id!==expected.input||v.quality!=='unverified'||v.robot_ready!==false||!sha(v.source_sha256)||v.unit!=='m'||typeof v.frame_id!=='string'||!v.frame_id||!Array.isArray(v.axes)||v.axes.length!==3||!v.axes.every(a=>typeof a==='string'))throw Error('预览来源与当前记录不一致。');
 if(expected.candidate&&(v.candidate_id!==expected.candidate||v.manifest_sha256!==expected.manifest))throw Error('选点模型与当前候选不一致。');
 if(!expected.job&&!expected.candidate&&v.format!=='ply_pointcloud')throw Error('预览格式不受支持。');
 if(expected.source&&v.source_sha256!==expected.source||expected.snapshot&&v.snapshot_sha256!==expected.snapshot||expected.job&&(v.job_id!==expected.job||v.kind!==expected.kind||v.manifest_sha256!==expected.manifest)||expected.task&&v.task_id!==expected.task)throw Error('预览摘要与当前记录不一致。');
 if(!Number.isSafeInteger(v.point_count)||v.point_count<1||!Array.isArray(v.bounds)||v.bounds.length!==2||!v.bounds.every(xyz)||v.bounds[0].some((n,i)=>n>v.bounds[1][i]))throw Error('预览范围无效。');
 const s=v.sampling;
 if(!s||s.method!=='file_index_stride'||s.limit!==10000||s.stride!==Math.max(1,Math.ceil(v.point_count/10000))||s.count!==Math.ceil(v.point_count/s.stride)||!Array.isArray(v.points)||v.points.length!==s.count||!Array.isArray(v.colors)||v.colors.length!==s.count||!v.points.every(p=>xyz(p)&&p.every((n,i)=>n>=v.bounds[0][i]&&n<=v.bounds[1][i]))||!v.colors.every(p=>xyz(p)&&p.every(n=>Number.isInteger(n)&&n>=0&&n<=255)))throw Error('预览点数、颜色或预算无效。');
 return v;
}
export async function readPreview(url:string,signal:AbortSignal,maxBytes=2*1024*1024){
 if(!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>2*1024*1024)throw Error('预览读取预算无效。');
 const r=await fetch(url,{signal,cache:'no-store'});if(!r.ok)throw Error(r.status===403?'当前账户无权查看该资料或构建。':r.status===409?'该阶段尚未就绪，或来源校验未通过，请刷新核查。':'预览暂不可用，请重试。');
 const reader=r.body?.getReader();if(!reader)throw Error('预览响应无法读取。');const chunks:Uint8Array[]= [];let size=0;
 try{while(true){const result=await reader.read();if(result.done)break;size+=result.value.length;if(size>maxBytes)throw Error('预览响应超过显示预算。');chunks.push(result.value);}}finally{await reader.cancel();}
 const raw=new Uint8Array(size);let offset=0;for(const part of chunks){raw.set(part,offset);offset+=part.length;}return JSON.parse(new TextDecoder().decode(raw));
}
