import numpy as np
import pytest
from packages.construction.rgbd_multiscale import (increment,grid_for,surface_normals,solve_plane_step,
    register_multiscale,correspondences)
from packages.construction.rgbd_tracking import transform,register_pair
from packages.data.nyu_rgbd import make_cloud


@pytest.fixture
def levels():
    v,u=np.mgrid[:480,:640]
    depth=(965+22*np.sin(u/51)+19*np.cos(v/43)).astype('u2')
    rgb=np.zeros((480,640,3),dtype='u1'); result={}
    for stride in (16,8,4):
        p,_,pix,_,_=make_cloud(depth,rgb,stride); result[stride]=(p,pix)
    return result


def test_zero_increment_and_proper_rotation():
    assert np.array_equal(increment(np.zeros(6)),np.eye(4))
    m=increment(np.array([.02,-.01,.03,.004,.002,-.001]))
    assert np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3))
    assert np.linalg.det(m[:3,:3])==pytest.approx(1)
    assert np.allclose(m[:3,3],[.004,.002,-.001])


def test_known_linearized_motion_is_recovered():
    rng=np.random.default_rng(19); p=rng.normal(size=(1000,3))
    normals=rng.normal(size=p.shape); normals/=np.linalg.norm(normals,axis=1)[:,None]
    expected=np.array([1e-4,-2e-4,3e-4,.0002,.0003,-.0001])
    target=p+np.cross(np.broadcast_to(expected[:3],p.shape),p)+expected[3:]
    actual,ratio,rmse=solve_plane_step(p,target,normals)
    assert np.allclose(actual,expected,atol=1e-12) and ratio>1e-7 and rmse>0


def test_plane_constraints_cannot_determine_all_six_dof():
    x,y=np.meshgrid(np.linspace(-1,1,30),np.linspace(-1,1,30))
    p=np.column_stack([x.ravel(),y.ravel(),np.ones(x.size)])
    normals=np.tile([0.,0.,1.],(len(p),1))
    with pytest.raises(ValueError,match='weak_plane_constraints'): solve_plane_step(p,p,normals)


@pytest.mark.parametrize('case',['shape','nonfinite'])
def test_plane_input_refused(case):
    a=np.ones((10,3)); b=a.copy(); n=a.copy()
    if case=='shape': b=b[:-1]
    if case=='nonfinite': a[0,0]=np.nan
    with pytest.raises(ValueError): solve_plane_step(a,b,n)


def test_normals_do_not_cross_depth_jump():
    pix=np.array([[x*4,y*4] for y in range(5) for x in range(5)])
    p=np.column_stack([pix[:,0]*.001,pix[:,1]*.001,np.where(pix[:,0]<8,2.,4.)])
    normals,valid=surface_normals(p,pix,4)
    at_jump=(pix[:,0]==4)|(pix[:,0]==8)
    assert not valid[at_jump].any()
    assert valid.any() and np.allclose(np.linalg.norm(normals[valid],axis=1),1)


def test_identity_registration_and_comparable_metric(levels):
    result=register_multiscale(levels,levels)
    assert result['accepted'],result
    assert result['rmse_m']<1e-12 and np.allclose(result['T_previous_current'],np.eye(4),atol=1e-12)
    p,pixels=levels[4]; baseline=register_pair(p,p,pixels)
    assert result['matched_points']==baseline['matched_points']
    assert result['overlap']==baseline['overlap']
    assert not result['algorithm_ready'] and not result['independent_accuracy_verified']


def test_small_known_translation_recovery(levels):
    shifted={stride:(p-np.array([.002,-.001,.0015]),pix) for stride,(p,pix) in levels.items()}
    result=register_multiscale(shifted,levels)
    assert result['accepted'],result
    assert np.allclose(np.array(result['T_previous_current'])[:3,3],[.002,-.001,.0015],atol=.0005)


def test_disjoint_cloud_is_rejected(levels):
    shifted={stride:(p+np.array([30.,0,0]),pix) for stride,(p,pix) in levels.items()}
    result=register_multiscale(shifted,levels)
    assert not result['accepted'] and result['matched_points']==0
    assert 'insufficient_normal_matches' in result['reasons']


def test_no_duplicate_target_vote(levels):
    p,pixels=levels[4]; grid=grid_for(p,pixels,4)
    _,src,dst,_=correspondences(np.repeat(p[:1],100,axis=0),p,grid,4,np.eye(4))
    assert len(src)==1 and len(np.unique(dst))==1


@pytest.mark.parametrize('case',['duplicate','out_of_bounds','nonfinite','bad_stride'])
def test_grid_input_validation(levels,case):
    p,pixels=levels[4]; p=p.copy(); pixels=pixels.copy(); stride=4
    if case=='duplicate': pixels[0]=pixels[1]
    if case=='out_of_bounds': pixels[0]=[640,0]
    if case=='nonfinite': p[0,0]=np.nan
    if case=='bad_stride': stride=0
    with pytest.raises(ValueError): grid_for(p,pixels,stride)
