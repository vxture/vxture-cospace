"""Bounded ROS1 specimen -> first sensor-local cloud; no poses or registration."""
import hashlib
import json
from pathlib import Path
import numpy as np

FORMAT='ros1_lidar_single_frame'
MULTIFRAME_FORMAT='ros1_lidar_multiframe_icp'


def read_specimen(root, *, sequence=False):
    # Optional input dependencies are loaded only for this adapter.
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores,get_typestore
    from packages.data.bag_preflight import inspect_bag,MAX_FILE_BYTES
    root=Path(root).resolve();manifest=root/'sample.json'
    if manifest.stat().st_size>256_000:raise ValueError('lidar_manifest_budget')
    raw=manifest.read_bytes();doc=json.loads(raw)
    if doc.get('profile')!='cospace.external-lidar-specimen/0.1':raise ValueError('unsupported_input_format')
    bag=root/'sample.bag'
    if not bag.resolve().is_relative_to(root) or bag.stat().st_size>MAX_FILE_BYTES:raise ValueError('lidar_bag_budget_or_path')
    binding=doc['artifacts']['sample.bag'];payload=bag.read_bytes()
    sha=hashlib.sha256(payload).hexdigest()
    if binding!={'bytes':len(payload),'sha256':sha}:raise ValueError('lidar_bag_integrity')
    first=doc['first_frame']['from_message'];topic=first['topic']
    candidates=[name for name in doc['topics'] if name.endswith('/imu')]
    if len(candidates)!=1:raise ValueError('lidar_imu_topic_ambiguous')
    check=inspect_bag(bag,topic,candidates[0],sha)
    if not check['structural_precheck_passed']:raise ValueError('lidar_structural_precheck_failed')
    # Capture exact bytes so a later change to the path cannot affect this read.
    import tempfile
    records=[];cloud=None;count=0;clouds=[]
    store=get_typestore(Stores.ROS1_NOETIC)
    with tempfile.TemporaryDirectory(prefix='cospace-lidar-') as temporary:
        fixed=Path(temporary)/'input.bag';fixed.write_bytes(payload)
        with Reader(fixed) as reader:
            for connection,timestamp,message in reader.messages():
                item={'topic':connection.topic,'recorded_ns':timestamp,'serialized_bytes':len(message),
                      'sha256':hashlib.sha256(message).hexdigest()}
                # All supported specimen messages use standard ROS1 definitions.
                expected=store.generate_msgdef(connection.msgtype)[1]
                if connection.digest!=expected:raise ValueError('lidar_message_definition')
                decoded=store.deserialize_ros1(message,connection.msgtype)
                if hasattr(decoded,'header'):
                    item.update(frame_id=decoded.header.frame_id,header_ns=int(decoded.header.stamp.sec)*10**9+int(decoded.header.stamp.nanosec))
                records.append(item)
                if connection.topic==topic:
                    count+=1
                    if cloud is None:cloud=decoded
                    if sequence:
                        if len(clouds)>=20:raise ValueError('lidar_sequence_frame_budget')
                        clouds.append((item,decoded))
    if records!=doc['messages']:raise ValueError('lidar_message_evidence_mismatch')
    if cloud is None or next(r for r in records if r['topic']==topic)!=first:raise ValueError('lidar_first_frame_mismatch')
    window=doc['recorded_window']
    if not window['start_ns']<window['end_exclusive_ns'] or any(not window['start_ns']<=r['recorded_ns']<window['end_exclusive_ns'] for r in records):
        raise ValueError('lidar_window_mismatch')
    from collections import Counter
    if dict(Counter(r['topic'] for r in records))!=doc['topics']:raise ValueError('lidar_topic_counts_mismatch')
    if doc['first_frame']['frame_id']!=cloud.header.frame_id or doc['first_frame']['unit']!='m':raise ValueError('lidar_coordinate_declaration')
    points,intensity=cloud_arrays(cloud)
    if len(points)!=doc['first_frame']['valid_points']:raise ValueError('lidar_valid_points_mismatch')
    summary={'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'bag_sha256':sha,'bag_bytes':len(payload),
             'input_frames':count,'used_frames':1,'verified_messages':len(records),
             'selected_frame':first,'frame_id':cloud.header.frame_id,'unit':'m','valid_points':len(points)}
    if not sequence:return summary,points,intensity
    if not 2<=len(clouds)<=20:raise ValueError('lidar_sequence_requires_multiple_frames')
    frames=[]
    for evidence,message in clouds:
        if evidence['frame_id']!=summary['frame_id']:raise ValueError('lidar_sequence_frame_changed')
        if frames and (evidence['header_ns']<=frames[-1]['evidence']['header_ns'] or
                       evidence['recorded_ns']<=frames[-1]['evidence']['recorded_ns']):
            raise ValueError('lidar_sequence_time_order')
        p,intensity=cloud_arrays(message)
        frames.append({'evidence':evidence,'points':p,'intensity':intensity})
    summary.update(used_frames=0,sequence_frames=[f['evidence'] for f in frames],
                   source_clock='ros_header_unverified_utc')
    return summary,frames


def cloud_arrays(cloud):
    fields={f.name:f for f in cloud.fields};endian='>' if cloud.is_bigendian else '<'
    def array(name):
        f=fields[name];types={2:'u1',4:'u2',6:'u4',7:'f4',8:'f8'}
        if f.count!=1 or f.datatype not in types:raise ValueError('lidar_field_type')
        return np.ndarray((cloud.height,cloud.width),dtype=endian+types[f.datatype],buffer=cloud.data,
                          offset=f.offset,strides=(cloud.row_step,cloud.point_step)).reshape(-1)
    points=np.column_stack([array(n) for n in ('x','y','z')])
    if 'range' not in fields or 'intensity' not in fields:raise ValueError('lidar_range_intensity_required')
    intensity=array('intensity');valid=np.isfinite(points).all(axis=1)&(np.linalg.norm(points,axis=1)>1e-6)&(array('range')>0)
    points=points[valid].astype(np.float32);intensity=intensity[valid].astype(np.float32)
    if not len(points) or not np.isfinite(intensity).all():
        raise ValueError('lidar_valid_points_mismatch')
    return points,intensity
