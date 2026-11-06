"""Human-readable, read-only diagnostics for a registered local preview input."""
from datetime import datetime, timezone
from packages.lifecycle.preview_scope import owned


REASONS = {
    'source_mismatch': ('轨迹与资料不匹配', '使用从该封存报告生成的轨迹，重新登记后再试。'),
    'registered_input_changed': ('登记后资料发生变化', '恢复封存文件，或将变更后的资料重新登记为新输入。'),
    'input_integrity': ('图像完整性核对失败', '恢复缺失或改动的图像，并保持报告中的摘要与字节数一致。'),
    'unsupported_input_format': ('资料格式尚不支持', '选择NYU封存RGB-D与已有轨迹、ROS1激光样本，或带坐标声明的PLY点云。'),
    'lidar_bag_integrity': ('激光样本摘要不一致', '恢复封存sample.bag，或将新样本作为新资料登记。'),
    'lidar_message_evidence_mismatch': ('激光消息与抽取记录不一致', '核对样本清单、逐消息摘要和时间，不改写旧登记记录。'),
    'lidar_structural_precheck_failed': ('激光样本结构预检未通过', '使用独立ROS1预检查看消息布局、时间及预算拒绝原因。'),
    'invalid_input_poses': ('位姿数量或矩阵不符合要求', '检查轨迹帧数、有限数值、4×4形状及齐次矩阵末行。'),
    'invalid_input_member': ('图像成员路径无效', '使用raw目录内的PGM/PPM文件名，不得引用目录外文件。'),
    'input_member_too_large': ('图像超出当前适配器限制', '检查图像格式，当前每个图像文件须不超过2MB。'),
}


def preflight(catalog, identity):
    # A missing registration is an API lookup error, not a failed file check.
    record = catalog.read(identity)
    issue = None
    try:
        catalog.resolve(identity)
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        code = str(exc)
        if isinstance(exc, FileNotFoundError):
            code = 'input_file_missing'
            title, action = '资料文件缺失', '恢复已登记的封存目录或轨迹文件后重新预检。'
        elif isinstance(exc, OSError):
            code = 'input_file_unreadable'
            title, action = '资料文件无法读取', '检查本机文件权限或文件是否被占用。'
        elif code.startswith('pointcloud_'):
            title, action = '点云或坐标声明不符合要求', '核对pointcloud.json的米制局部坐标声明、摘要与cloud.ply；使用受支持的二进制XYZ或XYZRGB布局。'
        elif code in REASONS:
            title, action = REASONS[code]
        else:
            code = 'invalid_input_content'
            title, action = '资料内容或图像格式无效', '检查报告字段、轨迹JSON和640×480的PGM/PPM图像，再重新预检。'
        issue = {'code': code, 'title': title, 'action': action}
    mapping=record['format']=='ros1_lidar_multiframe_icp'
    lidar=record['format'] in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp')
    pointcloud=record['format']=='ply_pointcloud'
    return {'profile': 'cospace.preview-input-preflight/0.1', 'input_id': record['id'],
            **owned(record),
            'snapshot_sha256': record['snapshot_sha256'], **({'cloud_sha256':record['cloud_sha256']} if pointcloud else {k:record[k] for k in ('bag_sha256','selected_frame')} if lidar else {'tracking_sha256':record['tracking_sha256']}),
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'status': 'failed' if issue else 'passed', 'issue': issue,
            'checks_scope': ['点云文件摘要与字节数','二进制XYZ/XYZRGB布局、有限坐标与数量预算','显式米制局部坐标；不执行场景配准'] if pointcloud else ['样本清单与bag摘要绑定','逐消息摘要、话题、时间和结构预算','多帧有效点、递增源时间和一致坐标系；配准在构建时执行' if mapping else '首帧有效点及局部坐标声明；不执行位姿配准'] if lidar else ['报告与轨迹摘要绑定', '位姿结构与数量', '接受帧的图像格式、尺寸、摘要及字节数'],
            'counts': {k: record[k] for k in (('point_count','cloud_bytes') if pointcloud else ('input_frames','used_frames','verified_messages','valid_points') if lidar else ('input_frames', 'used_frames', 'verified_image_members'))},
            'counts_basis': 'registration', 'quality': 'unverified', 'robot_ready': False,
            'notice': '仅为本次文件核对；构建提交时重新校验，不代表精度或可通行性验收。'}
