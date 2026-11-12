export type OverviewJob={id:string;space_id:string;created_at:string;state:string;display_code?:string;build_code?:string;input_id?:string;input_binding?:{label?:string;format?:string};mode?:string;pipeline?:string;view_parent_id?:string};
export type OverviewStages={space_id:string;job_id:string;legacy?:boolean;views:Record<string,{state:string}>};
export function sceneBuildMode(job:OverviewJob){
 if(job.view_parent_id)return '沿用基准模型 · 视图派生';
 const format=job.input_binding?.format;
 const modes:Record<string,string>={ply_pointcloud:'已有点云 · 整理与表达派生',nyu_rgbd_with_existing_poses:'RGB-D＋已有轨迹',ros1_lidar_single_frame:'激光单帧 · 局部候选',ros1_lidar_multiframe_icp:'激光多帧 · 局部建图'};
 if(format&&modes[format])return modes[format];
 const legacy:Record<string,string>={candidate_from_frozen_rgbd_and_existing_poses:'RGB-D＋已有轨迹',candidate_from_existing_pointcloud:'已有点云 · 整理与表达派生'};
 return legacy[job.mode||'']||'构建模式未记录';
}
export function sceneViewSummary(stages:OverviewStages|null,kind:string){
 if(!stages)return '派生记录暂不可读';
 const state=stages.views[kind]?.state;
 const labels:Record<string,string>={queued:'排队中',running:'派生中',succeeded:'已派生',failed:'派生失败',interrupted:'派生中断'};
 return labels[state||'']||(stages.legacy?'历史构建未记录独立派生状态':'尚未派生');
}
