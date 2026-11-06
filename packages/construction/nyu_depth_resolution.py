"""NYU code resolution and controlled quantization; not a sensor noise model."""
import numpy as np


def decode_codes(codes):
    codes=np.asarray(codes)
    if not np.isfinite(codes).all() or np.any(codes!=np.floor(codes)):
        raise ValueError('noninteger_code')
    with np.errstate(divide='ignore',invalid='ignore'):
        z=351.3/(1092.5-codes)
    if np.any(codes<600) or np.any(codes>=2047) or np.any(z<=0) or np.any(z>10) or not np.isfinite(z).all():
        raise ValueError('unsupported_depth_code')
    return z


def quantize_depth(depth):
    depth=np.asarray(depth,dtype=float)
    if not np.isfinite(depth).all() or np.any(depth<=0) or np.any(depth>10):
        raise ValueError('unsupported_depth')
    code=np.rint(1092.5-351.3/depth).astype(np.int64)
    return decode_codes(code),code


def quantize_points(points):
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():
        raise ValueError('invalid_points')
    measured,_=quantize_depth(points[:,2])
    return points*(measured/points[:,2])[:,None]
