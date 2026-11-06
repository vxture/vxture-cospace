import numpy as np
import pytest
from packages.construction.rgbd_rectify import rasterize_depth_cloud
from packages.data.nyu_rgbd import DEPTH_K


def at_pixel(x,y,z):
    return [(x-(DEPTH_K[2]-1))*z/DEPTH_K[0],(y-(DEPTH_K[3]-1))*z/DEPTH_K[1],z]


def test_nearest_surface_wins_and_holes_remain_invalid():
    points=np.array([at_pixel(300,200,3),at_pixel(300,200,2),at_pixel(310,210,4)])
    colors=np.array([[255,0,0],[0,255,0],[0,0,255]],dtype='u1')
    depth,color,report=rasterize_depth_cloud(points,colors,np.ones(3,dtype=bool))
    assert depth.dtype==np.float32 and depth[200,300]==2
    assert np.array_equal(color[200,300],[0,255,0])
    assert np.count_nonzero(depth)==2 and report['unobserved_pixels']==480*640-2
    assert not report['depth_inpainted']


def test_uncolored_or_outside_or_negative_points_do_not_become_depth():
    points=np.array([at_pixel(300,200,2),at_pixel(300,200,-1),at_pixel(800,200,2)])
    depth,_,report=rasterize_depth_cloud(points,np.ones((3,3),dtype='u1'),np.array([False,True,True]))
    assert not np.any(depth) and report['valid_pixels']==0


def test_invalid_cloud_is_rejected():
    with pytest.raises(ValueError): rasterize_depth_cloud(np.array([[np.nan,0,1]]),np.ones((1,3)),np.ones(1,dtype=bool))
