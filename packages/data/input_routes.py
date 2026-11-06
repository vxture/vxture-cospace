"""Descriptions of the three implemented input adapters, not an algorithm registry."""
from copy import deepcopy

ROUTES = {
    'nyu_rgbd_with_existing_poses': {
        'category':'acquisition','category_label':'原始采集资料','label':'RGB-D＋已有轨迹',
        'requires':['封存图像清单','匹配的已有轨迹'],
        'result':'按已有位姿累积固定模型，再派生双视图；不生成新轨迹。'},
    'ros1_lidar_single_frame': {
        'category':'acquisition','category_label':'原始采集资料','label':'ROS1 激光短样本',
        'requires':['受支持的样本清单','封存日志与首帧声明'],
        'result':'取首帧生成局部模型，再派生双视图；不执行配准或 SLAM。'},
    'ros1_lidar_multiframe_icp': {
        'category':'acquisition','category_label':'原始采集资料','label':'ROS1 激光多帧建图',
        'requires':['2～20帧受支持的封存激光样本','严格递增的激光消息时间与一致坐标系'],
        'result':'纯激光逐帧配准并生成局部模型和估计轨迹，再派生双视图；不使用IMU或参考位姿。'},
    'ply_pointcloud': {
        'category':'existing_product','category_label':'已有空间成果','label':'PLY＋坐标声明',
        'requires':['受支持的 XYZ／XYZRGB 点云','米制局部坐标及来源清单'],
        'result':'保留声明坐标形成固定模型，再派生双视图；不自动对齐场景。'},
}


def route(format):
    value=ROUTES.get(format)
    return {'format':format,**deepcopy(value)} if value else None


def routes(formats):
    return [route(format) for format in formats if format in ROUTES]
