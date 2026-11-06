"""Offline ROS1 bag structural inspection; no ROS runtime or algorithm admission."""
import hashlib
import struct
import tempfile
from pathlib import Path

from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore

import math

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_MESSAGES = 20000
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_POINTS = 100000
TYPES = {'lidar':'sensor_msgs/msg/PointCloud2', 'imu':'sensor_msgs/msg/Imu'}
FORMATS = {1:'b', 2:'B', 3:'h', 4:'H', 5:'i', 6:'I', 7:'f', 8:'d'}


def cloud_values(message):
    """Check layout and every XYZ/time value, without assigning time semantics."""
    if not message.width or not message.height or message.width * message.height > MAX_POINTS:
        raise ValueError('cloud_point_budget_or_empty')
    if (not message.point_step or message.row_step < message.width * message.point_step
            or len(message.data) != message.height * message.row_step):
        raise ValueError('cloud_layout')
    fields = {}
    occupied = set()
    for field in message.fields:
        if field.name in fields or not field.name or field.datatype not in FORMATS or not field.count:
            raise ValueError('cloud_field_definition')
        fmt = FORMATS[field.datatype]
        end = field.offset + struct.calcsize(fmt) * field.count
        if end > message.point_step or occupied.intersection(range(field.offset,end)):
            raise ValueError('cloud_field_layout')
        occupied.update(range(field.offset,end))
        fields[field.name] = field
    if not {'x','y','z'}.issubset(fields):
        raise ValueError('missing_xyz')
    time_fields = set(fields).intersection(('time','t','timestamp'))
    if len(time_fields) != 1:
        raise ValueError('missing_or_ambiguous_point_time')
    selected = ['x','y','z',next(iter(time_fields))]
    for name in selected:
        if fields[name].count != 1 or (name in ('x','y','z') and fields[name].datatype not in (7,8)):
            raise ValueError('cloud_required_field_type')
    endian = '>' if message.is_bigendian else '<'
    raw = memoryview(message.data)
    for row in range(message.height):
        for col in range(message.width):
            offset = row * message.row_step + col * message.point_step
            for name in selected:
                field = fields[name]
                value = struct.unpack_from(endian+FORMATS[field.datatype],raw,offset+field.offset)[0]
                if not math.isfinite(value):
                    raise ValueError('non_finite_point_value')
    return tuple((f.name,f.offset,f.datatype,f.count) for f in message.fields)


def inspect_bag(path, lidar_topic='/points_raw', imu_topic='/imu', expected_sha256=None):
    """Inspect one bounded captured byte snapshot. External source identity is optional."""
    if not lidar_topic or not imu_topic or lidar_topic == imu_topic:
        raise ValueError('distinct_topics_required')
    report = {'schema_version':'cospace.bag-preflight/0.1','format':'ros1_bag_v2',
              'input':{'bytes':None,'sha256':None,'expected_digest_verified':False},
              'streams':{},'header_time_overlap_ns':None,'errors':[],
              'structural_precheck_passed':False,'algorithm_ready':False,'real_release_ready':False,
              'unverified':['data_provenance_and_role','point_time_unit_and_reference',
                            'clock_sync','extrinsics','imu_convention_and_attitude','independent_quality'],
              'limits':{'file_bytes':MAX_FILE_BYTES,'messages':MAX_MESSAGES,
                        'message_bytes':MAX_MESSAGE_BYTES,'points_per_cloud':MAX_POINTS}}
    errors = set()
    def fail(code,topic=None):
        errors.add((topic or '',code))
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_FILE_BYTES+1)
    except OSError:
        fail('input_unreadable')
        raw = None
    if raw is not None:
        report['input'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if len(raw)>MAX_FILE_BYTES:
            # The bounded prefix is not the original file's length or digest.
            report['input'].update(bytes=None,sha256=None)
            fail('file_budget')
        elif expected_sha256 is not None and report['input']['sha256'] != expected_sha256:
            fail('input_digest_mismatch')
        else:
            report['input']['expected_digest_verified'] = expected_sha256 is not None
            store = get_typestore(Stores.ROS1_NOETIC)
            try:
                # Reader works against a captured temporary copy, never a mutable source path.
                with tempfile.TemporaryDirectory(prefix='cospace-bag-') as directory:
                    snapshot = Path(directory)/'snapshot.bag'
                    snapshot.write_bytes(raw)
                    with Reader(snapshot) as reader:
                        topics = {lidar_topic:'lidar',imu_topic:'imu'}
                        connections = [c for c in reader.connections if c.topic in topics]
                        for topic,role in topics.items():
                            selected = [c for c in connections if c.topic==topic]
                            if not selected:
                                fail('missing_topic',topic)
                            expected_md5 = store.generate_msgdef(TYPES[role])[1]
                            for connection in selected:
                                if connection.msgtype != TYPES[role] or connection.digest != expected_md5:
                                    fail('unsupported_message_definition',topic)
                        if errors:
                            connections = []
                        layouts = {}
                        previous = {}
                        count = 0
                        for connection,recorded,payload in reader.messages(connections=connections) if connections else ():
                            count += 1
                            if count > MAX_MESSAGES:
                                fail('message_count_budget'); break
                            if len(payload)>MAX_MESSAGE_BYTES:
                                fail('message_bytes_budget'); break
                            topic = connection.topic
                            state = report['streams'].setdefault(topic,{
                                'role':topics[topic],'type':connection.msgtype,'count':0,'points':0,
                                'frame_ids':[],'fields':[],'header_start_ns':None,'header_end_ns':None,
                                'backward_steps':0,'duplicate_steps':0})
                            state['count'] += 1
                            message = store.deserialize_ros1(payload,connection.msgtype)
                            stamp = message.header.stamp
                            at = stamp.sec*1000000000+stamp.nanosec
                            if stamp.sec < 0 or not 0 <= stamp.nanosec < 1000000000 or at <= 0:
                                fail('invalid_header_time',topic)
                            else:
                                if topic in previous:
                                    state['backward_steps'] += int(at<previous[topic])
                                    state['duplicate_steps'] += int(at==previous[topic])
                                previous[topic] = at
                                state['header_start_ns'] = min(at,state['header_start_ns'] if state['header_start_ns'] is not None else at)
                                state['header_end_ns'] = max(at,state['header_end_ns'] if state['header_end_ns'] is not None else at)
                            frame = message.header.frame_id
                            if frame not in state['frame_ids']: state['frame_ids'].append(frame)
                            if not frame.strip(): fail('empty_frame',topic)
                            if topics[topic]=='lidar':
                                try:
                                    layout = cloud_values(message)
                                    if topic in layouts and layouts[topic] != layout:
                                        fail('changing_cloud_layout',topic)
                                    layouts[topic] = layout
                                    state['fields'] = [dict(zip(('name','offset','datatype','count'),f)) for f in layout]
                                    state['points'] += message.width*message.height
                                except ValueError as error:
                                    fail(str(error),topic)
                            else:
                                values = [getattr(vector,axis) for vector in
                                          (message.angular_velocity,message.linear_acceleration) for axis in ('x','y','z')]
                                if not all(map(math.isfinite,values)): fail('non_finite_imu',topic)
                        for topic in topics:
                            state = report['streams'].get(topic)
                            if state is None or state['count']<2: fail('insufficient_messages',topic)
                            if state:
                                if state['backward_steps'] or state['duplicate_steps']: fail('non_increasing_header_time',topic)
                                if len(state['frame_ids'])>1: fail('changing_frame',topic)
                        left,right = (report['streams'].get(t) for t in (lidar_topic,imu_topic))
                        if left and right and all(s['header_start_ns'] is not None for s in (left,right)):
                            overlap = max(0,min(left['header_end_ns'],right['header_end_ns'])-max(left['header_start_ns'],right['header_start_ns']))
                            report['header_time_overlap_ns'] = overlap
                            if overlap<=0: fail('no_positive_header_overlap')
            except Exception:
                # Corrupt/unsupported bag bytes must never become an empty successful report.
                fail('bag_decode_failed')
    report['errors'] = [{'topic':topic or None,'code':code} for topic,code in sorted(errors)]
    report['structural_precheck_passed'] = not errors
    return report
