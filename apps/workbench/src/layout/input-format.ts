export type InputCounts={format?:string;input_frames:number;used_frames:number;point_count?:number;verified_image_members?:number;verified_messages?:number};
export function inputCounts(value:InputCounts){
 return value.format==='ply_pointcloud'?`${(value.point_count??0).toLocaleString('zh-CN')} 点 · 显式米制坐标 · 场景对齐未核验`:value.format==='ros1_lidar_multiframe_icp'?`${value.input_frames} 帧点云 · 构建时估计轨迹 · ${value.verified_messages??0} 条已核对消息`:value.format==='ros1_lidar_single_frame'
  ? `${value.input_frames} 帧点云 · 选取首帧 · ${value.verified_messages??0} 条已核对消息 · 未配准`
  : `${value.input_frames} 帧 · ${value.used_frames} 帧位姿 · ${value.verified_image_members??0} 个图像成员`;
}
export function inputFormat(format:string){
 return format==='ply_pointcloud'?'PLY已有点云 · 显式坐标':format==='ros1_lidar_multiframe_icp'?'ROS1激光 · 多帧局部建图':format==='ros1_lidar_single_frame'?'ROS1激光 · 单帧局部候选':format==='nyu_rgbd_with_existing_poses'?'NYU RGB-D＋已有轨迹':format;
}

export function inputDisplayName(value:{label:string;presentation?:{display_name:string}}){return value.presentation?.display_name||value.label;}

export type InputRoute={format:string;category:string;category_label:string;label:string;requires:string[];result:string};
const routeDescriptions:Record<string,Omit<InputRoute,'format'>>={
 nyu_rgbd_with_existing_poses:{category:'acquisition',category_label:'原始采集资料',label:'RGB-D＋已有轨迹',requires:['封存图像清单','匹配的已有轨迹'],result:'按已有位姿累积固定模型，再派生双视图；不生成新轨迹。'},
 ros1_lidar_single_frame:{category:'acquisition',category_label:'原始采集资料',label:'ROS1 激光短样本',requires:['受支持的样本清单','封存日志与首帧声明'],result:'取首帧生成局部模型，再派生双视图；不执行配准或 SLAM。'},
 ros1_lidar_multiframe_icp:{category:'acquisition',category_label:'原始采集资料',label:'ROS1 激光多帧建图',requires:['2～20帧封存激光样本','递增消息时间与一致坐标系'],result:'纯激光逐帧配准，生成局部模型和估计轨迹后派生双视图；不使用IMU或参考位姿。'},
 ply_pointcloud:{category:'existing_product',category_label:'已有空间成果',label:'PLY＋坐标声明',requires:['受支持的 XYZ／XYZRGB 点云','米制局部坐标及来源清单'],result:'保留声明坐标形成固定模型，再派生双视图；不自动对齐场景。'}
};
// Compatibility descriptions only: callers must first obtain a declared server format.
export function inputRoute(format:string):InputRoute|null{return routeDescriptions[format]?{format,...routeDescriptions[format]}:null;}
export type UploadCapabilities={profile:string;formats:string[];routes?:InputRoute[];max_upload_bytes:number;max_expanded_bytes:number;input_preview?:{profile:string;formats:string[];max_points:number};pointcloud_preparation?:{profile:string;format:string;source_profile:string;max_cloud_bytes:number;max_points:number}};
export function canPreparePointcloud(value:UploadCapabilities|null){const p=value?.pointcloud_preparation;return !!value?.formats.includes('ply_pointcloud')&&p?.profile==='cospace.pointcloud-preparation/0.1'&&p.format==='ply_pointcloud'&&p.source_profile==='cospace.pointcloud-source/0.1'&&p.max_cloud_bytes===32*1024*1024&&p.max_points===1_000_000;}
export function validRoute(value:unknown):value is InputRoute{
 const r=value as InputRoute|undefined;
 return !!r&&typeof r.format==='string'&&typeof r.category==='string'&&typeof r.category_label==='string'&&typeof r.label==='string'&&typeof r.result==='string'&&Array.isArray(r.requires)&&r.requires.every(v=>typeof v==='string');
}
export function uploadRoutes(value:UploadCapabilities){return value.formats.flatMap(format=>{const known=inputRoute(format);return known?[(Array.isArray(value.routes)?value.routes:[]).find(r=>validRoute(r)&&r.format===format)||known]:[];});}
export async function readUploadCapabilities(endpoint:string,space:string,signal?:AbortSignal):Promise<UploadCapabilities>{
 const r=await fetch(`${endpoint}/api/input-uploads?${new URLSearchParams({space_id:space})}`,{signal,cache:'no-store'});
 if(!r.ok)throw Error('上传能力暂不可用，可重试或使用已配置来源。');
 const body=await r.json();
 if(body.profile!=='cospace.input-upload/0.1'||!Array.isArray(body.formats)||!body.formats.every((f:unknown)=>typeof f==='string')||!Number.isSafeInteger(body.max_upload_bytes)||body.max_upload_bytes<=0||!Number.isSafeInteger(body.max_expanded_bytes)||body.max_expanded_bytes<=0)throw Error('上传能力响应无法识别，请刷新重试。');
 return body;
}
