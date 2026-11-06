import {rigidPose,type ProcessFrame} from './build-process-data';
export const RGBD_PROFILE='cospace.rgbd-input-preview/0.1';
export type RGBDFrame={index:number;source_index:number;depth:string;rgb:string;depth_sha256:string;rgb_sha256:string;source_time_us:number|null;relative_time_us:number|null;pair_delta_us:number|null;pose:number[][]|null};
export type RGBDDirectory={profile:string;space_id:string;input_id:string;snapshot_sha256:string;tracking_sha256:string;input_frames:number;pose_frames:number;frames:RGBDFrame[];source_clock:string;frame_id:string;axes:string[];unit:string;quality:string;robot_ready:boolean;payload_checked:false};
export type RGBDImage={profile:string;kind:string;space_id:string;input_id:string;snapshot_sha256:string;tracking_sha256:string;frame:RGBDFrame;source_size:number[];display_size:number[];display_rule:string;depth_range_m:number[];invalid_depth:string;valid_depth_pixels:number;rgb_png:string;depth_png:string;payload_checked:string;quality:string;robot_ready:boolean};
export type RGBDBinding={space:string;input:string;snapshot?:string;tracking?:string};
const integer=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>=0;
const time=(v:unknown)=>v===null||integer(v);
const sha=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const fail=()=>{throw Error('RGB-D来源校验未通过，请核查当前资料。');};
function binding(v:RGBDDirectory|RGBDImage,e:RGBDBinding){
 if(!v||v.profile!==RGBD_PROFILE||v.space_id!==e.space||v.input_id!==e.input||!sha(v.snapshot_sha256)||!sha(v.tracking_sha256)||e.snapshot&&v.snapshot_sha256!==e.snapshot||e.tracking&&v.tracking_sha256!==e.tracking||v.quality!=='unverified'||v.robot_ready!==false)fail();
}
export function validRGBDFrame(f:RGBDFrame){
 return !!f&&integer(f.index)&&f.index<500&&integer(f.source_index)&&f.source_index<500&&typeof f.depth==='string'&&f.depth.length<=200&&/^[A-Za-z0-9_.-]+\.pgm$/.test(f.depth)&&typeof f.rgb==='string'&&f.rgb.length<=200&&/^[A-Za-z0-9_.-]+\.ppm$/.test(f.rgb)&&sha(f.depth_sha256)&&sha(f.rgb_sha256)&&time(f.source_time_us)&&time(f.relative_time_us)&&(f.pair_delta_us===null||Number.isSafeInteger(f.pair_delta_us))&&(f.pose===null||rigidPose(f.pose));
}
export function validateRGBDDirectory(value:unknown,e:RGBDBinding):RGBDDirectory{
 const v=value as RGBDDirectory;binding(v,e);
 if(!integer(v.input_frames)||!v.input_frames||v.input_frames>500||!integer(v.pose_frames)||!v.pose_frames||v.pose_frames>v.input_frames||!Array.isArray(v.frames)||v.frames.length!==v.input_frames||v.unit!=='m'||v.frame_id!=='first_depth_camera_anchor'||JSON.stringify(v.axes)!=='["right","down","forward"]'||!['filename_time_unverified_utc','unverified'].includes(v.source_clock)||v.payload_checked!==false||new TextEncoder().encode(JSON.stringify(v)).length>1024*1024)fail();
 const timed=v.frames.every(f=>f.source_time_us!==null);
 v.frames.forEach((f,i)=>{if(!validRGBDFrame(f)||f.index!==i||i>0&&f.source_index<=v.frames[i-1].source_index||(f.pose!==null)!==(i<v.pose_frames)||timed&&(f.relative_time_us!==f.source_time_us!-v.frames[0].source_time_us!||i>0&&f.source_time_us!<=v.frames[i-1].source_time_us!)||!timed&&f.relative_time_us!==null)fail();});
 return v;
}
const crcTable=Array.from({length:256},(_,i)=>{let c=i;for(let j=0;j<8;j++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
function png(value:unknown,alpha:boolean){
 if(typeof value!=='string'||value.length>1024*1024||!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value))return false;
 try{const s=atob(value.slice(22));if(s.length<57||s.slice(0,8)!=='\x89PNG\r\n\x1a\n')return false;const b=Uint8Array.from(s,v=>v.charCodeAt(0)),d=new DataView(b.buffer);
  if(d.getUint32(8)!==13||s.slice(12,16)!=='IHDR'||d.getUint32(16)!==320||d.getUint32(20)!==240||b[24]!==8||b[25]!== (alpha?6:2)||b[26]!==0||b[27]!==0||b[28]!==0)return false;
  let offset=8;for(const kind of ['IHDR','IDAT','IEND']){if(offset+12>b.length)return false;const length=d.getUint32(offset);if(offset+12+length>b.length||s.slice(offset+4,offset+8)!==kind||kind==='IDAT'&&!length||kind==='IEND'&&length!==0)return false;let crc=0xffffffff;for(let i=offset+4;i<offset+8+length;i++)crc=crcTable[(crc^b[i])&255]^(crc>>>8);if(((crc^0xffffffff)>>>0)!==d.getUint32(offset+8+length))return false;offset+=12+length;}return offset===b.length;
 }catch{return false;}
}
export function validateRGBDImage(value:unknown,directory:RGBDDirectory,index:number):RGBDImage{
 const v=value as RGBDImage;binding(v,{space:directory.space_id,input:directory.input_id,snapshot:directory.snapshot_sha256,tracking:directory.tracking_sha256});
 if(!integer(index)||!directory.frames[index]||!validRGBDFrame(v.frame)||JSON.stringify(v.frame)!==JSON.stringify(directory.frames[index])||v.kind!=='frame'||JSON.stringify(v.source_size)!=='[640,480]'||JSON.stringify(v.display_size)!=='[320,240]'||v.display_rule!=='nyu-depth-metres-nearest-rgba/0.1'||JSON.stringify(v.depth_range_m)!=='[0,10]'||v.invalid_depth!=='transparent'||!integer(v.valid_depth_pixels)||v.valid_depth_pixels>307200||v.payload_checked!=='selected_pair_only'||!png(v.rgb_png,false)||!png(v.depth_png,true)||new TextEncoder().encode(JSON.stringify(v)).length>2*1024*1024)fail();
 return v;
}
export function processSourceFrame(directory:RGBDDirectory,process:ProcessFrame):number{
 const f=directory.frames[process.index];
 if(!f||f.source_time_us!==process.source_time_us||f.relative_time_us!==process.relative_time_us||f.depth_sha256!==process.depth_sha256||f.rgb_sha256!==process.rgb_sha256||JSON.stringify(f.pose)!==JSON.stringify(process.pose))fail();
 return f.index;
}
export function supportsRGBD(value:unknown){
 const p=(value as {rgbd_input_preview?:{profile:string;formats:string[];max_frames:number;max_index_bytes:number;max_response_bytes:number;display_size:number[]}})?.rgbd_input_preview;
 return !!p&&p.profile===RGBD_PROFILE&&p.formats?.includes('nyu_rgbd_with_existing_poses')&&p.max_frames===500&&p.max_index_bytes===1024*1024&&p.max_response_bytes===2*1024*1024&&JSON.stringify(p.display_size)==='[320,240]';
}
