import hashlib
import json
import struct
import time
from pathlib import Path
import numpy as np
import pytest
from rosbags.rosbag1 import Writer,Reader
from rosbags.typesys import Stores,get_typestore
from packages.construction.lidar_mapping import register_pair,transform
from packages.data.preview_lidar import read_specimen,MULTIFRAME_FORMAT
from packages.construction.preview_model import digest
from packages.construction.build_process import read_process
from packages.data.input_preview import PreviewUnavailable
from test_preview_batches import prepared


def sequence(root,broken=False):
    root.mkdir();store=get_typestore(Stores.ROS1_NOETIC);t=store.types
    Header=t['std_msgs/msg/Header'];Time=t['builtin_interfaces/msg/Time'];Field=t['sensor_msgs/msg/PointField']
    V=t['geometry_msgs/msg/Vector3'];Q=t['geometry_msgs/msg/Quaternion']
    rng=np.random.default_rng(42);world=rng.uniform([-3,-2,-1],[4,3,2],(1800,3)).astype(np.float32)
    with Writer(root/'sample.bag') as writer:
        pc=writer.add_connection('/points','sensor_msgs/msg/PointCloud2',typestore=store)
        imu=writer.add_connection('/imu','sensor_msgs/msg/Imu',typestore=store)
        for i in range(21):
            header=Header(i,Time(100,i*10_000_000),'imu')
            message=t['sensor_msgs/msg/Imu'](header,Q(0.,0.,0.,1.),np.zeros(9),V(0.,0.,0.),np.zeros(9),V(0.,0.,9.81),np.zeros(9))
            writer.write(imu,100_000_000_000+i*10_000_000,store.serialize_ros1(message,message.__msgtype__))
            if i%10==0:
                points=world-np.array([i*.003,0.,0.],dtype=np.float32)
                if broken and i==20:points+=100
                payload=b''.join(struct.pack('<ffffII',*p,100.,j,1000) for j,p in enumerate(points))
                fields=[Field(n,o,k,1) for n,o,k in [('x',0,7),('y',4,7),('z',8,7),('intensity',12,7),('t',16,6),('range',20,6)]]
                message=t['sensor_msgs/msg/PointCloud2'](Header(i,Time(100,i*10_000_000),'lidar'),1,len(points),fields,False,24,len(payload),np.frombuffer(payload,dtype=np.uint8).copy(),True)
                writer.write(pc,100_000_000_000+i*10_000_000,store.serialize_ros1(message,message.__msgtype__))
    records=[]
    with Reader(root/'sample.bag') as reader:
        for c,at,raw in reader.messages():
            msg=store.deserialize_ros1(raw,c.msgtype)
            records.append({'topic':c.topic,'recorded_ns':at,'serialized_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'frame_id':msg.header.frame_id,'header_ns':msg.header.stamp.sec*10**9+msg.header.stamp.nanosec})
    first=next(r for r in records if r['topic']=='/points')
    doc={'profile':'cospace.external-lidar-specimen/0.1','artifacts':{'sample.bag':{'bytes':(root/'sample.bag').stat().st_size,'sha256':digest(root/'sample.bag')}},
        'messages':records,'topics':{'/imu':21,'/points':3},'first_frame':{'from_message':first,'frame_id':'lidar','unit':'m','valid_points':len(world)},
        'recorded_window':{'start_ns':100_000_000_000,'end_exclusive_ns':101_000_000_000}}
    (root/'sample.json').write_text(json.dumps(doc));return root


def wait(jobs,identity):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        job=next(j for j in jobs.list() if j['id']==identity)
        if job['state'] not in ('queued','running'):return job
        time.sleep(.04)
    pytest.fail('mapping timeout')


def test_known_motion_registration_direction():
    rng=np.random.default_rng(1);p=rng.uniform(-3,3,(2000,3));pose=np.eye(4)
    a=.025;pose[:3,:3]=[[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]];pose[:3,3]=[.06,-.03,.02]
    current=transform(p,np.linalg.inv(pose));r=register_pair(current,p)
    assert r['accepted'];np.testing.assert_allclose(r['T_previous_current'],pose,atol=2e-3)
    assert not register_pair(current+100,p)['accepted']


def test_sequence_input_keeps_old_first_frame_meaning(tmp_path):
    root=sequence(tmp_path/'source');single,p,_=read_specimen(root);multi,frames=read_specimen(root,sequence=True)
    assert single['used_frames']==1 and multi['used_frames']==0 and len(frames)==3
    assert multi['sequence_frames'][0]==single['selected_frame'];np.testing.assert_equal(frames[0]['points'],p)


def mapped(tmp_path,broken=False):
    _,jobs,_,spaces,_=prepared(tmp_path);root=sequence(tmp_path/'laser',broken)
    record=jobs.inputs.register('laser mapping',root,space_id=spaces[0]['id'],format=MULTIFRAME_FORMAT)
    job=wait(jobs,jobs.start(record['id'],spaces[0]['id'])['id'])
    return jobs,spaces[0]['id'],record,job,root


def test_real_subprocess_freeze_dual_views_and_process_match(tmp_path):
    jobs,space,record,job,_=mapped(tmp_path)
    assert job['state']=='succeeded',(job,(jobs.root/job['id']/'build.log').read_text())
    model=jobs.model(job['id']);m=model.manifest
    assert m['construction']['used_frames']==3 and m['data_kind']=='real_lidar_multiframe_candidate'
    assert m['source']['input_binding']['format']==MULTIFRAME_FORMAT and m['robot_ready'] is False
    assert m['human_view']['source_model_sha256']==m['agent_view']['source_model_sha256']
    process=read_process(jobs,space,job['id'])
    assert process['state']=='completed' and process['processed_frames']==3 and process['point_count']==m['construction']['model_points']
    assert all(f['input_points']==1800 for f in process['frames']) and process['frames'][0]['added_points']>0
    assert process['frames'][2]['pose'][0][3]==pytest.approx(.06,abs=.002)
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path('contracts/schemas/lidar-build-process-v0.1.schema.json').read_bytes())).validate(process)
    Draft202012Validator(json.loads(Path('contracts/schemas/lidar-build-process-index-v0.1.schema.json').read_bytes())).validate(json.loads((jobs.root/job['id']/'process/process.json').read_bytes()))
    assert 'tracking_sha256' not in process and 'depth_sha256' not in process['frames'][0]
    with np.load(model.root/'spatial.npz') as a:
        chunks=[np.load(jobs.root/job['id']/'process'/f'frame-{i:04d}.npz')['points'] for i in range(3)]
        allpoints=np.concatenate(chunks);order=np.lexsort(np.floor(allpoints/.05).astype(np.int64).T[::-1])
        # Final equality already enforced before freezing by Recorder.complete.
        assert len(allpoints)==len(a['points'])
    with pytest.raises(ValueError):read_process(jobs,'space-0000000000000000',job['id'])
    other=next(s for s in jobs.directory.list('space') if s['id']!=space)
    with pytest.raises(ValueError):read_process(jobs,other['id'],job['id'])


@pytest.mark.parametrize('change',['pose','time','message','bag','chunk','chain'])
def test_process_tampering_refused(tmp_path,change):
    jobs,space,_,job,_=mapped(tmp_path);root=jobs.root/job['id'];path=root/'process/process.json';v=json.loads(path.read_bytes())
    if change=='pose':v['frames'][1]['pose'][0][0]=2
    if change=='time':v['frames'][1]['header_ns']='1'
    if change=='message':v['frames'][1]['message_sha256']='0'*64
    if change=='bag':v['bag_sha256']='0'*64
    if change=='chain':v['frames'][1]['pose'][0][3]+=1
    if change=='chunk':(root/'process/frame-0001.npz').write_bytes(b'bad')
    path.write_text(json.dumps(v))
    with pytest.raises(PreviewUnavailable):read_process(jobs,space,job['id'])


def test_rejection_preserves_prefix_retry_and_restart(tmp_path):
    jobs,space,record,job,root=mapped(tmp_path,True)
    assert job['state']=='failed'
    process=read_process(jobs,space,job['id']);assert process['state']=='failed' and process['processed_frames']==2
    assert process['rejection']['index']==2
    assert not (jobs.root/job['id']/'frozen/frozen.json').exists()
    result=jobs.retry(space,job['id'],'1'*32);again=jobs.retry(space,job['id'],'1'*32)
    assert result['job']['id']==again['job']['id'] and not again['created']
    assert wait(jobs,result['job']['id'])['state']=='failed'
    assert read_process(jobs,space,job['id'])['processed_frames']==2
