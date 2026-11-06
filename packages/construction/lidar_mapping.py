"""Bounded laser-only scan-to-scan ICP. Local odometry, no loop closure or IMU."""
import numpy as np
from scipy.spatial import cKDTree
from packages.construction.rgbd_tracking import rigid_fit, transform, angle

METHOD='laser_scan_to_scan_icp'
CONFIG={'levels':[[.4,1.],[.2,.5],[.1,.25]],'iterations':40,'min_matches':100,
        'min_overlap':.4,'max_rmse_m':.20,'max_translation_m':.75,'max_rotation_rad':.35,
        'cycle_translation_m':.08,'cycle_rotation_rad':.08,'convergence':1e-5}


def downsample(points, size):
    _,ids=np.unique(np.floor(points/size).astype(np.int64),axis=0,return_index=True)
    return points[ids].astype(float)


def solve(source,target):
    pose=np.eye(4);iterations=0
    for voxel,distance in CONFIG['levels']:
        src=downsample(source,voxel);dst=downsample(target,voxel);tree=cKDTree(dst)
        for _ in range(CONFIG['iterations']):
            moved=transform(src,pose);d,ids=tree.query(moved,distance_upper_bound=distance,workers=1)
            mask=np.isfinite(d)
            if mask.sum()<CONFIG['min_matches']:break
            # Trim the largest residuals, retaining actual point correspondences.
            mask &= d<=np.quantile(d[mask],.9)
            try:step=rigid_fit(moved[mask],dst[ids[mask]])
            except ValueError:break
            pose=step@pose;iterations+=1
            if np.linalg.norm(step[:3,3])<CONFIG['convergence'] and angle(step[:3,:3])<CONFIG['convergence']:break
    src=downsample(source,.1);dst=downsample(target,.1)
    d,_=cKDTree(dst).query(transform(src,pose),distance_upper_bound=.25,workers=1)
    valid=np.isfinite(d);matches=int(valid.sum());overlap=matches/len(src)
    rmse=float(np.sqrt(np.mean(d[valid]**2))) if matches else None
    reasons=[]
    if matches<CONFIG['min_matches']:reasons.append('insufficient_matches')
    if overlap<CONFIG['min_overlap']:reasons.append('low_overlap')
    if rmse is None or rmse>CONFIG['max_rmse_m']:reasons.append('high_residual')
    if np.linalg.norm(pose[:3,3])>CONFIG['max_translation_m'] or angle(pose[:3,:3])>CONFIG['max_rotation_rad']:reasons.append('motion_limit')
    if matches>=3:
        s=np.linalg.svd(transform(src[valid],pose)-transform(src[valid],pose).mean(axis=0),compute_uv=False)
        if s[1]/max(s[0],1e-12)<.01:reasons.append('degenerate_geometry')
    return {'T_previous_current':pose.tolist(),'matched_points':matches,'overlap':overlap,
            'rmse_m':rmse,'iterations':iterations,'reasons':reasons}


def register_pair(source,target):
    for p in (source,target):
        if p.ndim!=2 or p.shape[1]!=3 or len(p)<CONFIG['min_matches'] or not np.isfinite(p).all():
            raise ValueError('lidar_registration_cloud_invalid')
    forward=solve(source,target);reverse=solve(target,source)
    cycle=np.array(forward['T_previous_current'])@np.array(reverse['T_previous_current'])
    ct=float(np.linalg.norm(cycle[:3,3]));cr=angle(cycle[:3,:3])
    reasons=list(forward['reasons'])
    if reverse['reasons']:reasons.append('reverse_registration_rejected')
    if ct>CONFIG['cycle_translation_m'] or cr>CONFIG['cycle_rotation_rad']:reasons.append('bidirectional_inconsistent')
    return {**forward,'accepted':not reasons,'reasons':reasons,'reverse':reverse,
            'cycle_translation_m':ct,'cycle_rotation_rad':cr}
