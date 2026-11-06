"""Inspect fixed raw/rectified RGB-D frames and archive descriptive diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np
from PIL import Image
from packages.data.nyu_rgbd import (read_pnm,make_cloud,COLOR_R,COLOR_T,RGB_K,RGB_D,distort)
from packages.construction.rgbd_diagnostics import boundaries


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('prepared',type=Path); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    manifest=a.prepared/'input.json'; inputs=json.loads(manifest.read_bytes())
    source=Path(inputs['source_snapshot']); source_manifest=source/'report.json'; src=json.loads(source_manifest.read_bytes())
    if sha(source_manifest)!=inputs['source_report_sha256']: raise ValueError('source_integrity')
    toolbox=Path('experiments/evidence/2026-10-28/nyu-offices-review-001/toolbox-source.zip')
    with zipfile.ZipFile(toolbox) as z:
        for name in ['camera_params.m','depth_world2rgb_world.m','rgb_world2rgb_plane.m','get_synched_frames.m']:
            (a.output/name).write_bytes(z.read(name))
    rows=[]; cards=[]
    # Fixed indices include the old and new first break; minimum coverage adds a stress frame.
    selected={0,1,5,6,30,59,min(inputs['frames'],key=lambda f:f['valid_pixels'])['index']}
    for frame in inputs['frames']:
        path=a.prepared/frame['path']
        if sha(path)!=frame['sha256']: raise ValueError('prepared_integrity')
        with np.load(path,allow_pickle=False) as arrays: depth=arrays['depth']; color=arrays['color']
        holes,surfaces,edges,stats=boundaries(depth,color)
        stats.update(index=frame['index'],rgb_minus_depth_us=frame['pair']['rgb_minus_depth_us'])
        rows.append(stats)
        if frame['index'] not in selected: continue
        images=[]
        for role in ['depth','rgb']:
            name=frame['pair'][role]; raw=(source/'raw'/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=src['members'][name]['sha256']: raise ValueError('raw_integrity')
            images.append(read_pnm(raw,role=='depth'))
        points,colors,pixels,valid,_=make_cloud(*images,1)
        projected=points@COLOR_R.T+COLOR_T
        dx,dy=distort(projected[:,0]/projected[:,2],projected[:,1]/projected[:,2],RGB_D)
        u=np.rint(dx*RGB_K[0]+RGB_K[2]-1).astype(int); v=np.rint(dy*RGB_K[1]+RGB_K[3]-1).astype(int)
        # Independent expanded Brown-Conrady formula checks implementation arithmetic.
        x=projected[:,0]/projected[:,2]; y=projected[:,1]/projected[:,2]; r=x*x+y*y
        k1,k2,p1,p2,k3=RGB_D; scale=1+k1*r+k2*r*r+k3*r*r*r
        ex=x*scale+2*p1*x*y+p2*(r+2*x*x); ey=y*scale+p1*(r+2*y*y)+2*p2*x*y
        if not np.allclose(dx,ex) or not np.allclose(dy,ey): raise ValueError('projection_arithmetic')
        # Compare projected depth discontinuities with original RGB, excluding missing-depth boundaries.
        raw_depth=np.zeros((480,640),np.float32); raw_depth[pixels[:,1],pixels[:,0]]=points[:,2]
        _,raw_surfaces,_,_=boundaries(raw_depth,images[1])
        on_edge=valid&raw_surfaces[pixels[:,1],pixels[:,0]]
        overlay=images[1].copy(); overlay[v[on_edge],u[on_edge]]=[0,240,230]
        rect=color.copy(); rect[surfaces]=[0,240,230]; rect[holes]=[255,80,100]
        occlusion_key=v[valid]*640+u[valid]
        # Negative Z is the literal toolbox projection convention: use positive original depth for this diagnostic.
        ids=np.flatnonzero(valid); order=np.argsort(points[ids,2]); ids=ids[order]
        key=v[ids]*640+u[ids]; _,first=np.unique(key,return_index=True)
        nearest=np.full(480*640,np.inf); nearest[key[first]]=points[ids[first],2]
        behind=points[ids,2]>nearest[key]+.05
        stats.update(projected_points=int(valid.sum()),projection_collision_points=int(len(occlusion_key)-len(np.unique(occlusion_key))),
                     behind_nearest_original_depth_gt_5cm=int(behind.sum()),
                     projected_z_negative_points=int((projected[:,2]<0).sum()),
                     projection_arithmetic_verified=True)
        for suffix,image in [('rgb',images[1]),('projected-edges',overlay),('rectified-edges',rect)]:
            Image.fromarray(image).save(a.output/f'frame-{frame["index"]:03}-{suffix}.png')
        i=frame['index']; fraction=stats['valid_image_edges_near_holes']/max(1,stats['image_edges_on_valid_depth'])
        cards.append(f'<section><h2>帧 {i} · 彩深时间差 {stats["rgb_minus_depth_us"]/1000:.2f}ms</h2>'
                     f'<p>有效像素 {stats["valid_pixels"]:,} · 有效深度上的图像边缘中，距空洞边界≤2px：{fraction:.1%}</p>'
                     f'<div><figure><img src="frame-{i:03}-rgb.png"><figcaption>原始RGB</figcaption></figure>'
                     f'<figure><img src="frame-{i:03}-projected-edges.png"><figcaption>原始RGB＋投影深度突变（青色）</figcaption></figure>'
                     f'<figure><img src="frame-{i:03}-rectified-edges.png"><figcaption>里程计输入：青色深度突变，红色空洞边界</figcaption></figure></div></section>')
    result={'schema_version':'cospace.rgbd-alignment-diagnostics/0.1','prepared_input_sha256':sha(manifest),
            'toolbox_sha256':sha(toolbox),'projection_R_determinant':float(np.linalg.det(COLOR_R)),
            'color_translation':COLOR_T.tolist(),'frames':rows,'selected_frames':sorted(selected),
            'thresholds_descriptive_only':{'depth_jump_m':.15,'gray_edge':.1,'edge_radius_px':2,'behind_nearest_depth_m':.05},
            'limitations':['no_independent_calibration_or_motion_reference','edge_coincidence_is_not_accuracy',
                          'collision_uses_original_depth_proxy_not_physical_RGB_camera_Z','no_clock_or_motion_compensation'],
            'algorithm_ready':False,'real_release_ready':False,
            'implementation_sha256':{f:sha(Path(f)) for f in ['experiments/scripts/diagnose_nyu_alignment.py',
                'packages/construction/rgbd_diagnostics.py','packages/data/nyu_rgbd.py']}}
    (a.output/'diagnostics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    html='''<!doctype html><meta charset="utf-8"><title>NYU 彩深配准诊断</title><style>body{max-width:1400px;margin:32px auto;padding:0 20px;background:#111827;color:#e2e8f0;font:14px system-ui}h1{font-size:24px}h2{font-size:17px}p,figcaption{color:#94a3b8}section{margin:24px 0;padding:16px;background:#1e293b;border-radius:10px}section div{display:flex;gap:12px}figure{margin:0;flex:1;min-width:0}img{width:100%}a{color:#7dd3fc}@media(max-width:900px){section div{display:block}}</style><h1>NYU办公室 · 彩深配准与空洞诊断</h1><p>用于检查输入，不代表标定或建图精度合格。青色：已观测深度突变；红色：有效/缺失深度边界。所有空洞保持无效。</p><a href="diagnostics.json">全部60帧指标与来源</a>'''
    (a.output/'index.html').write_text(html+''.join(cards),encoding='utf-8')
    print(json.dumps({'frames':len(rows),'selected_frames':sorted(selected),'projection_R_determinant':result['projection_R_determinant']}))


if __name__=='__main__': main()
