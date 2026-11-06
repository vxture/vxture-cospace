import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

pytest.importorskip('rosbags',reason='optional input extra is required for offline bag checks')
import numpy as np
from experiments.scripts.bag_fixture import create_bag
from packages.data.bag_preflight import inspect_bag


def errors(report):
    return {item['code'] for item in report['errors']}


def test_actual_bag_bytes_and_no_algorithm_admission(tmp_path):
    path=tmp_path/'input.bag'; create_bag(path)
    raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
    report=inspect_bag(path,expected_sha256=sha)
    assert report['structural_precheck_passed'],report['errors']
    assert report['input']=={'bytes':len(raw),'sha256':sha,'expected_digest_verified':True}
    assert report['streams']['/imu']['count']==21
    assert report['streams']['/points_raw']['points']==6
    assert report['header_time_overlap_ns']==200000000
    assert not report['algorithm_ready'] and not report['real_release_ready']
    assert path.read_bytes()==raw


def test_report_schema_for_success_and_failures(tmp_path):
    schema=json.loads(Path('contracts/schemas/bag-preflight-v0.1.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema)
    for case in ('valid','missing_point_time','backward_imu','missing_imu'):
        path=tmp_path/(case+'.bag'); create_bag(path,case)
        validator.validate(inspect_bag(path))
    validator.validate(inspect_bag(tmp_path/'absent.bag'))


@pytest.mark.parametrize('case,code',[
    ('missing_point_time','missing_or_ambiguous_point_time'),
    ('backward_imu','non_increasing_header_time'),('missing_imu','insufficient_messages')])
def test_primary_smoke_failures(tmp_path,case,code):
    path=tmp_path/'input.bag'; create_bag(path,case)
    report=inspect_bag(path)
    assert not report['structural_precheck_passed'] and code in errors(report)


@pytest.mark.parametrize('case,code',[
    ('xyz_nan','non_finite_point_value'),('time_nan','non_finite_point_value'),
    ('imu_nan','non_finite_imu'),('empty_frame','empty_frame'),
    ('changing_frame','changing_frame'),('empty_cloud','cloud_point_budget_or_empty'),
    ('row_truncated','cloud_layout'),('field_overlap','cloud_field_layout'),
    ('duplicate_field','cloud_field_definition'),('xyz_integer','cloud_required_field_type'),
    ('duplicate_stamp','non_increasing_header_time'),('zero_stamp','invalid_header_time'),
    ('invalid_nanoseconds','invalid_header_time'),('no_overlap','no_positive_header_overlap'),
    ('changing_layout','changing_cloud_layout'),('missing_xyz','missing_xyz'),
    ('field_count','cloud_required_field_type'),('multiple_time','missing_or_ambiguous_point_time')])
def test_message_content_failures(tmp_path,case,code):
    def mutate(role,i,m):
        if role=='imu':
            if case=='imu_nan': m.angular_velocity.x=float('nan')
            if case=='duplicate_stamp' and i==10: m.header.stamp.nanosec=90000000
            if case=='zero_stamp': m.header.stamp.sec=m.header.stamp.nanosec=0
            if case=='invalid_nanoseconds': m.header.stamp.nanosec=1000000000
            if case=='no_overlap': m.header.stamp.sec=200
        if role!='lidar': return
        if case=='xyz_nan': struct.pack_into('<f',m.data,0,float('nan'))
        if case=='time_nan': struct.pack_into('<f',m.data,12,float('nan'))
        if case=='empty_frame': m.header.frame_id=''
        if case=='changing_frame' and i==10: m.header.frame_id='different'
        if case=='empty_cloud': m.width=0
        if case=='row_truncated': m.data=m.data[:-1]
        if case=='field_overlap': m.fields[1].offset=0
        if case=='duplicate_field': m.fields[1].name='x'
        if case=='xyz_integer': m.fields[0].datatype=5
        if case=='changing_layout' and i==10: m.fields[3].name='t'
        if case=='missing_xyz': m.fields[0].name='other'
        if case=='field_count':
            m.fields[0].count=2; m.fields=[m.fields[0],m.fields[2],m.fields[3]]
            m.fields[1].name='y'; m.fields[2].name='z'
            # Add a separate valid time field in the second point stride.
            Field=type(m.fields[0]); m.fields.append(Field('time',16,7,1))
            m.point_step=20; m.row_step=40; m.data=np.zeros(40,dtype=np.uint8)
        if case=='multiple_time':
            m.fields.append(type(m.fields[0])('t',16,7,1))
            m.point_step=20; m.row_step=40; m.data=np.zeros(40,dtype=np.uint8)
    path=tmp_path/'input.bag'; create_bag(path,mutate=mutate)
    report=inspect_bag(path)
    assert not report['structural_precheck_passed'] and code in errors(report),report['errors']


def test_big_endian_and_row_padding(tmp_path):
    def mutate(role,i,m):
        if role!='lidar': return
        m.is_bigendian=True
        m.data=np.frombuffer(struct.pack('>ffffffff',1.,2.,3.,0.,4.,5.,6.,.001)+b'padding!',dtype=np.uint8)
        m.row_step=40
    path=tmp_path/'input.bag'; create_bag(path,mutate=mutate)
    assert inspect_bag(path)['structural_precheck_passed']


@pytest.mark.parametrize('wrong_type',[True,False])
def test_message_type_and_checksum_rejected(tmp_path,wrong_type):
    from rosbags.rosbag1 import Writer
    from rosbags.typesys import Stores, get_typestore
    store=get_typestore(Stores.ROS1_NOETIC)
    path=tmp_path/'input.bag'
    with Writer(path) as writer:
        writer.add_connection('/imu','sensor_msgs/msg/Imu',typestore=store)
        if wrong_type:
            writer.add_connection('/points_raw','sensor_msgs/msg/Imu',typestore=store)
        else:
            definition=store.generate_msgdef('sensor_msgs/msg/PointCloud2')[0]
            writer.add_connection('/points_raw','sensor_msgs/msg/PointCloud2',msgdef=definition,md5sum='0'*32)
    assert 'unsupported_message_definition' in errors(inspect_bag(path))


def test_integer_nanosecond_precision(tmp_path):
    def mutate(role,i,m):
        m.header.stamp.sec=1700000000
        m.header.stamp.nanosec=i
    path=tmp_path/'input.bag'; create_bag(path,mutate=mutate)
    report=inspect_bag(path)
    assert report['structural_precheck_passed']
    assert report['header_time_overlap_ns']==20
    assert report['streams']['/imu']['duplicate_steps']==0


def test_one_cloud_missing_time_cannot_be_hidden_by_other_messages(tmp_path):
    def mutate(role,i,m):
        if role=='lidar' and i==10: m.fields=m.fields[:-1]
    path=tmp_path/'input.bag'; create_bag(path,mutate=mutate)
    assert 'missing_or_ambiguous_point_time' in errors(inspect_bag(path))


@pytest.mark.parametrize('case', ['corrupt','empty','truncated','missing','digest'])
def test_input_failures(tmp_path,case):
    path=tmp_path/'input.bag'
    if case in ('truncated','digest'): create_bag(path)
    if case=='corrupt': path.write_bytes(b'not a bag')
    if case=='empty': path.write_bytes(b'')
    if case=='truncated': path.write_bytes(path.read_bytes()[:150])
    report=inspect_bag(path,expected_sha256='0'*64 if case=='digest' else None)
    assert not report['structural_precheck_passed']
    assert ('input_digest_mismatch' if case=='digest' else 'input_unreadable' if case=='missing' else 'bag_decode_failed') in errors(report)


def test_missing_topics_and_ambiguous_config(tmp_path):
    path=tmp_path/'input.bag'; create_bag(path)
    assert 'missing_topic' in errors(inspect_bag(path,lidar_topic='/absent'))
    with pytest.raises(ValueError,match='distinct_topics'): inspect_bag(path,'/same','/same')


@pytest.mark.parametrize('limit,code',[('MAX_FILE_BYTES','file_budget'),('MAX_MESSAGES','message_count_budget'),
                                     ('MAX_MESSAGE_BYTES','message_bytes_budget'),('MAX_POINTS','cloud_point_budget_or_empty')])
def test_limits(tmp_path,monkeypatch,limit,code):
    path=tmp_path/'input.bag'; create_bag(path)
    monkeypatch.setattr('packages.data.bag_preflight.'+limit,1)
    assert code in errors(inspect_bag(path))


def test_cli_actual_exit_codes_and_output_protection(tmp_path):
    path=tmp_path/'input.bag'; create_bag(path)
    def run(source,output):
        return subprocess.run([sys.executable,'-m','experiments.scripts.inspect_bag_offline',str(source),
                               '--output',str(output)],capture_output=True,text=True)
    output=tmp_path/'report.json'
    assert run(path,output).returncode==0
    original=output.read_bytes()
    assert json.loads(original)['structural_precheck_passed']
    assert run(path,output).returncode!=0 and output.read_bytes()==original
    raw=path.read_bytes()
    assert run(path,path).returncode!=0 and path.read_bytes()==raw
    bad=tmp_path/'bad.bag'; bad.write_bytes(b'corrupt')
    assert run(bad,tmp_path/'bad.json').returncode==2
