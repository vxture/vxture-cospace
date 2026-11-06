"""Build reproducible descriptive comparison; preserve all rejected edges."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import numpy as np


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--hybrid',type=Path,required=True)
    p.add_argument('--constant-color',type=Path,required=True); p.add_argument('--color-only',type=Path,required=True)
    p.add_argument('--alignment',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output; out.mkdir(parents=True,exist_ok=False)
    reports={}; sources={}; rows=[]; fingerprints=None; source_hash=None
    for mode,path in [('hybrid',a.hybrid),('constant-color',a.constant_color),('color-only',a.color_only)]:
        raw=path/'comparison.json'; report=json.loads(raw.read_bytes())
        if report['mode']!=mode: raise ValueError('mode_mismatch')
        if fingerprints is None: fingerprints=report['implementation_sha256']; source_hash=report['prepared_input_sha256']
        if fingerprints!=report['implementation_sha256'] or source_hash!=report['prepared_input_sha256']:
            raise ValueError('comparison_fingerprint_mismatch')
        reports[mode]=report; sources[mode]={'path':str(path),'sha256':sha(raw)}
        shutil.copyfile(raw,out/f'{mode}.json')
        r=report['result']; first=next((e for e in report['edges'] if not e['accepted']),None)
        rows.append({'mode':mode,**r,'first_rejected_edge':None if first is None else {
            k:first[k] for k in ['previous_frame','current_frame','rmse_m','cycle_translation_m','cycle_rotation_rad','reasons']}})
    alignment=json.loads((a.alignment/'diagnostics.json').read_bytes())
    if alignment['prepared_input_sha256']!=source_hash: raise ValueError('alignment_input_mismatch')
    shutil.copyfile(a.alignment/'diagnostics.json',out/'alignment.json')
    missing=[f['missing_pixels'] for f in alignment['frames']]
    near=sum(f['valid_image_edges_near_holes'] for f in alignment['frames'])
    total=sum(f['image_edges_on_valid_depth'] for f in alignment['frames'])
    summary={'schema_version':'cospace.rgbd-ablation-comparison/0.1','sources':sources,'results':rows,
             'prepared_input_sha256':source_hash,'identical_runner_fingerprints':True,
             'missing_pixels_range':[min(missing),max(missing)],
             'valid_depth_image_edges_near_holes_fraction':near/total,
             'max_abs_rgb_depth_delta_us':max(abs(f['rgb_minus_depth_us']) for f in alignment['frames']),
             'algorithm_ready':False,'real_release_ready':False,'independent_accuracy_verified':False,
             'limitations':['color_only_still_uses_depth_for_association','constant_color_is_hybrid_objective_ablation',
                           'missing_pixel_edges_can_affect_photometric_objective','no_independent_pose_or_calibration_reference'],
             'implementation_sha256':sha(Path(__file__))}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    # Images are diagnostic artifacts only; source raw images remain read-only.
    for image in a.alignment.glob('*.png'): shutil.copyfile(image,out/image.name)
    for name in ['camera_params.m','depth_world2rgb_world.m','rgb_world2rgb_plane.m','get_synched_frames.m']:
        shutil.copyfile(a.alignment/name,out/name)
    shutil.copyfile(a.alignment/'index.html',out/'alignment.html')
    html='''<!doctype html><meta charset="utf-8"><title>NYU 输入与约束分离对照</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;background:#111827;color:#e2e8f0;font:14px system-ui}h1{font-size:24px}h2{font-size:18px}p{line-height:1.7;color:#94a3b8}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #334155}a{color:#7dd3fc}section{padding:20px;background:#1e293b;border-radius:10px;margin:20px 0}img{max-width:100%}</style><h1>NYU办公室 · 输入质量与约束分离对照</h1><p>同一60帧，同一有效像素、起始位姿、几何与双向阈值；三种模式使用同版实现。均非独立位姿精度验收。</p><table><tr><th>模式</th><th>前向几何</th><th>双向</th><th>连续前缀</th><th>首断点（0起编号）</th></tr>'''
    labels={'hybrid':'光度＋深度混合','constant-color':'固定颜色混合（纹理消融）','color-only':'仅光度目标（依赖深度关联）'}
    for row in rows:
        edge=row['first_rejected_edge']; first='无' if edge is None else f'{edge["previous_frame"]}→{edge["current_frame"]}'
        html+=f'<tr><td><a href="{row["mode"]}.json">{escape(labels[row["mode"]])}</a></td><td>{row["common_gate_accepted_edges"]}/59</td><td>{row["bidirectional_accepted_edges"]}/59</td><td>{row["prefix_frames"]}帧</td><td>{first}</td></tr>'
    html+='</table><section><h2>如何解释</h2><p>仅光度目标的连续性改善，但最后仍被几何检查拒绝。固定颜色未消除首断点，真实纹理并非唯一因素。空洞边界、深度量化、时间差和优化目标相互作用尚未分离，不能据此认定根因或放行融合。</p>'
    html+=f'<p>全部60帧：{near/total:.1%} 的有效深度图像边缘位于空洞边界2像素以内。这是描述性共现，包含预处理产生的边界，不是对真实场景纹理的因果结论。最大彩深时间差 {summary["max_abs_rgb_depth_delta_us"]/1000:.3f}ms。</p></section>'
    html+='<a href="alignment.html">查看六帧叠加诊断</a> · <a href="summary.json">比较摘要与来源</a><h2>后续验证</h2><p>固定本轮仅光度候选，先检查与空洞边缘保持距离的共同有效区、几何残差的空间分布及跨帧重投影；不修改既有结果，不放宽门槛，不把缺失当空闲。</p><img src="frame-030-rectified-edges.png" alt="帧30输入，青色为深度突变，红色为空洞边界">'
    (out/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__': main()
