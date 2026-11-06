import numpy as np
import pytest
from packages.data.nyu_rgbd import read_pnm,timestamp_us,make_cloud,ply_bytes,distort


def test_timestamp_preserves_microseconds():
    assert timestamp_us('d-1294619369.100506-2678041901.pgm')==1294619369100506
    with pytest.raises(ValueError): timestamp_us('unknown.pgm')


def test_depth_little_endian_is_not_generic_pgm_big_endian():
    raw=b'P5 640 480 65535\n'+np.full((480,640),1000,dtype='<u2').tobytes()
    decoded=read_pnm(raw,True)
    assert decoded.shape==(480,640) and decoded[0,0]==1000
    with pytest.raises(ValueError,match='length'): read_pnm(raw[:-1],True)
    with pytest.raises(ValueError,match='profile'): read_pnm(raw)


def test_rgb_roundtrip():
    rgb=np.full((480,640,3),47,dtype='u1')
    assert np.array_equal(read_pnm(b'P6 640 480 255\n'+rgb.tobytes()),rgb)


@pytest.mark.parametrize('code',[0,599,1093,2047,65535])
def test_invalid_depth_never_becomes_surface(code):
    points,colors,pixels,valid,stats=make_cloud(np.full((480,640),code,dtype='u2'),np.zeros((480,640,3),dtype='u1'),16)
    assert len(points)==0 and stats['valid_points']==0
    assert stats['invalid_or_unresolved_pixels']==stats['sampled_pixels']


def test_metric_depth_and_pixel_association():
    depth=np.full((480,640),1000,dtype='u2'); rgb=np.zeros((480,640,3),dtype='u1'); rgb[:]=[11,22,33]
    points,colors,pixels,color_valid,stats=make_cloud(depth,rgb,16)
    assert np.allclose(points[:,2],351.3/92.5)
    assert np.all(pixels[:,0]%16==0) and np.all(pixels[:,1]%16==0)
    assert np.all(colors[color_valid]==[11,22,33])
    assert stats['valid_points']+stats['invalid_or_unresolved_pixels']==stats['sampled_pixels']
    output=ply_bytes(points,colors,color_valid)
    assert f'element vertex {len(points)}'.encode() in output
    assert b'property uchar color_valid' in output
    assert len(output.split(b'end_header\n')[1].splitlines())==len(points)


def test_distortion_identity_and_invalid_stride():
    x=np.array([0.,.2]); y=np.array([0.,-.3])
    a,b=distort(x,y,[0,0,0,0,0]); assert np.array_equal(a,x) and np.array_equal(b,y)
    with pytest.raises(ValueError,match='stride'):
        make_cloud(np.zeros((480,640)),np.zeros((480,640,3)),0)
