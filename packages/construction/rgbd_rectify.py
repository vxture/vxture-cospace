"""Rectify a sampled NYU depth cloud into a pinhole grid without filling holes."""
import numpy as np
from packages.data.nyu_rgbd import DEPTH_K


def rasterize_depth_cloud(points,colors,color_valid):
    if (points.ndim!=2 or points.shape[1]!=3 or colors.shape!=points.shape
        or color_valid.shape!=(len(points),) or not np.isfinite(points).all()):
        raise ValueError('invalid_cloud')
    good=(points[:,2]>0)&(points[:,2]<=10)&color_valid
    ids=np.flatnonzero(good)
    p=points[ids]
    x=np.rint(p[:,0]*DEPTH_K[0]/p[:,2]+DEPTH_K[2]-1).astype(int)
    y=np.rint(p[:,1]*DEPTH_K[1]/p[:,2]+DEPTH_K[3]-1).astype(int)
    inside=(x>=0)&(x<640)&(y>=0)&(y<480)
    ids=ids[inside]; x=x[inside]; y=y[inside]
    # For collisions select the closest observed surface, without interpolating missing depth.
    order=np.argsort(points[ids,2],kind='stable'); ids=ids[order]; x=x[order]; y=y[order]
    _,first=np.unique(y*640+x,return_index=True)
    ids=ids[first]; x=x[first]; y=y[first]
    depth=np.zeros((480,640),dtype=np.float32); color=np.zeros((480,640,3),dtype=np.uint8)
    depth[y,x]=points[ids,2]; color[y,x]=colors[ids]
    return depth,color,{'valid_pixels':len(ids),'unobserved_pixels':int(depth.size-len(ids)),
                        'input_points':len(points),'color_required':True,'depth_inpainted':False}
