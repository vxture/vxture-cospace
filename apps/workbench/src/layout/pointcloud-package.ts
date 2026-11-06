/** Bounded P14 PLY layout and deterministic ZIP_STORE packaging. No coordinate conversion. */
export const CLOUD_MAX_BYTES=32*1024*1024,CLOUD_MAX_POINTS=1_000_000;
export type Declaration={frame_id:string;axes:[string,string,string];scope:'sensor_local'|'scene_local';description:string};
import type {PreviewGeometry,XYZ} from './geometry-preview-data';
export type CheckedCloud={file:File;raw:Uint8Array<ArrayBuffer>;points:number;colored:boolean;sha256:string;display:PreviewGeometry};
const encoder=new TextEncoder();
export async function sha256(raw:Uint8Array<ArrayBuffer>){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw))).map(v=>v.toString(16).padStart(2,'0')).join('');}
export function validateDeclaration(d:Declaration){
 if(!/^[A-Za-z0-9_/-]{1,100}$/.test(d.frame_id))throw Error('请填写1至100字的局部坐标系标识，仅使用英文字母、数字、下划线、斜线或连字符。');
 if(d.axes.length!==3||new Set(d.axes).size!==3||d.axes.some(v=>!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(v)))throw Error('请明确填写三条不同的轴语义，使用英文字母开头的标识。');
 if(!['sensor_local','scene_local'].includes(d.scope))throw Error('请选择局部坐标范围。');
 if(!d.description.trim()||d.description.length>500)throw Error('请填写1至500字的来源说明。');
}
export async function checkCloud(file:File,signal?:AbortSignal):Promise<CheckedCloud>{
 if(!file.name.toLowerCase().endsWith('.ply')||!file.size||file.size>CLOUD_MAX_BYTES)throw Error('请选择不超过32MiB的非空PLY文件。');
 if(file.name.length>160||/[\\/:\x00-\x1f]/.test(file.name))throw Error('文件名不能包含路径或控制字符，且最多160字。');
 const raw=new Uint8Array(await file.arrayBuffer());signal?.throwIfAborted();
 const lines:string[]=[];let offset=0;
 while(true){
  const end=raw.indexOf(10,offset),stop=end<0?raw.length:end+1,length=stop-offset;
  if(!length||length>1024||stop>8192)throw Error('PLY头部不符合要求：最多8KiB，每行不超过1024字节。');
  const line=raw.subarray(offset,stop);if(line.some(v=>v>127))throw Error('PLY头部必须为ASCII文本。');
  const text=new TextDecoder().decode(line).replace(/[\r\n]+$/,'');offset=stop;
  if(text==='end_header')break;
  if(!text.startsWith('comment '))lines.push(text);
 }
 const match=/^element vertex ([1-9][0-9]*)$/.exec(lines[2]||'');const points=match?Number(match[1]):0;
 if(!Number.isSafeInteger(points)||points<1||points>CLOUD_MAX_POINTS)throw Error('仅支持1至100万个点的单vertex点云。');
 const prefix=['ply','format binary_little_endian 1.0',`element vertex ${points}`,'property float x','property float y','property float z'];
 const rgb=['property uchar red','property uchar green','property uchar blue'];
 const same=(a:string[],b:string[])=>JSON.stringify(a)===JSON.stringify(b),colored=same(lines,prefix.concat(rgb));
 if(!same(lines,prefix)&&!colored)throw Error('仅支持二进制小端float32 XYZ，可附带uchar RGB；不支持ASCII、网格或额外属性。');
 const stride=colored?15:12;if(raw.length-offset!==points*stride)throw Error('PLY点数与文件负载长度不一致，文件可能截断或包含额外数据。');
 const view=new DataView(raw.buffer),sampleStride=Math.max(1,Math.ceil(points/10000)),positions:XYZ[]=[],colors:XYZ[]=[],min:XYZ=[Infinity,Infinity,Infinity],max:XYZ=[-Infinity,-Infinity,-Infinity];
 for(let i=0;i<points;i++){
  const p:XYZ=[0,0,0];for(let axis=0;axis<3;axis++){const v=view.getFloat32(offset+i*stride+axis*4,true);if(!Number.isFinite(v)||Math.abs(v)>1_000_000)throw Error('点坐标含无效数值或超出当前支持范围（绝对值100万米）。');p[axis]=v;min[axis]=Math.min(min[axis],v);max[axis]=Math.max(max[axis],v);}
  if(i%sampleStride===0){positions.push(p);colors.push(colored?[raw[offset+i*stride+12],raw[offset+i*stride+13],raw[offset+i*stride+14]]:[160,160,160]);}
  if(i%65536===0){await new Promise(resolve=>setTimeout(resolve,0));signal?.throwIfAborted();}
 }
 return {file,raw,points,colored,sha256:await sha256(raw),display:{point_count:points,bounds:[min,max],sampling:{method:'file_index_stride',stride:sampleStride,limit:10000,count:positions.length},points:positions,colors,unit:'',frame_id:'原文件局部坐标',axes:[],appearance:colored?'source_rgb':'neutral_not_rgb'}};
}
const crcTable=Uint32Array.from({length:256},(_,n)=>{let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
function crc32(raw:Uint8Array){let c=0xffffffff;for(const b of raw)c=crcTable[(c^b)&255]^(c>>>8);return (c^0xffffffff)>>>0;}
function zipStore(files:[string,Uint8Array<ArrayBuffer>][]){
 const parts:ArrayBuffer[]=[],central:ArrayBuffer[]=[];let offset=0,centralSize=0;
 for(const [name,raw] of files){
  const filename=encoder.encode(name),crc=crc32(raw),header=new Uint8Array(30+filename.length),h=new DataView(header.buffer);
  h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(12,33,true);h.setUint32(14,crc,true);h.setUint32(18,raw.length,true);h.setUint32(22,raw.length,true);h.setUint16(26,filename.length,true);header.set(filename,30);
  const entry=new Uint8Array(46+filename.length),e=new DataView(entry.buffer);
  e.setUint32(0,0x02014b50,true);e.setUint16(4,20,true);e.setUint16(6,20,true);e.setUint16(14,33,true);e.setUint32(16,crc,true);e.setUint32(20,raw.length,true);e.setUint32(24,raw.length,true);e.setUint16(28,filename.length,true);e.setUint32(42,offset,true);entry.set(filename,46);
  parts.push(header.buffer,raw.buffer);central.push(entry.buffer);offset+=header.length+raw.length;centralSize+=entry.length;
 }
 const end=new ArrayBuffer(22),e=new DataView(end);e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,centralSize,true);e.setUint32(16,offset,true);
 return new Blob([...parts,...central,end],{type:'application/zip'});
}
export async function preparePackage(cloud:CheckedCloud,declaration:Declaration){
 validateDeclaration(declaration);
 const coordinates={unit:'m',frame_id:declaration.frame_id,axes:declaration.axes,scope:declaration.scope,scene_alignment:'unverified'};
 const member={path:'cloud.ply',sha256:cloud.sha256,bytes:cloud.raw.length,points:cloud.points};
 const receipt={profile:'cospace.pointcloud-source/0.1',basis:'user_declared_file',original_name:cloud.file.name,cloud:member,coordinates,description:declaration.description.trim()};
 const json=(value:unknown)=>encoder.encode(JSON.stringify(value)+'\n');
 const source=json(receipt),sourceSha=await sha256(source);
 const manifest={profile:'cospace.pointcloud-input/0.1',cloud:member,coordinates,
  provenance:{kind:'existing_pointcloud',source_manifest_sha256:sourceSha,source_member_sha256:cloud.sha256,description:receipt.description},source_receipt_path:'source.json'};
 const bundle=zipStore([['input.json',json({profile:'cospace.input-upload/0.1',format:'ply_pointcloud'})],['snapshot/pointcloud.json',json(manifest)],['snapshot/cloud.ply',cloud.raw],['snapshot/source.json',source]]);
 return {bundle,sha256:await sha256(new Uint8Array(await bundle.arrayBuffer())),receipt};
}
