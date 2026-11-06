import json
import time
from pathlib import Path
import numpy as np
import pytest
from packages.construction.build_process import Recorder, read_process, matrix, write
from packages.construction.preview_model import digest
from packages.data.input_preview import PreviewUnavailable
from test_preview_batches import prepared, files
from test_preview_inputs import source
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def temporal(tmp_path):
    _, jobs, directory, spaces, _ = prepared(tmp_path)
    folder = tmp_path/'timed'; folder.mkdir(); snapshot, tracking = source(folder)
    depth=snapshot/'raw/d.pgm';depth.write_bytes(b'P5\n640 480\n65535\n'+b'\xe8\x03'*(640*480))
    report = json.loads((snapshot/'report.json').read_bytes())
    report['members']['d.pgm']={'sha256':digest(depth),'bytes':depth.stat().st_size}
    report['pairs'] = [report['pairs'][0] | {'depth_time_us': 1000000+i*30000} for i in range(4)]
    (snapshot/'report.json').write_text(json.dumps(report))
    poses = [np.eye(4) for _ in range(3)]
    poses[1][0,3] = .03; poses[2][0,3] = .06
    tracking.write_text(json.dumps({'source_report_sha256': digest(snapshot/'report.json'),
                                  'prefix_T_anchor_camera': [m.tolist() for m in poses]}))
    record = jobs.inputs.register('timed', snapshot, tracking, spaces[0]['id'])
    return jobs, spaces[0]['id'], record, snapshot, tracking


def manual(tmp_path):
    jobs, space, record, snapshot, tracking = temporal(tmp_path)
    job = {'id':'build-timed', 'state':'running', 'input_id':record['id'],
           'space_id':space, 'project_id':record['project_id'], 'process_profile':'cospace.build-process/0.1',
           'input_binding':{k:v for k,v in record.items() if k not in ('snapshot','tracking')}}
    root = jobs.root/job['id']; root.mkdir(); jobs.save(job)
    source_data = json.loads((snapshot/'report.json').read_bytes())
    poses = json.loads(tracking.read_bytes())['prefix_T_anchor_camera']
    recorder = Recorder(root/'process', job, record['snapshot_sha256'], record['tracking_sha256'], source_data['pairs'], poses)
    return jobs, space, job, recorder, source_data, poses


def test_atomic_prefix_read_only_zero_additions_and_final_equivalence(tmp_path, monkeypatch):
    jobs, space, job, rec, src, poses = manual(tmp_path)
    monkeypatch.setattr(jobs, 'poll', lambda: pytest.fail('read must never poll'))
    assert read_process(jobs,space,job['id'])['processed_frames']==0
    p=np.array([[.011,0,1],[.08,0,1]],dtype=float); c=np.array([[10,20,30],[40,50,60]],dtype=np.uint8)
    for i in range(3):
        rec.record(src['pairs'][i], poses[i], p, c, src['members'])
        before=files(tmp_path);value=read_process(jobs,space,job['id'])
        assert value['processed_frames']==i+1 and value['point_count']==2
        assert files(tmp_path)==before
        assert value['first_seen_frames']==[0,0] and value['frames'][i]['added_points']==(2 if not i else 0)
        assert value['frames'][i]['relative_time_us']==i*30000
    model=jobs.root/job['id']/'test.npz';np.savez_compressed(model,points=p.astype(np.float32),colors=c)
    rec.complete(p.astype(np.float32),c,model)
    value=read_process(jobs,space,job['id'])
    assert value['state']=='completed' and value['excluded_frames']==1
    assert value['source_model_sha256']==digest(model)
    assert value['quality']=='unverified' and not value['robot_ready']
    assert 'input_binding' not in value and 'chunk' not in value['frames'][0]
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path('contracts/schemas/build-process-v0.1.schema.json').read_bytes())).validate(value)
    Draft202012Validator(json.loads(Path('contracts/schemas/build-process-index-v0.1.schema.json').read_bytes())).validate(json.loads((rec.root/'process.json').read_bytes()))


def test_windows_atomic_index_retry_is_bounded_preserves_previous(tmp_path,monkeypatch):
    path=tmp_path/'process.json';write(path,{'revision':0});replace=Path.replace;calls=[]
    def busy(self,target):
        calls.append(1)
        if len(calls)<3:
            assert json.loads(path.read_bytes())=={'revision':0}
            raise PermissionError('sharing_violation')
        return replace(self,target)
    monkeypatch.setattr(Path,'replace',busy)
    write(path,{'revision':1});assert len(calls)==3 and json.loads(path.read_bytes())=={'revision':1}
    monkeypatch.setattr(Path,'replace',lambda *a: (_ for _ in ()).throw(PermissionError('locked')))
    monkeypatch.setattr('packages.construction.build_process.time.sleep',lambda _:None)
    with pytest.raises(PermissionError):write(path,{'revision':2})
    assert json.loads(path.read_bytes())=={'revision':1}


@pytest.mark.parametrize('case',['pose','frame','digest','chunk','binding','time','budget','nan'])
def test_corrupt_process_never_draws(tmp_path, case):
    jobs,space,job,rec,src,poses=manual(tmp_path)
    rec.record(src['pairs'][0],poses[0],np.array([[1.,2.,3.]]),np.array([[1,2,3]],dtype=np.uint8),src['members'])
    p=rec.root/'process.json';v=json.loads(p.read_bytes())
    if case=='pose':v['frames'][0]['pose'][0][0]=2
    elif case=='frame':v['frames'][0]['index']=3
    elif case=='digest':v['frames'][0]['sha256']='0'*64
    elif case=='chunk':v['frames'][0]['chunk']='../outside'
    elif case=='binding':v['input_id']='input-wrong'
    elif case=='time':v['frames'][0]['relative_time_us']=1
    elif case=='budget':v['input_frames']=501
    elif case=='nan':v['frames'][0]['pose'][0][0]=float('nan')
    p.write_text(json.dumps(v))
    with pytest.raises(PreviewUnavailable):read_process(jobs,space,job['id'])


@pytest.mark.parametrize('state',['failed','interrupted'])
def test_partial_survives_failure_restart_and_cannot_complete_early(tmp_path,state):
    jobs,space,job,rec,src,poses=manual(tmp_path)
    p=np.array([[1.,2.,3.]]);c=np.array([[1,2,3]],dtype=np.uint8)
    rec.record(src['pairs'][0],poses[0],p,c,src['members'])
    with pytest.raises(ValueError,match='incomplete'):rec.complete(p,c,Path('missing'))
    job['state']=state;jobs.save(job)
    value=read_process(jobs,space,job['id'])
    assert value['state']==state and value['processed_frames']==1 and len(value['points'])==1
    before=files(tmp_path)
    assert read_process(jobs,space,job['id'])==value and files(tmp_path)==before


def test_global_display_budget_and_no_future_points(tmp_path):
    jobs,space,job,rec,src,poses=manual(tmp_path)
    p=np.column_stack((np.arange(12000)*.1,np.zeros(12000),np.ones(12000)))
    rec.record(src['pairs'][0],poses[0],p,np.full(p.shape,50,dtype=np.uint8),src['members'])
    value=read_process(jobs,space,job['id'])
    assert len(value['points'])==6000 and len(value['first_seen_frames'])==6000
    assert max(value['first_seen_frames'])==0 and len(value['frames'])==1
    assert len(json.dumps(value).encode())<2*1024*1024


def test_real_worker_records_same_frozen_points_and_integrity(tmp_path):
    jobs,space,record,_,_=temporal(tmp_path)
    job=jobs.start(record['id'],space)
    for _ in range(500):
        job=next(j for j in jobs.list() if j['id']==job['id'])
        if job['state'] not in ('queued','running'):break
        time.sleep(.03)
    assert job['state']=='succeeded',job
    value=read_process(jobs,space,job['id'])
    assert value['processed_frames']==3 and value['excluded_frames']==1
    assert value['state']=='completed' and value['point_count']>0
    path=jobs.root/job['id']/'process/process.json';index=json.loads(path.read_bytes())
    index['frames'][0]['pose'][0][3]=.1;path.write_text(json.dumps(index))
    with pytest.raises(PreviewUnavailable):read_process(jobs,space,job['id'])


@pytest.mark.parametrize('user,allowed',[('usr_local_test',False),('usr_other',False),('usr_engineer',True),('usr_manager',True)])
def test_process_http_permissions_and_old_jobs(secured,user,allowed):
    _,client,_,_,jobs,_,spaces,*_=secured
    url='/api/build-process';params={'space_id':spaces[0]['id'],'candidate_id':'build-one'}
    assert client.get(url,params=params).status_code==401
    headers,_=sign_in(secured,user)
    response=client.get(url,params=params)
    assert response.status_code==(200 if allowed else 403),response.text
    if allowed:
        assert response.json()['supported'] is False and response.headers['cache-control']=='no-store'
        assert client.get(url,params=params|{'path':'outside'}).status_code==422
        assert client.get(url,params=list(params.items())+[('candidate_id','build-one')]).status_code==403
    assert client.get(url,params=params|{'space_id':spaces[1]['id']}).status_code==403
    assert client.post(url,json=params,headers=headers).status_code==403


@pytest.mark.parametrize('value',[np.zeros((4,4)),np.eye(3),np.diag([-1,1,1,1])])
def test_invalid_camera_pose_rejected(value):
    with pytest.raises(ValueError):matrix(value)
