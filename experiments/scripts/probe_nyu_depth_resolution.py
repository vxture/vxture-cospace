"""Fixed real pair intervals and known-motion code quantization diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import open3d as o3d
from packages.data.nyu_rgbd import read_pnm,make_cloud
from packages.construction.nyu_depth_resolution import decode_codes,quantize_depth,quantize_points
from packages.construction.rgbd_diagnostics import residual_summary
from packages.construction.rgbd_multiscale import correspondences,grid_for
from packages.construction.rgbd_tracking import angle,CONFIG
from experiments.scripts.run_nyu_open3d import geometric_check,OPTIONS


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def bands(distance,target_depth):
    return [{'min_m':low,'max_m':min(high,10.),**residual_summary(distance[(target_depth>=low)&(target_depth<high)])}
            for low,high in [(0,2),(2,4),(4,6),(6,10.00001)]]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--adjacent',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    manifest=a.prepared/'input.json'; inputs=json.loads(manifest.read_bytes())
    baseline=json.loads(a.adjacent.read_bytes()); source=Path(inputs['source_snapshot'])
    raw_report=source/'report.json'; original=json.loads(raw_report.read_bytes())
    if (sha(raw_report)!=inputs['source_report_sha256'] or baseline['prepared_input_sha256']!=sha(manifest)
        or baseline['mode']!='color-only' or baseline['options']['hole_margin_px']!=0
        or baseline['common_geometry_config']!=CONFIG): raise ValueError('input_mismatch')
    cache={}
    def frame(index):
        if index in cache: return cache[index]
        f=inputs['frames'][index]; path=a.prepared/f['path']
        if sha(path)!=f['sha256']: raise ValueError('prepared_integrity')
        with np.load(path,allow_pickle=False) as arr: depth=arr['depth']; color=arr['color']
        rgbd=o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(color.copy()),
            o3d.geometry.Image(depth.copy()),depth_scale=1.,depth_trunc=10.,convert_rgb_to_intensity=True)
        images=[]
        for role in ['depth','rgb']:
            name=f['pair'][role]; raw=(source/'raw'/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=original['members'][name]['sha256']: raise ValueError('raw_integrity')
            images.append(read_pnm(raw,role=='depth'))
        cloud=make_cloud(*images,4); cache[index]=(rgbd,cloud)
        return cache[index]
    k=inputs['intrinsic']; intrinsic=o3d.camera.PinholeCameraIntrinsic(640,480,k['fx'],k['fy'],k['cx_zero_based'],k['cy_zero_based'])
    option=o3d.pipelines.odometry.OdometryOption(o3d.utility.IntVector(OPTIONS['iterations']),.03,0.,10.)
    jac=o3d.pipelines.odometry.RGBDOdometryJacobianFromColorTerm()
    anchors=[0,20,40,50,55]; gaps=[1,2,4]; pairs=[]
    for start in anchors:
        for gap in gaps:
            end=start+gap; target=frame(start); current=frame(end)
            def compute(src,dst):
                ok,t,_=o3d.pipelines.odometry.compute_rgbd_odometry(src[0],dst[0],intrinsic,np.eye(4),jac,option)
                result=geometric_check(src[1][0],dst[1][0],dst[1][2],t,bool(ok))
                _,s,d,dist=correspondences(src[1][0],dst[1][0],grid_for(dst[1][0],dst[1][2],4),4,t)
                result.update(matrix=t.tolist(),solver_success=bool(ok),bands=bands(dist,dst[1][0][d,2]),
                              source_points=len(src[1][0]),matched_count=len(s))
                return result
            forward=compute(current,target); reverse=compute(target,current)
            t=np.array(forward['matrix']); closure=t@np.array(reverse['matrix'])
            ct=float(np.linalg.norm(closure[:3,3])); cr=angle(closure[:3,:3])
            accepted=bool(forward['accepted'] and reverse['accepted'] and ct<=.02 and cr<=.02)
            # Compose only independently accepted adjacent edges, never across a rejection.
            chain=np.eye(4); available=True
            for edge in baseline['edges'][start:end]:
                if not edge['accepted']: available=False; break
                chain=chain@np.array(edge['T_previous_current'])
            difference=np.linalg.inv(chain)@t if available else None
            pairs.append({'start':start,'end':end,'gap':gap,
                'dt_us':inputs['frames'][end]['time_us']-inputs['frames'][start]['time_us'],
                'forward':forward,'reverse':reverse,'cycle_translation_m':ct,'cycle_rotation_rad':cr,
                'accepted':accepted,'accepted_adjacent_chain_available':available,
                'chain_matrix':chain.tolist() if available else None,
                'direct_vs_chain_translation_m':None if difference is None else float(np.linalg.norm(difference[:3,3])),
                'direct_vs_chain_rotation_rad':None if difference is None else angle(difference[:3,:3])})
            print(json.dumps({'pair':[start,end],'accepted':accepted}),flush=True)
    # Exact known correspondences, independent of nearest-neighbor matching/solver.
    rng=np.random.default_rng(20261028); base=rng.uniform(-1,1,(5000,3)); synthetic=[]; resolution=[]
    for center in [1.,2.,3.,4.,5.,6.,8.]:
        measured,code=quantize_depth(np.array([center])); z=decode_codes(code); next_z=decode_codes(code+1)
        resolution.append({'nominal_depth_m':center,'code':int(code[0]),'decoded_m':float(z[0]),
                           'next_code_step_m':float((next_z-z)[0]),'derivative_step_m':float((z*z/351.3)[0])})
        target=np.column_stack([base[:,0]*center*.3,base[:,1]*center*.2,center+base[:,2]*.15])
        for motion in [0.,.02,.05]:
            translation=np.array([0.,0.,motion]); src=target-translation
            clean=np.linalg.norm(src+translation-target,axis=1)
            measured_source=quantize_points(src); measured_target=quantize_points(target)
            correct=np.linalg.norm(measured_source+translation-measured_target,axis=1)
            biased=np.linalg.norm(measured_source+translation+np.array([.05,0.,0.])-measured_target,axis=1)
            synthetic.append({'center_depth_m':center,'motion_z_m':motion,'count':len(target),
                'clean_true_pose':residual_summary(clean),'quantized_true_pose':residual_summary(correct),
                'quantized_with_50mm_x_pose_bias':residual_summary(biased)})
    report={'schema_version':'cospace.nyu-resolution-probe/0.1','prepared_sha256':sha(manifest),
        'source_sha256':sha(raw_report),'adjacent_sha256':sha(a.adjacent),
        'input_paths':{'prepared':str(manifest),'source':str(raw_report),'adjacent':str(a.adjacent)},
        'options':{**OPTIONS,'jacobian':type(jac).__name__,'mode':'color-only','hole_margin_px':0},
        'common_geometry_config':CONFIG,'open3d_version':o3d.__version__,'python':sys.version,
        'anchors':anchors,'gaps':gaps,'pairs':pairs,'resolution':resolution,'synthetic':synthetic,
        'synthetic_seed':20261028,'algorithm_ready':False,'real_release_ready':False,'independent_accuracy_verified':False,
        'limitations':['code_resolution_is_not_a_calibrated_noise_sigma','synthetic_has_no_occlusion_or_sensor_noise',
            'synthetic_known_correspondence_differs_from_real_nearest_neighbor','direct_chain_consistency_is_not_independent_accuracy',
            'fixed_motion_limit_applied_to_all_intervals','no_trajectory_or_map_published'],
        'implementation_sha256':{f:sha(Path(f)) for f in ['experiments/scripts/probe_nyu_depth_resolution.py',
            'packages/construction/nyu_depth_resolution.py','packages/construction/rgbd_diagnostics.py',
            'packages/data/nyu_rgbd.py','packages/construction/rgbd_multiscale.py',
            'experiments/scripts/run_nyu_open3d.py','experiments/stack/rgbd-open3d/uv.lock']}}
    (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    html='''<!doctype html><meta charset="utf-8"><title>NYU 深度分辨率与帧间隔验证</title><style>body{max-width:1150px;margin:32px auto;padding:0 20px;background:#111827;color:#e2e8f0;font:14px system-ui}h1{font-size:24px}h2{font-size:18px}p{line-height:1.7;color:#94a3b8}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #334155;text-align:left}a{color:#7dd3fc}</style><h1>NYU办公室 · 深度分辨率与帧间隔验证</h1><p>固定仅光度目标和原始几何门槛；相隔1/2/4帧独立估计，不拼成轨迹。分辨率是编码尺度，不能称为已标定噪声或精度。</p><a href="report.json">原始指标、矩阵与来源</a><h2>真实序列：独立帧对</h2><table><tr><th>帧对</th><th>间隔ms</th><th>双向</th><th>前向RMSE mm</th><th>组合平移mm</th><th>与已接受邻边链的差mm</th></tr>'''
    for pair in pairs:
        f=pair['forward']; chain='不可用' if pair['direct_vs_chain_translation_m'] is None else f'{pair["direct_vs_chain_translation_m"]*1000:.2f}'
        html+=f'<tr><td>{pair["start"]}→{pair["end"]}</td><td>{pair["dt_us"]/1000:.1f}</td><td>{"通过" if pair["accepted"] else "拒绝"}</td><td>{f["rmse_m"]*1000:.2f}</td><td>{pair["cycle_translation_m"]*1000:.2f}</td><td>{chain}</td></tr>'
    html+='</table><h2>已知20mm轴向运动：编码量化影响</h2><p>固定5000个已知对应点；无噪声时真位姿残差接近零。下表加入深度整数编码量化；不含真实设备噪声、遮挡和配对错误。50mm横向位姿偏差用于检查诊断响应。</p><table><tr><th>名义距离m</th><th>正确位姿量化后RMSE mm</th><th>额外50mm位姿偏差后RMSE mm</th></tr>'
    for s in synthetic:
        if s['motion_z_m']!=.02: continue
        html+=f'<tr><td>{s["center_depth_m"]:.0f}</td><td>{s["quantized_true_pose"]["rmse_m"]*1000:.2f}</td><td>{s["quantized_with_50mm_x_pose_bias"]["rmse_m"]*1000:.2f}</td></tr>'
    html+='</table><h2>整数编码的精确相邻步长</h2><table><tr><th>名义距离m</th><th>实际解码距离m</th><th>相邻码步长mm</th></tr>'
    for row in resolution:
        html+=f'<tr><td>{row["nominal_depth_m"]:.0f}</td><td>{row["decoded_m"]:.4f}</td><td>{row["next_code_step_m"]*1000:.2f}</td></tr>'
    html+='</table><p>无独立真实位姿参考；仅凭内部一致性和量化试验不能认定真实断点根因，也不能据此放宽35mm门槛或放行融合。</p>'
    (a.output/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps({'pairs':len(pairs),'accepted_pairs':sum(x['accepted'] for x in pairs),'synthetic_cases':len(synthetic)}))


if __name__=='__main__': main()
