import numpy as np
import pytest
from packages.construction.rgbd_tracking import rigid_fit,transform,register_pair
from packages.data.nyu_rgbd import make_cloud


def test_known_rigid_motion_and_composition():
    rng=np.random.default_rng(52); points=rng.normal(size=(500,3))
    theta=.07; expected=np.eye(4)
    expected[:3,:3]=[[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]]
    expected[:3,3]=[.03,-.02,.01]
    fitted=rigid_fit(points,transform(points,expected))
    assert np.allclose(fitted,expected,atol=1e-12)
    assert np.allclose(transform(transform(points,expected),np.linalg.inv(expected)),points)
    assert np.linalg.det(fitted[:3,:3])==pytest.approx(1)


def test_reflection_not_returned_as_rotation():
    rng=np.random.default_rng(11); source=rng.normal(size=(100,3)); target=source.copy(); target[:,0]*=-1
    fitted=rigid_fit(source,target)
    assert np.linalg.det(fitted[:3,:3])==pytest.approx(1)
    assert np.mean(np.linalg.norm(transform(source,fitted)-target,axis=1))>.1


@pytest.mark.parametrize('case',['collinear','nonfinite','short','shape'])
def test_invalid_fit(case):
    a=np.zeros((10,3)); b=a.copy()
    if case=='nonfinite': a[0,0]=np.nan
    if case=='short': a=b=np.zeros((2,3))
    if case=='shape': b=np.zeros((9,3))
    with pytest.raises(ValueError): rigid_fit(a,b)


@pytest.fixture
def cloud():
    v,u=np.mgrid[:480,:640]
    code=(960+20*np.sin(u/55)+15*np.cos(v/38)).astype('u2')
    return make_cloud(code,np.zeros((480,640,3),dtype='u1'),8)


def test_identical_cloud_accepts_zero_motion(cloud):
    points,_,pixels,_,_=cloud
    result=register_pair(points,points,pixels,8)
    assert result['accepted'],result
    assert np.allclose(result['T_previous_current'],np.eye(4),atol=1e-12)
    assert result['rmse_m']<1e-12
    assert not result['independent_accuracy_verified'] and not result['algorithm_ready']


def test_disjoint_cloud_rejected(cloud):
    points,_,pixels,_,_=cloud
    result=register_pair(points+[20,0,0],points,pixels,8)
    assert not result['accepted'] and result['matched_points']==0 and result['rmse_m'] is None


def test_many_to_one_does_not_inflate_overlap(cloud):
    points,_,pixels,_,_=cloud
    result=register_pair(np.repeat(points[:1],1000,axis=0),points,pixels,8)
    assert not result['accepted'] and result['matched_points']<=1


@pytest.mark.parametrize('case',['nan','duplicate_pixels','wrong_stride','outside'])
def test_input_validation(cloud,case):
    points,_,pixels,_,_=cloud; points=points.copy(); pixels=pixels.copy()
    if case=='nan': points[0,0]=np.nan
    if case=='duplicate_pixels': pixels[0]=pixels[1]
    if case=='wrong_stride': pixels[0]=[1,1]
    if case=='outside': pixels[0]=[640,0]
    with pytest.raises(ValueError): register_pair(points,points,pixels,8)


def test_rejected_edge_stops_trajectory_and_keeps_last_accepted_frame(tmp_path,monkeypatch,cloud):
    import hashlib,json,sys
    from experiments.scripts import track_nyu_short_scene as runner
    snapshot=tmp_path/'snapshot'; (snapshot/'raw').mkdir(parents=True)
    members={}; pairs=[]
    for i in range(4):
        pair={'accepted':True,'depth_time_us':i*33000}
        for role in ('depth','rgb'):
            name=f'{role}-{i}'; raw=bytes([i])
            (snapshot/'raw'/name).write_bytes(raw)
            members[name]={'bytes':1,'sha256':hashlib.sha256(raw).hexdigest()}; pair[role]=name
        pairs.append(pair)
    (snapshot/'report.json').write_text(json.dumps({'pairs':pairs,'members':members}))
    monkeypatch.setattr(runner,'read_pnm',lambda *args:None)
    monkeypatch.setattr(runner,'make_cloud',lambda *args:cloud)
    calls=[]
    def register(*args):
        calls.append(1); matrix=np.eye(4); matrix[0,3]=.01
        return {'accepted':len(calls)==1,'T_previous_current':matrix.tolist(),'reasons':['forced_rejection'] if len(calls)>1 else []}
    monkeypatch.setattr(runner,'register_pair',register)
    output=tmp_path/'output'
    monkeypatch.setattr(sys,'argv',['track',str(snapshot),'--output',str(output)])
    runner.main()
    report=json.loads((output/'tracking.json').read_text())
    assert report['tracked_frames']==2 and len(calls)==2 and not report['completed']
    assert report['poses'][-1]['T_anchor_camera'][0][3]==pytest.approx(.01)
    assert report['accumulated_point_count']==len(cloud[0])*2


def test_tracking_rejects_corrupt_snapshot_before_registration(tmp_path,monkeypatch):
    import hashlib,json,sys
    from experiments.scripts import track_nyu_short_scene as runner
    snapshot=tmp_path/'snapshot'; (snapshot/'raw').mkdir(parents=True)
    (snapshot/'raw'/'depth').write_bytes(b'changed')
    pair={'accepted':True,'depth':'depth','rgb':'rgb','depth_time_us':1}
    (snapshot/'report.json').write_text(json.dumps({'pairs':[pair,pair],'members':{
        'depth':{'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}}}))
    monkeypatch.setattr(sys,'argv',['track',str(snapshot),'--output',str(tmp_path/'output')])
    with pytest.raises(ValueError,match='snapshot_integrity'): runner.main()
