"""Experimental projective point-to-point ICP; local diagnostic, not SLAM."""
import numpy as np
from packages.data.nyu_rgbd import DEPTH_K, DEPTH_D, distort

CONFIG={'iterations':40,'max_distance_m':.12,'min_matches':300,'min_overlap':.30,
        'max_rmse_m':.035,'max_translation_m':.15,'max_rotation_rad':.15,
        'convergence_m':1e-5,'convergence_rad':1e-5,'min_geometry_ratio':.01}


def transform(points,matrix):
    return points@matrix[:3,:3].T+matrix[:3,3]


def rigid_fit(source,target):
    if source.shape!=target.shape or source.ndim!=2 or source.shape[1]!=3 or len(source)<3:
        raise ValueError('correspondence_shape')
    if not np.isfinite(source).all() or not np.isfinite(target).all(): raise ValueError('non_finite_points')
    a=source.mean(axis=0); b=target.mean(axis=0)
    u,s,vh=np.linalg.svd((source-a).T@(target-b))
    if s[1]<1e-12: raise ValueError('degenerate_correspondences')
    correction=np.eye(3); correction[2,2]=np.linalg.det(vh.T@u.T)
    rotation=vh.T@correction@u.T
    matrix=np.eye(4); matrix[:3,:3]=rotation; matrix[:3,3]=b-rotation@a
    return matrix


def angle(rotation):
    return float(np.arccos(np.clip((np.trace(rotation)-1)/2,-1,1)))


def register_pair(source,target,target_pixels,stride=4,config=None):
    cfg={**CONFIG,**(config or {})}
    if (source.ndim!=2 or target.ndim!=2 or source.shape[1:]!=(3,) or target.shape[1:]!=(3,)
        or target_pixels.shape!=(len(target),2) or not np.isfinite(source).all() or not np.isfinite(target).all()):
        raise ValueError('invalid_cloud')
    if type(stride) is not int or not 1<=stride<=32: raise ValueError('invalid_stride')
    if (not np.issubdtype(target_pixels.dtype,np.integer) or np.any(target_pixels<0)
        or np.any(target_pixels[:,0]>=640) or np.any(target_pixels[:,1]>=480)
        or np.any(target_pixels%stride) or len(np.unique(target_pixels,axis=0))!=len(target_pixels)):
        raise ValueError('invalid_target_pixels')
    grid=np.full(((480+stride-1)//stride,(640+stride-1)//stride),-1,dtype=int)
    grid[target_pixels[:,1]//stride,target_pixels[:,0]//stride]=np.arange(len(target))
    def matches(matrix):
        moved=transform(source,matrix)
        safe=moved[:,2]>0
        x,y=distort(moved[:,0]/np.maximum(moved[:,2],1e-9),moved[:,1]/np.maximum(moved[:,2],1e-9),DEPTH_D)
        # Bound before integer conversion; only front-facing points are eligible.
        cx=np.rint(np.clip((x*DEPTH_K[0]+DEPTH_K[2]-1)/stride,-1000,1000)).astype(int)
        cy=np.rint(np.clip((y*DEPTH_K[1]+DEPTH_K[3]-1)/stride,-1000,1000)).astype(int)
        best=np.full(len(source),np.inf); ids=np.full(len(source),-1,dtype=int)
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                xx,yy=cx+dx,cy+dy
                inside=safe&(xx>=0)&(xx<grid.shape[1])&(yy>=0)&(yy<grid.shape[0])
                rows=np.flatnonzero(inside); lookup=grid[yy[rows],xx[rows]]
                rows,lookup=rows[lookup>=0],lookup[lookup>=0]
                distance=np.linalg.norm(moved[rows]-target[lookup],axis=1)
                better=distance<best[rows]
                ids[rows[better]]=lookup[better]; best[rows[better]]=distance[better]
        selected=np.flatnonzero(best<cfg['max_distance_m'])
        # A target sample contributes at most once; avoid inflated overlap via many-to-one matching.
        selected=selected[np.argsort(best[selected],kind='stable')]
        _,first=np.unique(ids[selected],return_index=True)
        selected=selected[first]
        return moved,selected,ids[selected],best[selected]
    matrix=np.eye(4); converged=False; reasons=[]; iterations=0
    for iteration in range(cfg['iterations']):
        iterations=iteration+1
        moved,src,dst,dist=matches(matrix)
        if len(src)<cfg['min_matches']: reasons.append('insufficient_matches'); break
        # Trim the worst 20% of geometric pairs; final diagnostics use all gated unique pairs.
        keep=dist<=np.quantile(dist,.8)
        try: update=rigid_fit(moved[src[keep]],target[dst[keep]])
        except ValueError: reasons.append('degenerate_correspondences'); break
        matrix=update@matrix
        if np.linalg.norm(update[:3,3])<cfg['convergence_m'] and angle(update[:3,:3])<cfg['convergence_rad']:
            converged=True; break
    moved,src,dst,dist=matches(matrix)
    overlap=len(src)/len(source) if len(source) else 0
    rmse=float(np.sqrt(np.mean(dist**2))) if len(dist) else None
    geometry_ratio=0.
    if len(src)>=3:
        s=np.linalg.svd(target[dst]-target[dst].mean(axis=0),compute_uv=False)
        geometry_ratio=float(s[-1]/s[0]) if s[0] else 0.
    if len(src)<cfg['min_matches']: reasons.append('insufficient_matches')
    if not converged: reasons.append('not_converged')
    if overlap<cfg['min_overlap']: reasons.append('low_overlap')
    if rmse is None or rmse>cfg['max_rmse_m']: reasons.append('high_residual')
    if geometry_ratio<cfg['min_geometry_ratio']: reasons.append('weak_3d_geometry')
    if np.linalg.norm(matrix[:3,3])>cfg['max_translation_m'] or angle(matrix[:3,:3])>cfg['max_rotation_rad']:
        reasons.append('motion_limit')
    return {'accepted':not reasons,'reasons':sorted(set(reasons)),
            'T_previous_current':matrix.tolist(),'matched_points':len(src),'overlap':overlap,
            'rmse_m':rmse,'geometry_ratio':geometry_ratio,'iterations':iterations,'converged':converged,
            'independent_accuracy_verified':False,'algorithm_ready':False}
