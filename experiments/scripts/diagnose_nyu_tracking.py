"""Evaluate each adjacent edge independently; never join across a rejected edge."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from packages.data.nyu_rgbd import make_cloud,read_pnm
from packages.construction.rgbd_tracking import CONFIG,register_pair


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('snapshot',type=Path)
    parser.add_argument('--tracking',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); root=args.output; root.mkdir(parents=True,exist_ok=False)
    raw_report=(args.snapshot/'report.json').read_bytes(); source=json.loads(raw_report)
    def load(pair):
        arrays=[]
        for role in ('depth','rgb'):
            name=pair[role]; raw=(args.snapshot/'raw'/name).read_bytes(); m=source['members'][name]
            if len(raw)!=m['bytes'] or hashlib.sha256(raw).hexdigest()!=m['sha256']: raise ValueError('snapshot_integrity')
            arrays.append(read_pnm(raw,role=='depth'))
        return make_cloud(*arrays)
    pairs=[p for p in source['pairs'] if p['accepted']]; previous=load(pairs[0]); edges=[]
    for i,pair in enumerate(pairs[1:],1):
        current=load(pair); edge=register_pair(current[0],previous[0],previous[2])
        edge.update(previous_frame=i-1,current_frame=i); edges.append(edge); previous=current
    counts={}
    for edge in edges:
        for reason in edge['reasons']: counts[reason]=counts.get(reason,0)+1
    report={'schema_version':'cospace.rgbd-pair-diagnostics/0.1','config':CONFIG,'edges':edges,
            'mode':'independent_adjacent_pairs_no_global_trajectory',
            'source_report_sha256':hashlib.sha256(raw_report).hexdigest(),
            'accepted_edges':sum(e['accepted'] for e in edges),'total_edges':len(edges),'rejection_reasons':counts,
            'algorithm_ready':False,'independent_accuracy_verified':False}
    (root/'diagnostics.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    tracking_raw=(args.tracking/'tracking.json').read_bytes(); tracking=json.loads(tracking_raw)
    if tracking['source_report_sha256']!=report['source_report_sha256']: raise ValueError('tracking_source_mismatch')
    report['tracking_report_sha256']=hashlib.sha256(tracking_raw).hexdigest()
    report['implementation_sha256']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
        ('packages/construction/rgbd_tracking.py','packages/data/nyu_rgbd.py','experiments/scripts/diagnose_nyu_tracking.py')}
    (root/'diagnostics.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    # Portable static report: all frames are diagnostic edges; only the accepted prefix is a trajectory.
    bars=[]
    for i,edge in enumerate(edges):
        height=min(180,(edge['rmse_m'] or .12)/.06*180)
        color='#38bdf8' if edge['accepted'] else '#fb7185'
        bars.append(f'<rect x="{i*12+10}" y="{210-height}" width="8" height="{height}" fill="{color}"><title>frame {i+1}: {edge["rmse_m"]} m; {edge["reasons"]}</title></rect>')
    import os
    def link(path): return Path(os.path.relpath(path,root)).as_posix()
    html='''<!doctype html><meta charset="utf-8"><title>NYU 连续帧配准核对</title>
<style>body{margin:40px auto;max-width:1000px;background:#111827;color:#dbeafe;font:14px system-ui}a{color:#7dd3fc}section{background:#1e293b;padding:24px;margin:20px 0;border-radius:10px}svg{width:100%}small{color:#94a3b8}</style>
<h2>NYU办公室 · 连续帧配准实验</h2>'''
    html+=f'<p>60帧 / 约2秒 · 深度几何ICP · 连续接受前缀 {tracking["tracked_frames"]} 帧</p>'
    html+=f'<section><h3>已保留断点</h3><p>逐对独立检查：{report["accepted_edges"]}/{len(edges)} 条边满足本次实验配置。后续通过的边不跨断点拼成全局轨迹。</p>'
    html+='<p>蓝色：通过；红色：拒绝。柱高为匹配残差，鼠标悬停查看诊断；虚线为35mm实验阈值。</p>'
    html+=f'<svg viewBox="0 0 {len(edges)*12+25} 230">'+''.join(bars)+f'<path d="M0 105 H{len(edges)*12+25}" stroke="#e2e8f0" stroke-dasharray="4 4"/></svg></section>'
    html+=f'<section><h3>可核对产物</h3><p><a href="{link(args.tracking/"accumulated.ply")}">短前缀累积PLY</a> · <a href="{link(args.tracking/"tracking.json")}">轨迹与拒绝记录</a> · <a href="diagnostics.json">全部59对诊断</a> · <a href="{link(args.snapshot/"index.html")}">单帧核对页</a></p></section>'
    html+='<small>残差是内部匹配指标，不是绝对精度。没有回环、多帧优化、TSDF融合或独立测量核验。</small>'
    (root/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('accepted_edges','total_edges','rejection_reasons')}))


if __name__=='__main__': main()
