import type {PreviewGeometry,XYZ} from './geometry-preview-data';
export type ProcessFrame={index:number;relative_time_us:number;source_time_us:number;pose:number[][];input_points:number;added_points:number;point_count:number;processed_at:string;depth_sha256:string;rgb_sha256:string;message_sha256?:string;header_ns?:string;recorded_ns?:string;registration?:{accepted:boolean;T_previous_current?:number[][]}};
export type ProcessData=PreviewGeometry&{profile:string;supported:true;ready:true;space_id:string;job_id:string;input_id:string;revision:number;state:string;job_state:string;snapshot_sha256:string;tracking_sha256:string;bag_sha256?:string;source_model_sha256:string|null;input_frames:number;available_frames:number;processed_frames:number;excluded_frames:number;source_clock:string;updated_at:string;frames:ProcessFrame[];first_seen_frames:number[];quality:string;robot_ready:boolean};
type Availability={supported:boolean;ready:false;space_id:string;job_id:string;input_id:string};
const integer=(n:unknown):n is number=>Number.isSafeInteger(n)&&Number(n)>=0;
const sha=(s:unknown)=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
const xyz=(p:unknown):p is XYZ=>Array.isArray(p)&&p.length===3&&p.every(v=>typeof v==='number'&&Number.isFinite(v));
export function rigidPose(m:unknown):m is number[][]{
 if(!Array.isArray(m)||m.length!==4||!m.every(r=>Array.isArray(r)&&r.length===4&&r.every(n=>typeof n==='number'&&Number.isFinite(n))))return false;
 if(m[3].some((n:number,i:number)=>Math.abs(n-(i===3?1:0))>1e-8))return false;
 for(let i=0;i<3;i++)for(let j=0;j<3;j++)if(Math.abs(m[0][i]*m[0][j]+m[1][i]*m[1][j]+m[2][i]*m[2][j]-(i===j?1:0))>1e-4)return false;
 const d=m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])-m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])+m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]);return Math.abs(d-1)<1e-4;
}
export function validateProcess(value:unknown,expected:{space:string;input:string;job:string;snapshot:string;tracking?:string;bag?:string;model?:string}):ProcessData|Availability{
 const v=value as ProcessData;
 if(!v||!['cospace.build-process/0.1','cospace.lidar-build-process/0.1'].includes(v.profile)||v.space_id!==expected.space||v.job_id!==expected.job||v.input_id!==expected.input||typeof v.supported!=='boolean')throw Error('构建过程与当前任务不一致。');
 if(!v.supported)return {supported:false,ready:false,space_id:v.space_id,job_id:v.job_id,input_id:v.input_id};
 if((value as {ready?:boolean}).ready===false)return {supported:true,ready:false,space_id:v.space_id,job_id:v.job_id,input_id:v.input_id};
 const lidar=v.profile==='cospace.lidar-build-process/0.1';
 const originValid=lidar?v.bag_sha256===expected.bag&&sha(v.bag_sha256)&&expected.tracking===undefined&&v.tracking_sha256===undefined&&v.frame_id==='first_lidar_anchor'&&JSON.stringify(v.axes)==='["sensor_x","sensor_y","sensor_z"]'&&v.source_clock==='ros_header_unverified_utc':v.tracking_sha256===expected.tracking&&sha(v.tracking_sha256)&&v.frame_id==='first_depth_camera_anchor'&&JSON.stringify(v.axes)==='["right","down","forward"]'&&v.source_clock==='filename_time_unverified_utc';
 if(v.ready!==true||v.snapshot_sha256!==expected.snapshot||!sha(v.snapshot_sha256)||!originValid||expected.model&&v.source_model_sha256!==expected.model||v.source_model_sha256!==null&&!sha(v.source_model_sha256)||v.quality!=='unverified'||v.robot_ready!==false||v.unit!=='m')throw Error('构建过程来源校验未通过。');
 if(lidar&&(v.input_frames<2||v.input_frames>20))throw Error('激光构建帧范围无效。');
 if(!integer(v.revision)||!integer(v.input_frames)||v.input_frames>500||!integer(v.available_frames)||v.available_frames<1||v.available_frames>v.input_frames||!integer(v.processed_frames)||v.processed_frames>v.available_frames||v.excluded_frames!==v.input_frames-v.available_frames||!Array.isArray(v.frames)||v.frames.length!==v.processed_frames||!['recording','completed','failed','interrupted'].includes(v.state)||v.state==='completed'&&v.processed_frames!==v.available_frames)throw Error('构建帧范围无效。');
 let total=0;
 for(let i=0;i<v.frames.length;i++){
  const f=v.frames[i];total+=f.added_points;
  const sourceValid=lidar?sha(f.message_sha256)&&typeof f.header_ns==='string'&&/^[0-9]{1,19}$/.test(f.header_ns)&&BigInt(f.header_ns)/1000n===BigInt(f.source_time_us)&&typeof f.recorded_ns==='string'&&/^[0-9]{1,19}$/.test(f.recorded_ns)&&f.registration?.accepted===true&&(i===0||rigidPose(f.registration.T_previous_current)):sha(f.depth_sha256)&&sha(f.rgb_sha256);
  if(f.index!==i||!integer(f.relative_time_us)||!integer(f.source_time_us)||f.relative_time_us!==f.source_time_us-v.frames[0].source_time_us||i>0&&f.relative_time_us<=v.frames[i-1].relative_time_us||!rigidPose(f.pose)||!integer(f.added_points)||!integer(f.input_points)||f.input_points<f.added_points||f.point_count!==total||!sourceValid||!Number.isFinite(Date.parse(f.processed_at)))throw Error('构建帧记录无效。');
 }
 const s=v.sampling;
 if(v.point_count!==total||!integer(total)||total>2500000||!Array.isArray(v.bounds)||v.bounds.length!==2||!v.bounds.every(xyz)||v.bounds[0].some((n,i)=>n>v.bounds[1][i])||!s||s.limit!==10000||s.method!=='file_index_stride'||s.stride!==Math.max(1,Math.ceil(total/10000))||s.count!==Math.ceil(total/s.stride)||!Array.isArray(v.points)||v.points.length!==s.count||!Array.isArray(v.colors)||v.colors.length!==s.count||!Array.isArray(v.first_seen_frames)||v.first_seen_frames.length!==s.count||!v.points.every(p=>xyz(p)&&p.every((n,i)=>n>=v.bounds[0][i]&&n<=v.bounds[1][i]))||!v.colors.every(p=>xyz(p)&&p.every(n=>integer(n)&&n<=255))||!v.first_seen_frames.every((f,i)=>integer(f)&&f<v.processed_frames&&(i===0||f>=v.first_seen_frames[i-1])))throw Error('构建过程几何或显示预算无效。');
 for(let i=0;i<v.first_seen_frames.length;i++){const f=v.first_seen_frames[i],index=i*s.stride,previous=f?v.frames[f-1].point_count:0;if(index<previous||index>=v.frames[f].point_count)throw Error('显示点与首次观测帧不一致。');}
 return v;
}
export function visibleCount(data:ProcessData,frame:number){let lo=0,hi=data.first_seen_frames.length;while(lo<hi){const mid=(lo+hi)>>>1;if(data.first_seen_frames[mid]<=frame)lo=mid+1;else hi=mid;}return lo;}
export function frameAt(data:ProcessData,timeUs:number){let index=0;for(let i=0;i<data.frames.length;i++){if(data.frames[i].relative_time_us>timeUs)break;index=i;}return index;}
export type ProcessPlayback={frame:number;data:ProcessData};
