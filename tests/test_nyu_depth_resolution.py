import numpy as np
import pytest
from packages.construction.nyu_depth_resolution import decode_codes,quantize_depth,quantize_points


def test_exact_neighbor_step_and_monotonicity():
    codes=np.array([700,800,900,1000,1040])
    depths=decode_codes(codes)
    assert np.all(np.diff(depths)>0)
    step=decode_codes(codes+1)-depths
    assert np.allclose(step,351.3/((1092.5-codes)*(1091.5-codes)))
    assert np.all(step>depths**2/351.3)


def test_code_roundtrip_and_quantized_rays():
    codes=np.arange(600,1058)
    decoded=decode_codes(codes); measured,actual=quantize_depth(decoded)
    assert np.array_equal(actual,codes) and np.allclose(measured,decoded)
    points=np.array([[.4,.2,2.],[1.,-.3,6.]])
    quantized=quantize_points(points)
    assert np.allclose(quantized[:,:2]/quantized[:,2,None],points[:,:2]/points[:,2,None])


def test_known_translation_is_exact_before_quantization():
    rng=np.random.default_rng(123); target=rng.uniform(-.2,.2,(300,3)); target[:,2]+=6
    motion=np.array([0.,0.,.02]); source=target-motion
    assert np.max(np.linalg.norm(source+motion-target,axis=1))<1e-12
    distance=np.linalg.norm(quantize_points(source)+motion-quantize_points(target),axis=1)
    assert np.sqrt(np.mean(distance**2))>.01


@pytest.mark.parametrize('code',[599,1058,1093,2047,1000.5,float('nan')])
def test_invalid_codes_are_not_clamped(code):
    with pytest.raises(ValueError): decode_codes(np.array([code]))


@pytest.mark.parametrize('depth',[0.,-1.,.5,11.,float('inf')])
def test_unsupported_quantization_rejected(depth):
    with pytest.raises(ValueError): quantize_depth(np.array([depth]))
