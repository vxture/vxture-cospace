import numpy as np
import pytest
from packages.construction.rgbd_diagnostics import boundaries,dilate,interior_mask,residual_summary


def test_interior_mask_excludes_holes_and_border_without_filling():
    depth=np.ones((15,15)); depth[7,7]=0
    core=interior_mask(depth,2)
    assert not core[5:10,5:10].any()
    assert not core[:2].any() and not core[-2:].any()
    assert core[3,3] and not np.any(core&(depth==0))
    assert np.array_equal(interior_mask(depth,0),depth>0)


def test_interior_all_missing_and_invalid_radius():
    assert not interior_mask(np.zeros((12,12)),4).any()
    with pytest.raises(ValueError): interior_mask(np.ones((12,12)),9)


def test_residual_partition_preserves_squared_error():
    a=np.array([.01,.02,.04,.08]); full=residual_summary(a)
    left=residual_summary(a[:2]); right=residual_summary(a[2:])
    assert full['over_35mm']==2
    assert np.isclose(full['squared_error_sum_m2'],left['squared_error_sum_m2']+right['squared_error_sum_m2'])
    assert np.isclose(full['rmse_m']**2,full['squared_error_sum_m2']/4)
    assert residual_summary(np.array([]))['rmse_m'] is None
    with pytest.raises(ValueError): residual_summary(np.array([float('nan')]))


def test_missing_boundary_is_separate_from_observed_surface_jump():
    depth=np.full((8,12),2.); depth[:,:3]=0; depth[:,7:]=3.
    holes,surfaces,_,stats=boundaries(depth,np.zeros((8,12,3),dtype='u1'))
    assert holes[:,2:4].all() and not holes[:,6:8].any()
    assert surfaces[:,6:8].all() and not surfaces[:,2:4].any()
    assert stats['valid_pixels']==72 and stats['image_edge_pixels']==0


def test_edge_proximity_does_not_wrap_across_image():
    mask=np.zeros((6,6),bool); mask[0,0]=True
    result=dilate(mask,1)
    assert result.sum()==4 and not result[-1].any() and not result[:,-1].any()


@pytest.mark.parametrize('value',[-1.,float('nan'),float('inf')])
def test_invalid_depth_rejected(value):
    with pytest.raises(ValueError): boundaries(np.full((2,3),value),np.zeros((2,3,3),dtype='u1'))
