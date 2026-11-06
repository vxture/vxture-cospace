"""Independent multiscale point-to-plane research adapter using existing NumPy."""
import numpy as np
from packages.data.nyu_rgbd import DEPTH_K,DEPTH_D,distort
from packages.construction.rgbd_tracking import CONFIG,transform,angle

MULTISCALE={'strides':[16,8,4],'iterations':[20,20,30], 'huber_m':.015,
            'normal_neighbor_distance_m':.15,'normal_min_cross_m2':1e-5,
            'min_normal_matches':100,'min_hessian_ratio':1e-7,
            'max_update_translation_m':.05,'max_update_rotation_rad':.05}


def skew(v):
    x,y,z=v
    return np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])


def increment(twist):
    """Left Rodrigues rotation and independent small translation, not full SE3 exponential."""
    matrix=np.eye(4); omega=twist[:3]; theta=np.linalg.norm(omega); k=skew(omega)
    matrix[:3,:3]=np.eye(3)+k+(k@k)*.5 if theta<1e-8 else np.eye(3)+np.sin(theta)/theta*k+(1-np.cos(theta))/theta**2*(k@k)
    matrix[:3,3]=twist[3:]
    return matrix


def grid_for(points,pixels,stride):
    if points.shape!=(len(points),3) or pixels.shape!=(len(points),2) or not np.isfinite(points).all():
        raise ValueError('invalid_cloud')
    if type(stride) is not int or not 1<=stride<=32: raise ValueError('invalid_stride')
    if (not np.issubdtype(pixels.dtype,np.integer) or np.any(pixels<0) or np.any(pixels[:,0]>=640)
        or np.any(pixels[:,1]>=480) or np.any(pixels%stride) or len(np.unique(pixels,axis=0))!=len(pixels)):
        raise ValueError('invalid_pixels')
    grid=np.full(((480+stride-1)//stride,(640+stride-1)//stride),-1,dtype=int)
    grid[pixels[:,1]//stride,pixels[:,0]//stride]=np.arange(len(points))
    return grid


def surface_normals(points,pixels,stride):
    grid=grid_for(points,pixels,stride); normals=np.zeros_like(points); valid=np.zeros(len(points),dtype=bool)
    if not len(points): return normals,valid
    x=pixels[:,0]//stride; y=pixels[:,1]//stride
    inside=(x>0)&(x<grid.shape[1]-1)&(y>0)&(y<grid.shape[0]-1)
    rows=np.flatnonzero(inside)
    neighbors=np.stack([grid[y[rows],x[rows]-1],grid[y[rows],x[rows]+1],
                        grid[y[rows]-1,x[rows]],grid[y[rows]+1,x[rows]]],axis=1)
    good=np.all(neighbors>=0,axis=1); rows=rows[good]; neighbors=neighbors[good]
    if not len(rows): return normals,valid
    close=np.all(np.linalg.norm(points[neighbors]-points[rows,None,:],axis=2)<MULTISCALE['normal_neighbor_distance_m'],axis=1)
    rows=rows[close]; neighbors=neighbors[close]
    cross=np.cross(points[neighbors[:,1]]-points[neighbors[:,0]],points[neighbors[:,3]]-points[neighbors[:,2]])
    length=np.linalg.norm(cross,axis=1); good=length>MULTISCALE['normal_min_cross_m2']
    normals[rows[good]]=cross[good]/length[good,None]; valid[rows[good]]=True
    return normals,valid


def correspondences(source,target,grid,stride,matrix):
    moved=transform(source,matrix)
    safe=moved[:,2]>0
    x,y=distort(moved[:,0]/np.maximum(moved[:,2],1e-9),moved[:,1]/np.maximum(moved[:,2],1e-9),DEPTH_D)
    cx=np.rint(np.clip((x*DEPTH_K[0]+DEPTH_K[2]-1)/stride,-1000,1000)).astype(int)
    cy=np.rint(np.clip((y*DEPTH_K[1]+DEPTH_K[3]-1)/stride,-1000,1000)).astype(int)
    best=np.full(len(source),np.inf); ids=np.full(len(source),-1,dtype=int)
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            xx,yy=cx+dx,cy+dy
            rows=np.flatnonzero(safe&(xx>=0)&(xx<grid.shape[1])&(yy>=0)&(yy<grid.shape[0]))
            lookup=grid[yy[rows],xx[rows]]; good=lookup>=0; rows=rows[good]; lookup=lookup[good]
            distance=np.linalg.norm(moved[rows]-target[lookup],axis=1); better=distance<best[rows]
            best[rows[better]]=distance[better]; ids[rows[better]]=lookup[better]
    rows=np.flatnonzero(best<CONFIG['max_distance_m']); rows=rows[np.argsort(best[rows],kind='stable')]
    _,first=np.unique(ids[rows],return_index=True); rows=rows[first]
    return moved,rows,ids[rows],best[rows]


def solve_plane_step(points,targets,normals):
    if points.shape!=targets.shape or points.shape!=normals.shape or points.ndim!=2 or points.shape[1]!=3:
        raise ValueError('plane_shape')
    if not all(np.isfinite(a).all() for a in (points,targets,normals)): raise ValueError('plane_nonfinite')
    residual=np.einsum('ij,ij->i',normals,points-targets)
    jacobian=np.column_stack([np.cross(points,normals),normals])
    weights=np.minimum(1.,MULTISCALE['huber_m']/np.maximum(np.abs(residual),1e-12))
    h=jacobian.T@(weights[:,None]*jacobian); eigenvalues=np.linalg.eigvalsh(h)
    ratio=float(max(0.,eigenvalues[0])/max(eigenvalues[-1],1e-12))
    if ratio<MULTISCALE['min_hessian_ratio']: raise ValueError('weak_plane_constraints')
    step=np.linalg.solve(h,-jacobian.T@(weights*residual))
    return step,ratio,float(np.sqrt(np.mean(residual**2)))


def register_multiscale(source_levels,target_levels):
    matrix=np.eye(4); levels=[]; final_converged=False; reasons=[]
    for stride,limit in zip(MULTISCALE['strides'],MULTISCALE['iterations']):
        source,pixels=source_levels[stride]; target,target_pixels=target_levels[stride]
        grid_for(source,pixels,stride); grid=grid_for(target,target_pixels,stride)
        normals,normal_valid=surface_normals(target,target_pixels,stride)
        info={'stride':stride,'iterations':0,'normal_points':int(normal_valid.sum()),'converged':False,'failure':None}
        for iteration in range(limit):
            info['iterations']=iteration+1
            moved,src,dst,dist=correspondences(source,target,grid,stride,matrix)
            ok=normal_valid[dst]; src=src[ok]; dst=dst[ok]
            info['normal_matches']=len(src)
            if len(src)<MULTISCALE['min_normal_matches']:
                info['failure']='insufficient_normal_matches'; break
            try: step,ratio,plane_rmse=solve_plane_step(moved[src],target[dst],normals[dst])
            except ValueError as error: info['failure']=str(error); break
            info.update(hessian_ratio=ratio,plane_rmse_m=plane_rmse)
            if np.linalg.norm(step[:3])>MULTISCALE['max_update_rotation_rad'] or np.linalg.norm(step[3:])>MULTISCALE['max_update_translation_m']:
                info['failure']='unstable_update'; break
            matrix=increment(step)@matrix
            if np.linalg.norm(step[:3])<CONFIG['convergence_rad'] and np.linalg.norm(step[3:])<CONFIG['convergence_m']:
                info['converged']=True; break
        levels.append(info)
        if stride==4:
            final_converged=info['converged']
            if info['failure']: reasons.append(info['failure'])
    source,_=source_levels[4]; target,pixels=target_levels[4]; grid=grid_for(target,pixels,4)
    moved,src,dst,dist=correspondences(source,target,grid,4,matrix)
    rmse=float(np.sqrt(np.mean(dist**2))) if len(dist) else None
    overlap=len(src)/len(source) if len(source) else 0.
    ratio=0.
    if len(src)>=3:
        s=np.linalg.svd(target[dst]-target[dst].mean(axis=0),compute_uv=False); ratio=float(s[-1]/s[0]) if s[0] else 0.
    if not final_converged: reasons.append('not_converged')
    if len(src)<CONFIG['min_matches']: reasons.append('insufficient_matches')
    if overlap<CONFIG['min_overlap']: reasons.append('low_overlap')
    if rmse is None or rmse>CONFIG['max_rmse_m']: reasons.append('high_residual')
    if ratio<CONFIG['min_geometry_ratio']: reasons.append('weak_3d_geometry')
    if np.linalg.norm(matrix[:3,3])>CONFIG['max_translation_m'] or angle(matrix[:3,:3])>CONFIG['max_rotation_rad']: reasons.append('motion_limit')
    return {'accepted':not reasons,'reasons':sorted(set(reasons)),'T_previous_current':matrix.tolist(),
            'matched_points':len(src),'overlap':overlap,'rmse_m':rmse,'geometry_ratio':ratio,
            'converged':final_converged,'levels':levels,'algorithm_ready':False,'independent_accuracy_verified':False}
