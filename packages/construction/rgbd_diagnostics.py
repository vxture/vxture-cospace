"""Descriptive RGB-D boundary diagnostics; no calibrated quality gate."""
import numpy as np


def dilate(mask,radius=2):
    if mask.ndim!=2 or mask.dtype!=bool or type(radius) is not int or not 0<=radius<=8:
        raise ValueError('invalid_mask')
    out=np.zeros_like(mask); padded=np.pad(mask,radius)
    for y in range(2*radius+1):
        for x in range(2*radius+1): out |= padded[y:y+mask.shape[0],x:x+mask.shape[1]]
    return out


def boundaries(depth,color):
    if (depth.ndim!=2 or color.shape!=(*depth.shape,3) or not np.isfinite(depth).all()
        or np.any(depth<0) or color.dtype!=np.uint8): raise ValueError('invalid_rgbd')
    valid=depth>0; holes=np.zeros_like(valid); surfaces=np.zeros_like(valid)
    for axis in (0,1):
        lo=[slice(None),slice(None)]; hi=lo.copy(); lo[axis]=slice(None,-1); hi[axis]=slice(1,None)
        lo=tuple(lo); hi=tuple(hi)
        transition=valid[lo]!=valid[hi]
        jump=valid[lo]&valid[hi]&(np.abs(depth[lo]-depth[hi])>.15)
        holes[lo]|=transition; holes[hi]|=transition
        surfaces[lo]|=jump; surfaces[hi]|=jump
    gray=color.astype(float).mean(axis=2)/255
    image_edges=np.zeros_like(valid)
    image_edges[:,1:] |= np.abs(np.diff(gray,axis=1))>.1
    image_edges[1:,:] |= np.abs(np.diff(gray,axis=0))>.1
    valid_edges=image_edges&valid
    near_hole=dilate(holes)
    stats={'valid_pixels':int(valid.sum()),'missing_pixels':int((~valid).sum()),
           'hole_boundary_pixels':int(holes.sum()),'surface_boundary_pixels':int(surfaces.sum()),
           'image_edge_pixels':int(image_edges.sum()),'image_edges_on_valid_depth':int(valid_edges.sum()),
           'valid_image_edges_near_holes':int((valid_edges&near_hole).sum()),
           'surface_edges_near_image_edges':int((surfaces&dilate(image_edges)).sum())}
    return holes,surfaces,image_edges,stats


def interior_mask(depth,radius):
    """Exclude missing-depth neighborhoods and image border; never add observations."""
    if (depth.ndim!=2 or not np.isfinite(depth).all() or np.any(depth<0)
        or type(radius) is not int or not 0<=radius<=8): raise ValueError('invalid_interior')
    valid=depth>0
    if radius==0: return valid.copy()
    core=valid&~dilate(~valid,radius)
    core[:radius]=False; core[-radius:]=False; core[:,:radius]=False; core[:,-radius:]=False
    return core


def residual_summary(distance):
    if distance.ndim!=1 or not np.isfinite(distance).all() or np.any(distance<0):
        raise ValueError('invalid_distance')
    if not len(distance): return {'count':0,'rmse_m':None,'median_m':None,'p90_m':None,'over_35mm':0,'squared_error_sum_m2':0.}
    return {'count':len(distance),'rmse_m':float(np.sqrt(np.mean(distance**2))),
            'median_m':float(np.median(distance)),'p90_m':float(np.quantile(distance,.9)),
            'over_35mm':int((distance>.035).sum()),'squared_error_sum_m2':float(np.sum(distance**2))}
