"""Fixed-pose spatial residual attribution; never overrides the full-cloud gate."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import numpy as np
from PIL import Image
from packages.data.nyu_rgbd import read_pnm,make_cloud,DEPTH_K
from packages.construction.rgbd_multiscale import correspondences,grid_for,surface_normals
from packages.construction.rgbd_diagnostics import interior_mask,residual_summary


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def pinhole_pixels(points):
    u=np.rint(points[:,0]/points[:,2]*DEPTH_K[0]+DEPTH_K[2]-1).astype(int)
    v=np.rint(points[:,1]/points[:,2]*DEPTH_K[1]+DEPTH_K[3]-1).astype(int)
    valid=(u>=0)&(u<640)&(v>=0)&(v<480)
    return np.clip(u,0,639),np.clip(v,0,479),valid


def main():
    p=argparse.ArgumentParser(); p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--original',type=Path,required=True); p.add_argument('--interior',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    manifest=a.prepared/'input.json'; inputs=json.loads(manifest.read_bytes())
    source=Path(inputs['source_snapshot']); raw_report=source/'report.json'; src_report=json.loads(raw_report.read_bytes())
    if sha(raw_report)!=inputs['source_report_sha256']: raise ValueError('source_integrity')
    reports={mode:json.loads((root/'comparison.json').read_bytes()) for mode,root in [('original',a.original),('interior',a.interior)]}
    if any(r['prepared_input_sha256']!=sha(manifest) for r in reports.values()): raise ValueError('prepared_mismatch')
    if reports['original']['implementation_sha256']!=reports['interior']['implementation_sha256']:
        raise ValueError('runner_mismatch')
    cache={}
    def frame(i):
        if i in cache: return cache[i]
        f=inputs['frames'][i]; path=a.prepared/f['path']
        if sha(path)!=f['sha256']: raise ValueError('prepared_integrity')
        with np.load(path,allow_pickle=False) as arr: depth=arr['depth']; color=arr['color']
        images=[]
        for role in ['depth','rgb']:
            name=f['pair'][role]; raw=(source/'raw'/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=src_report['members'][name]['sha256']: raise ValueError('raw_integrity')
            images.append(read_pnm(raw,role=='depth'))
        cloud=make_cloud(*images,4); cache[i]=(cloud,interior_mask(depth,4),color)
        return cache[i]
    entries=[]; html_rows=[]; selected=[0,5,30,55,56,57,58]
    for mode,report in reports.items():
        for edge_i in selected:
            edge=report['edges'][edge_i]
            for direction in ['forward','reverse']:
                si,ti=(edge_i+1,edge_i) if direction=='forward' else (edge_i,edge_i+1)
                source_cloud,source_core,_=frame(si); target_cloud,target_core,color=frame(ti)
                points,_,_,_,_=source_cloud; target,_,pixels,_,_=target_cloud
                item=edge if direction=='forward' else edge['reverse']
                matrix=np.array(item['T_previous_current'])
                moved,src,dst,distance=correspondences(points,target,grid_for(target,pixels,4),4,matrix)
                full=residual_summary(distance)
                if not np.isclose(full['rmse_m'],item['rmse_m'],rtol=1e-10,atol=1e-12):
                    raise ValueError('residual_reproduction')
                su,sv,sinside=pinhole_pixels(points); tu,tv,tinside=pinhole_pixels(target)
                both_core=(sinside[src]&tinside[dst]&source_core[sv[src],su[src]]&target_core[tv[dst],tu[dst]])
                core=residual_summary(distance[both_core]); boundary=residual_summary(distance[~both_core])
                normal,nvalid=surface_normals(target,pixels,4)
                good=nvalid[dst]; delta=moved[src]-target[dst]
                plane=residual_summary(np.abs(np.einsum('ij,ij->i',delta[good],normal[dst[good]])))
                z=residual_summary(np.abs(delta[:,2]))
                bins=[]
                for y in range(3):
                    for x in range(4):
                        pick=(pixels[dst,0]//160==x)&(pixels[dst,1]//160==y)
                        bins.append({'column':x,'row':y,**residual_summary(distance[pick])})
                depth_bands=[]
                for low,high in [(0,2),(2,4),(4,6),(6,10.00001)]:
                    pick=(target[dst,2]>=low)&(target[dst,2]<high)
                    depths=target[dst[pick],2]
                    depth_bands.append({'depth_min_m':low,'depth_max_m':min(high,10.),
                        'target_depth_median_m':None if not len(depths) else float(np.median(depths)),
                        'nominal_one_code_step_median_m':None if not len(depths) else float(np.median(depths**2/351.3)),
                        **residual_summary(distance[pick])})
                entry={'mode':mode,'edge':edge_i,'direction':direction,'accepted_full_gate':item['accepted'],
                       'source_points':len(points),'not_in_retained_correspondences':len(points)-len(src),
                       'full':full,'both_core':core,'other_matches':boundary,'axial_z':z,'point_to_plane_valid_normals':plane,
                       'regions_4x3':bins,'target_depth_bands':depth_bands,
                       'core_error_share':core['squared_error_sum_m2']/full['squared_error_sum_m2']}
                entries.append(entry)
                full_mm=full['rmse_m']*1000; core_mm='—' if core['rmse_m'] is None else f'{core["rmse_m"]*1000:.2f}'
                html_rows.append(f'<tr><td>{mode}</td><td>{si}→{ti}</td><td>{full_mm:.2f}</td><td>{core_mm}</td><td>{core["count"]}/{full["count"]}</td><td>{entry["core_error_share"]:.1%}</td></tr>')
                if edge_i in [55,56,58] and direction=='forward':
                    overlay=(color*.35).astype('u1'); col=np.zeros((len(distance),3),dtype='u1')
                    col[distance<=.035]=[30,210,150]; col[(distance>.035)&(distance<=.06)]=[255,180,30]
                    col[distance>.06]=[255,60,90]
                    for dy in [-1,0,1]:
                        for dx in [-1,0,1]:
                            overlay[np.clip(tv[dst]+dy,0,479),np.clip(tu[dst]+dx,0,639)]=col
                    Image.fromarray(overlay).save(a.output/f'{mode}-edge-{edge_i:02}.png')
    report={'schema_version':'cospace.fixed-pose-residuals/0.1','selected_edges':selected,'entries':entries,
            'runs':{k:{'result':r['result'],'options':r['options'],'input_masks':r['input_masks']} for k,r in reports.items()},
            'input_sha256':sha(manifest),'original_sha256':sha(a.original/'comparison.json'),
            'interior_sha256':sha(a.interior/'comparison.json'),
            'interpretation':['core_is_subset_of_same_matches_no_refit','full_gate_remains_original_cloud',
                              'unmatched_and_over_120mm_not_in_rmse','plane_residual_is_descriptive_only',
                              'depth_mask_does_not_disable_all_photometric_pyramid_boundaries'],
            'algorithm_ready':False,'real_release_ready':False,'independent_accuracy_verified':False,
            'implementation_sha256':{f:sha(Path(f)) for f in ['experiments/scripts/diagnose_nyu_residuals.py',
                'packages/construction/rgbd_diagnostics.py','packages/construction/rgbd_multiscale.py']}}
    (a.output/'diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    html='''<!doctype html><meta charset="utf-8"><title>NYU 断点残差与空洞近邻对照</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;background:#111827;color:#e2e8f0;font:14px system-ui}h1{font-size:23px}h2{font-size:17px}p{color:#94a3b8;line-height:1.7}a{color:#7dd3fc}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #334155;text-align:left}img{width:48%;margin:1%}section{padding:18px;background:#1e293b;margin:18px 0;border-radius:10px}</style><h1>NYU办公室 · 断点残差与空洞近邻对照</h1><p>固定仅光度目标；原输入与排除空洞4像素近邻的深度关联对照。颜色不变，最终仍使用完整原始点云门槛。内部金字塔可能传播边缘影响，不代表完全屏蔽光度边界。</p>'''
    for mode,r in reports.items():
        s=r['result']; counts=[f['retained_pixels'] for f in r['input_masks']]
        html+=f'<section>{escape(mode)} · 双向 {s["bidirectional_accepted_edges"]}/59 · 连续前缀 {s["prefix_frames"]}帧 · 保留像素 {min(counts):,}—{max(counts):,}</section>'
    html+='<p>core：源/目标均距缺失区大于4像素的匹配子集，使用原位姿和原配对；其较低残差不用于放行。共同门槛保留35mm。绿色≤35mm，黄色35—60mm，红色＞60mm；散点并非表面精度。</p><a href="diagnostics.json">全部分区、轴向与法向残差</a><table><tr><th>模式</th><th>源→目标帧</th><th>全体RMSE mm</th><th>内部RMSE mm</th><th>内部/全部匹配</th><th>内部平方误差占比</th></tr>'+''.join(html_rows)+'</table>'
    html+='<h2>首断点56→57 · 按目标观测距离分组（原输入）</h2><table><tr><th>距离 m</th><th>匹配数</th><th>RMSE mm</th><th>名义单码步长 mm</th></tr>'
    first=next(e for e in entries if e['mode']=='original' and e['edge']==56 and e['direction']=='forward')
    for b in first['target_depth_bands']:
        rms='—' if b['rmse_m'] is None else f'{b["rmse_m"]*1000:.2f}'
        step='—' if b['nominal_one_code_step_median_m'] is None else f'{b["nominal_one_code_step_median_m"]*1000:.2f}'
        html+=f'<tr><td>{b["depth_min_m"]}—{b["depth_max_m"]}</td><td>{b["count"]}</td><td>{rms}</td><td>{step}</td></tr>'
    html+='</table><p>名义单码步长由原始深度换算式导数 z²/351.3 估计，是量化尺度，不是标准差、独立精度或允许误差。远距残差更大是后续核验线索，尚未证明根因；不据此放宽35mm门槛。</p>'
    for i in [55,56,58]:
        html+=f'<h2>边 {i}→{i+1}，显示目标帧上的残差位置</h2><img src="original-edge-{i:02}.png" alt="原输入"><img src="interior-edge-{i:02}.png" alt="排除空洞近邻">'
    (a.output/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps({'entries':len(entries),'runs':{k:r['result'] for k,r in reports.items()}}))


if __name__=='__main__': main()
