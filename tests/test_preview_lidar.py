import hashlib
import json
from pathlib import Path
import struct
import time
import numpy as np
import pytest
from rosbags.rosbag1 import Writer,Reader
from rosbags.typesys import Stores,get_typestore
from fastapi.testclient import TestClient
from packages.data.preview_lidar import read_specimen,FORMAT
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_source_config import load_sources
from packages.construction.preview_lidar import build
from packages.construction.preview_jobs import PreviewJobs
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.ontology.preview_versions import PreviewOntologies
from packages.views.agent.preview_offline import OfflinePreview,sha
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview


def specimen(tmp_path):
    root=tmp_path/'specimen';root.mkdir();store=get_typestore(Stores.ROS1_NOETIC);t=store.types
    Header=t['std_msgs/msg/Header'];Time=t['builtin_interfaces/msg/Time'];Field=t['sensor_msgs/msg/PointField']
    V=t['geometry_msgs/msg/Vector3'];Q=t['geometry_msgs/msg/Quaternion']
    def header(i,frame):return Header(i,Time(100,i*10_000_000),frame)
    with Writer(root/'sample.bag') as writer:
        pc=writer.add_connection('/points','sensor_msgs/msg/PointCloud2',typestore=store)
        imu=writer.add_connection('/imu','sensor_msgs/msg/Imu',typestore=store)
        for i in range(21):
            message=t['sensor_msgs/msg/Imu'](header(i,'imu'),Q(0.,0.,0.,1.),np.zeros(9),V(0.,0.,0.),np.zeros(9),V(0.,0.,9.81),np.zeros(9))
            writer.write(imu,100_000_000_000+i*10_000_000,store.serialize_ros1(message,message.__msgtype__))
            if i%10==0:
                fields=[Field(name,offset,kind,1) for name,offset,kind in [('x',0,7),('y',4,7),('z',8,7),('intensity',12,7),('t',16,6),('range',20,6)]]
                payload=b''.join(struct.pack('<ffffII',*values) for values in [(1.+i,2.,.5,10.,0,1000),(2.+i,3.,.6,20.,1000,2000),(0.,0.,0.,0.,2000,0)])
                message=t['sensor_msgs/msg/PointCloud2'](header(i,'lidar'),1,3,fields,False,24,len(payload),np.frombuffer(payload,dtype=np.uint8).copy(),True)
                writer.write(pc,100_000_000_000+i*10_000_000,store.serialize_ros1(message,message.__msgtype__))
    records=[]
    with Reader(root/'sample.bag') as reader:
        for c,at,raw in reader.messages():
            msg=store.deserialize_ros1(raw,c.msgtype)
            records.append({'topic':c.topic,'recorded_ns':at,'serialized_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                            'frame_id':msg.header.frame_id,'header_ns':msg.header.stamp.sec*10**9+msg.header.stamp.nanosec})
    raw=(root/'sample.bag').read_bytes();first=next(r for r in records if r['topic']=='/points')
    doc={'profile':'cospace.external-lidar-specimen/0.1','artifacts':{'sample.bag':{'bytes':len(raw),'sha256':sha(raw)}},
         'messages':records,'topics':{'/imu':21,'/points':3},'first_frame':{'from_message':first,'frame_id':'lidar','unit':'m','valid_points':2},
         'recorded_window':{'start_ns':100_000_000_000,'end_exclusive_ns':101_000_000_000}}
    (root/'sample.json').write_text(json.dumps(doc),encoding='utf-8');return root


def test_single_frame_uses_local_coordinates_not_later_scans_or_nyu_axes(tmp_path):
    root=specimen(tmp_path);summary,points,intensity=read_specimen(root)
    assert summary['input_frames']==3 and summary['used_frames']==1 and summary['verified_messages']==24
    np.testing.assert_allclose(points,[[1,2,.5],[2,3,.6]]);assert intensity.tolist()==[10,20]
    model=build(root,tmp_path/'output','build-test')
    assert model['frame_id']=='lidar' and model['axes']==['sensor_x','sensor_y','sensor_z']
    assert 'tracking' not in model['source'] and 'tracking_sha256' not in model['source']
    assert model['human_view']['appearance']=='intensity_grayscale_not_rgb'
    assert model['human_view']['source_model_sha256']==model['agent_view']['source_model_sha256']
    with np.load(tmp_path/'output/spatial.npz') as arrays:np.testing.assert_array_equal(arrays['points'],points)
    assert 'no_global_registration' in model['limitations'] and model['robot_ready'] is False
    with pytest.raises(FileExistsError):build(root,tmp_path/'output','build-overwrite')


@pytest.mark.parametrize('change',[
    lambda d:d['messages'][0].update(sha256='0'*64),
    lambda d:d['first_frame'].update(frame_id='map'),
    lambda d:d['first_frame'].update(valid_points=3),
    lambda d:d['first_frame']['from_message'].update(recorded_ns=1),
    lambda d:d['recorded_window'].update(end_exclusive_ns=1),
])
def test_capture_evidence_changes_rejected_before_registration(tmp_path,change):
    root=specimen(tmp_path);path=root/'sample.json';doc=json.loads(path.read_bytes());change(doc)
    path.write_text(json.dumps(doc),encoding='utf-8');catalog=PreviewInputs(tmp_path/'catalog')
    with pytest.raises(ValueError):catalog.register('bad',root,format=FORMAT)
    assert catalog.list()==[]


def test_changed_bytes_refused_and_no_trajectory_required(tmp_path):
    root=specimen(tmp_path);catalog=PreviewInputs(tmp_path/'catalog')
    record=catalog.register('lidar',root,format=FORMAT)
    assert 'tracking' not in record and 'verified_image_members' not in record
    with pytest.raises(ValueError,match='tracking_not_supported'):catalog.register('bad',root,root/'fake.json',format=FORMAT)
    with (root/'sample.bag').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='lidar_bag_integrity'):catalog.resolve(record['id'])


def test_new_source_config_validates_format_specific_paths(tmp_path):
    specimen(tmp_path);doc={'profile':'cospace.preview-sources/0.1','sources':[{'id':'lidar','label':'lidar','format':FORMAT,'enabled':True,'snapshot':'specimen'}]}
    path=tmp_path/'config.json';path.write_text(json.dumps(doc),encoding='utf-8')
    allowed,status=load_sources(path,tmp_path,True)
    assert allowed['lidar']['tracking'] is None and status['sources'][0]['status']=='validated'
    doc['sources'][0]['tracking']='fake.json';path.write_text(json.dumps(doc),encoding='utf-8')
    with pytest.raises(ValueError,match='tracking_not_supported'):load_sources(path,tmp_path)


def test_http_subprocess_annotation_publish_offline_and_scope(tmp_path):
    root=specimen(tmp_path);initial=tmp_path/'initial';initial.mkdir();make_preview(initial)
    directory=PreviewSpaces(tmp_path/'directory');project=directory.create('project','test')
    a,b=[directory.create('space',n,project['id']) for n in ('lidar','other')]
    catalog=PreviewInputs(tmp_path/'catalog',directory)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,catalog)
    ontology=PreviewOntologies(tmp_path/'ontology');rule=ontology.register('configs/ontology/indoor-equipment-v0.1.json')
    sources={'lidar':{'label':'lidar','snapshot':root,'format':FORMAT}}
    with TestClient(create_app(initial,jobs,registration_sources=sources,space_directory=directory,ontologies=ontology)) as client:
        request={'source_id':'lidar','label':'laser','space_id':a['id']}
        response=client.post('/api/inputs',json=request);assert response.status_code==201,response.text
        record=response.json()['input'];assert client.post('/api/inputs',json=request).json()['created'] is False
        assert client.post('/api/inputs/'+record['id']+'/preflight').json()['status']=='passed'
        detail=client.get('/api/inputs/'+record['id']).json();assert '单帧' in detail['supported_format'] and 'tracking' not in detail
        assert client.post('/api/builds',json={'input_id':record['id'],'space_id':b['id']}).status_code==409
        response=client.post('/api/builds',json={'input_id':record['id'],'space_id':a['id']});assert response.status_code==202,response.text
        identity=response.json()['id'];deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            job=next(j for j in jobs.list() if j['id']==identity)
            if job['state'] not in ('queued','running'):break
            time.sleep(.05)
        assert job['state']=='succeeded',(job,(jobs.root/identity/'build.log').read_text())
        m=jobs.model(identity);assert m.manifest['construction']['used_frames']==1
        assert client.get(job['candidate_url']+'api/thumbnail').content.startswith(b'\x89PNG')
        ref={k:rule[k] for k in ('ontology_id','version','sha256')}
        body={'space_id':a['id'],'base_candidate_id':identity,'base_manifest_sha256':hashlib.sha256((m.root/'model.json').read_bytes()).hexdigest(),
              'ontology_ref':ref,'objects':[{'object_id':'lidar-test-001','type_id':'inspection_point','properties':{'name':'流程测试锚点'},'point_index':0}]}
        response=client.post('/api/semantic-candidates',json=body);assert response.status_code==201,response.text
        semantic=response.json()['id']
        assert client.post('/api/selection',json={'space_id':a['id'],'candidate_id':semantic,'expected_revision':0}).status_code==200
        pub=client.post('/api/publications',json={'space_id':a['id'],'candidate_id':semantic,'expected_revision':1}).json()
        raw=client.get(pub['preview_url']+'offline.zip').content;offline=OfflinePreview(raw,pub['id'],sha(raw))
        online=client.get(pub['preview_url']+'api/objects/lidar-test-001').json()
        assert online==offline.objects('lidar-test-001') and online['frame_id']=='lidar'
        assert online['objects'][0]['confirmation']=='unverified'
        point=[1.05,2.05,.55];assert client.post(pub['query_url'],json={'point_m':point}).json()==offline.query(point)
        assert all(n['status']=='matched' for n in client.get(pub['preview_url']+'api/lineage').json()['nodes'])
        assert next(s for s in client.get(pub['preview_url']+'api/checklist').json()['stages'] if s['id']=='query')['status']=='passed'
        assert client.get('/api/publications',params={'space_id':b['id']}).json()['publications']==[]
        assert jobs.selection()['revision']==0
