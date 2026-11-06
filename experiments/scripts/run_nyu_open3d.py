"""Actual Open3D hybrid RGB-D odometry, isolated runtime, fixed input and gates."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np
import open3d as o3d
from packages.data.nyu_rgbd import read_pnm,make_cloud,ply_bytes
from packages.construction.rgbd_multiscale import correspondences,grid_for
from packages.construction.rgbd_tracking import CONFIG,angle,transform
from packages.construction.rgbd_diagnostics import interior_mask

OPTIONS={'iterations':[20,10,5],'depth_diff_max_m':.03,'depth_min_m':0.,'depth_max_m':10.,
         'depth_scale':1.,'jacobian':'RGBDOdometryJacobianFromHybridTerm',
         'cycle_translation_m':.02,'cycle_rotation_rad':.02}


def geometric_check(source,target,pixels,matrix,solver_ok):
    reasons=[]
    proper=(matrix.shape==(4,4) and np.isfinite(matrix).all() and np.allclose(matrix[3],[0,0,0,1])
            and np.allclose(matrix[:3,:3].T@matrix[:3,:3],np.eye(3),atol=1e-6)
            and abs(np.linalg.det(matrix[:3,:3])-1)<1e-6)
    if not proper:
        return {'accepted':False,'reasons':['invalid_transform'],'rmse_m':None,'matched_points':0,'overlap':0.,'geometry_ratio':0.}
    _,src,dst,distance=correspondences(source,target,grid_for(target,pixels,4),4,matrix)
    rmse=float(np.sqrt(np.mean(distance**2))) if len(distance) else None
    overlap=len(src)/len(source) if len(source) else 0.; ratio=0.
    if len(src)>=3:
        s=np.linalg.svd(target[dst]-target[dst].mean(axis=0),compute_uv=False); ratio=float(s[-1]/s[0]) if s[0] else 0.
    if not solver_ok: reasons.append('library_solver_failed')
    if len(src)<CONFIG['min_matches']: reasons.append('insufficient_matches')
    if overlap<CONFIG['min_overlap']: reasons.append('low_overlap')
    if rmse is None or rmse>CONFIG['max_rmse_m']: reasons.append('high_residual')
    if ratio<CONFIG['min_geometry_ratio']: reasons.append('weak_3d_geometry')
    if np.linalg.norm(matrix[:3,3])>CONFIG['max_translation_m'] or angle(matrix[:3,:3])>CONFIG['max_rotation_rad']: reasons.append('motion_limit')
    return {'accepted':not reasons,'reasons':reasons,'rmse_m':rmse,'matched_points':len(src),'overlap':overlap,'geometry_ratio':ratio}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('prepared',type=Path)
    parser.add_argument('--baseline',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=['hybrid','constant-color','color-only'],default='hybrid')
    parser.add_argument('--hole-margin',type=int,choices=[0,4],default=0)
    args=parser.parse_args(); root=args.output; root.mkdir(parents=True,exist_ok=False)
    input_raw=(args.prepared/'input.json').read_bytes(); inputs=json.loads(input_raw)
    source_root=Path(inputs['source_snapshot']); source_raw=(source_root/'report.json').read_bytes(); source=json.loads(source_raw)
    if hashlib.sha256(source_raw).hexdigest()!=inputs['source_report_sha256']: raise ValueError('source_report_integrity')
    baseline_raw=args.baseline.read_bytes(); baseline=json.loads(baseline_raw)
    if baseline['source_report_sha256']!=inputs['source_report_sha256'] or baseline['config']!=CONFIG: raise ValueError('baseline_mismatch')
    k=inputs['intrinsic']; intrinsic=o3d.camera.PinholeCameraIntrinsic(k['width'],k['height'],k['fx'],k['fy'],k['cx_zero_based'],k['cy_zero_based'])
    option=o3d.pipelines.odometry.OdometryOption(o3d.utility.IntVector(OPTIONS['iterations']),
        OPTIONS['depth_diff_max_m'],OPTIONS['depth_min_m'],OPTIONS['depth_max_m'])
    jacobian=(o3d.pipelines.odometry.RGBDOdometryJacobianFromColorTerm() if args.mode=='color-only'
              else o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm())
    input_masks=[]
    def load(frame):
        path=args.prepared/frame['path']; raw=path.read_bytes()
        if len(raw)!=frame['bytes'] or hashlib.sha256(raw).hexdigest()!=frame['sha256']: raise ValueError('prepared_integrity')
        with np.load(path,allow_pickle=False) as arrays: depth=arrays['depth']; color=arrays['color']
        if depth.shape!=(480,640) or depth.dtype!=np.float32 or color.shape!=(480,640,3) or color.dtype!=np.uint8:
            raise ValueError('prepared_profile')
        if not np.isfinite(depth).all() or np.any(depth<0) or np.any(depth>10): raise ValueError('prepared_depth')
        core=interior_mask(depth,args.hole_margin)
        input_masks.append({'frame':frame['index'],'original_valid_pixels':int((depth>0).sum()),
                            'retained_pixels':int(core.sum()),
                            'mask_sha256':hashlib.sha256(core.tobytes()).hexdigest()})
        # Keep color unchanged: this removes depth associations near holes, without
        # painting new black boundaries. Open3D's internal pyramids still matter.
        depth=np.where(core,depth,0).astype(np.float32)
        if args.mode=='constant-color': color=np.full_like(color,128)
        rgbd=o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(np.ascontiguousarray(color)),
            o3d.geometry.Image(np.ascontiguousarray(depth)),depth_scale=1.,depth_trunc=10.,convert_rgb_to_intensity=True)
        original=[]
        for role in ('depth','rgb'):
            name=frame['pair'][role]; raw=(source_root/'raw'/name).read_bytes(); m=source['members'][name]
            if len(raw)!=m['bytes'] or hashlib.sha256(raw).hexdigest()!=m['sha256']: raise ValueError('snapshot_integrity')
            original.append(read_pnm(raw,role=='depth'))
        cloud=make_cloud(*original,4)
        return rgbd,cloud
    frames=inputs['frames']
    if len(frames)-1!=len(baseline['edges']): raise ValueError('baseline_edge_count')
    previous=load(frames[0]); edges=[]; poses=[np.eye(4).tolist()]; prefix=True
    first_cloud=previous[1]; cloud_points=[first_cloud[0]]; colors=[first_cloud[1]]; color_valid=[first_cloud[3]]
    begin=time.perf_counter()
    for i,frame in enumerate(frames[1:],1):
        current=load(frame); start=time.perf_counter()
        def compute(a,b):
            success,matrix,info=o3d.pipelines.odometry.compute_rgbd_odometry(a[0],b[0],intrinsic,np.eye(4),jacobian,option)
            result=geometric_check(a[1][0],b[1][0],b[1][2],matrix,bool(success))
            result.update(library_solver_success=bool(success),T_previous_current=matrix.tolist(),
                          information_matrix_eigenvalues=np.linalg.eigvalsh(info).tolist())
            return result
        forward=compute(current,previous); reverse=compute(previous,current)
        closure=np.array(forward['T_previous_current'])@np.array(reverse['T_previous_current'])
        ct=float(np.linalg.norm(closure[:3,3])); cr=angle(closure[:3,:3]); common=forward['accepted']
        if not reverse['accepted']: forward['reasons'].append('reverse_registration_rejected')
        if ct>OPTIONS['cycle_translation_m'] or cr>OPTIONS['cycle_rotation_rad']: forward['reasons'].append('bidirectional_inconsistent')
        forward.update(accepted=not forward['reasons'],common_gate_accepted=common,reverse=reverse,
                       cycle_translation_m=ct,cycle_rotation_rad=cr,previous_frame=i-1,current_frame=i,
                       wall_seconds=time.perf_counter()-start)
        edges.append(forward)
        if prefix and forward['accepted']:
            pose=np.array(poses[-1])@np.array(forward['T_previous_current']); poses.append(pose.tolist())
            # Preserve every accepted frame, including the one before a rejection.
            cloud_points.append(transform(current[1][0],pose)); colors.append(current[1][1]); color_valid.append(current[1][3])
        else: prefix=False
        previous=current
        if i%10==0: print(json.dumps({'evaluated_edges':i,'accepted_prefix_frames':len(poses)}),flush=True)
    reasons={}
    for edge in edges:
        for reason in edge['reasons']: reasons[reason]=reasons.get(reason,0)+1
    report={'schema_version':'cospace.open3d-rgbd-experiment/0.1','mode':args.mode,'open3d_version':o3d.__version__,
            'python':sys.version,'platform':platform.platform(),
            'options':{**OPTIONS,'jacobian':type(jacobian).__name__,'hole_margin_px':args.hole_margin},
            'input_masks':input_masks,'common_geometry_config':CONFIG,
            'source_report_sha256':inputs['source_report_sha256'],'prepared_input_sha256':hashlib.sha256(input_raw).hexdigest(),
            'baseline_sha256':hashlib.sha256(baseline_raw).hexdigest(),'baseline':baseline['candidate'],
            'result':{'frames':len(frames),'common_gate_accepted_edges':sum(e['common_gate_accepted'] for e in edges),
                      'bidirectional_accepted_edges':sum(e['accepted'] for e in edges),'prefix_frames':len(poses),
                      'completed':len(poses)==len(frames),'rejection_reasons':reasons},
            'edges':edges,'prefix_T_anchor_camera':poses,'wall_seconds':time.perf_counter()-begin,
            'dependencies':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
            'algorithm_ready':False,'real_release_ready':False,'independent_accuracy_verified':False,
            'limitations':['no_independent_trajectory_reference','no_loop_closure_or_pose_graph',
                          'color_registration_not_independently_verified','no_surface_fusion_or_occupancy'],
            'implementation_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                ('experiments/scripts/run_nyu_open3d.py','packages/data/nyu_rgbd.py','packages/construction/rgbd_multiscale.py',
                 'packages/construction/rgbd_tracking.py','packages/construction/rgbd_diagnostics.py',
                 'experiments/stack/rgbd-open3d/uv.lock')}}
    cloud=ply_bytes(np.concatenate(cloud_points),np.concatenate(colors),np.concatenate(color_valid)).replace(b'frame depth_optical',b'frame first_depth_camera_anchor')
    (root/'accepted-prefix.ply').write_bytes(cloud); report['cloud_sha256']=hashlib.sha256(cloud).hexdigest()
    (root/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    from html import escape
    rows=[]
    for old,new in zip(baseline['edges'],edges):
        fmt=lambda n:'—' if n is None else f'{n*1000:.2f}'
        rows.append(f'<tr><td>{new["previous_frame"]}→{new["current_frame"]}</td><td>{"通过" if old["accepted"] else "拒绝"}</td><td>{fmt(old["rmse_m"])}</td><td>{"通过" if new["accepted"] else "拒绝"}</td><td>{fmt(new["rmse_m"])}</td><td>{fmt(new["cycle_translation_m"])}</td><td>{escape(", ".join(new["reasons"])) or "—"}</td></tr>')
    html='''<!doctype html><meta charset="utf-8"><title>NYU Open3D混合里程计</title><style>body{margin:32px auto;max-width:1100px;font:14px system-ui;background:#111827;color:#e2e8f0}section{padding:20px;background:#1e293b;border-radius:10px;margin:20px 0}a{color:#7dd3fc}td,th{padding:9px;border-bottom:1px solid #334155;text-align:left}table{width:100%;border-collapse:collapse}p{color:#94a3b8}</style><h2>NYU办公室 · Open3D 混合RGB-D里程计</h2>'''
    r=report['result']; html+=f'<section>Open3D {o3d.__version__} · {escape(args.mode)} · 独立Python3.12 · 60帧<br>共同几何判据：{r["common_gate_accepted_edges"]}/59；双向判据：{r["bidirectional_accepted_edges"]}/59；连续前缀：{r["prefix_frames"]}帧。</section>'
    html+='<p>前版：多尺度纯深度。本轮模式见上方；constant-color 为固定非零颜色的混合目标消融，color-only 仍以深度作投影关联。最终几何与双向阈值不变；内部优化目标不同。残差/双向平移单位mm，均非独立绝对精度。</p><a href="comparison.json">参数与全部诊断</a> · <a href="accepted-prefix.ply">已接受前缀累积点云</a><p>只累计首个断点之前的位姿。未做表面融合、回环或生产发布。</p><table><tr><th>帧</th><th>前版双向</th><th>前版残差</th><th>本轮双向</th><th>本轮残差</th><th>本轮双向平移</th><th>拒绝原因</th></tr>'+''.join(rows)+'</table>'
    (root/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps({'result':r,'wall_seconds':report['wall_seconds']}))


if __name__=='__main__': main()
