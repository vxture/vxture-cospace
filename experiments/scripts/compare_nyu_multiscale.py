"""Same-snapshot comparison with fixed common gates and bidirectional diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from packages.data.nyu_rgbd import read_pnm,make_cloud
from packages.construction.rgbd_tracking import CONFIG,angle
from packages.construction.rgbd_multiscale import MULTISCALE,register_multiscale


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('snapshot',type=Path)
    parser.add_argument('--baseline',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); root=args.output; root.mkdir(parents=True,exist_ok=False)
    raw_report=(args.snapshot/'report.json').read_bytes(); report=json.loads(raw_report)
    baseline_raw=args.baseline.read_bytes(); baseline=json.loads(baseline_raw)
    if baseline['source_report_sha256']!=hashlib.sha256(raw_report).hexdigest() or baseline['config']!=CONFIG:
        raise ValueError('baseline_source_or_config_mismatch')
    pairs=[p for p in report['pairs'] if p['accepted']]
    if len(baseline['edges'])!=len(pairs)-1: raise ValueError('baseline_edge_count')
    def load(pair):
        images=[]
        for role in ('depth','rgb'):
            name=pair[role]; raw=(args.snapshot/'raw'/name).read_bytes(); member=report['members'][name]
            if len(raw)!=member['bytes'] or hashlib.sha256(raw).hexdigest()!=member['sha256']: raise ValueError('snapshot_integrity')
            images.append(read_pnm(raw,role=='depth'))
        levels={}
        for stride in MULTISCALE['strides']:
            points,_,pixels,_,_=make_cloud(*images,stride)
            levels[stride]=(points,pixels)
        return levels
    previous=load(pairs[0]); edges=[]; poses=[np.eye(4).tolist()]; prefix_open=True; begin=time.perf_counter()
    for i,pair in enumerate(pairs[1:],1):
        current=load(pair); start=time.perf_counter()
        forward=register_multiscale(current,previous); reverse=register_multiscale(previous,current)
        closure=np.array(forward['T_previous_current'])@np.array(reverse['T_previous_current'])
        cycle_translation=float(np.linalg.norm(closure[:3,3])); cycle_rotation=angle(closure[:3,:3])
        common_accepted=forward['accepted']
        if not reverse['accepted']: forward['reasons'].append('reverse_registration_rejected')
        if cycle_translation>.02 or cycle_rotation>.02: forward['reasons'].append('bidirectional_inconsistent')
        forward.update(accepted=not forward['reasons'],common_gate_accepted=common_accepted,
                       current_frame=i,previous_frame=i-1,reverse=reverse,
                       cycle_translation_m=cycle_translation,cycle_rotation_rad=cycle_rotation,
                       wall_seconds=time.perf_counter()-start)
        edges.append(forward)
        if prefix_open and forward['accepted']:
            poses.append((np.array(poses[-1])@np.array(forward['T_previous_current'])).tolist())
        else: prefix_open=False
        previous=current
        if i%10==0: print(json.dumps({'evaluated_edges':i}),flush=True)
    reasons={}
    for edge in edges:
        for reason in edge['reasons']: reasons[reason]=reasons.get(reason,0)+1
    baseline_prefix=1
    for edge in baseline['edges']:
        if not edge['accepted']: break
        baseline_prefix+=1
    result={'schema_version':'cospace.rgbd-multiscale-comparison/0.1',
            'source_report_sha256':hashlib.sha256(raw_report).hexdigest(),
            'baseline_sha256':hashlib.sha256(baseline_raw).hexdigest(),'config':CONFIG,'multiscale':MULTISCALE,
            'cycle_limits':{'translation_m':.02,'rotation_rad':.02},'total_frames':len(pairs),
            'baseline':{'accepted_edges':baseline['accepted_edges'],'prefix_frames':baseline_prefix},
            'candidate':{'common_gate_accepted_edges':sum(e['common_gate_accepted'] for e in edges),
                         'bidirectional_accepted_edges':sum(e['accepted'] for e in edges),'prefix_frames':len(poses),
                         'rejection_reasons':reasons},'edges':edges,'prefix_T_anchor_camera':poses,
            'wall_seconds':time.perf_counter()-begin,'uses_rgb_for_tracking':False,
            'algorithm_ready':False,'independent_accuracy_verified':False,'real_release_ready':False,
            'open3d_probe':'PyPI TLS EOF even after escalated retry; compatibility not established; not installed',
            'implementation_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                ('packages/data/nyu_rgbd.py','packages/construction/rgbd_tracking.py',
                 'packages/construction/rgbd_multiscale.py','experiments/scripts/compare_nyu_multiscale.py')}}
    (root/'comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    rows=[]
    for i,(old,new) in enumerate(zip(baseline['edges'],edges),1):
        def fmt(value): return '—' if value is None else f'{value*1000:.2f}'
        rows.append(f'<tr><td>{i-1} → {i}</td><td>{"通过" if old["accepted"] else "拒绝"}</td><td>{fmt(old["rmse_m"])}</td>'
                    f'<td>{"通过" if new["common_gate_accepted"] else "拒绝"}</td><td>{fmt(new["rmse_m"])}</td>'
                    f'<td>{"通过" if new["accepted"] else "拒绝"}</td><td>{", ".join(new["reasons"]) or "—"}</td></tr>')
    html='''<!doctype html><meta charset="utf-8"><title>NYU 多尺度配准对照</title>
<style>body{background:#111827;color:#e2e8f0;font:14px system-ui;margin:36px auto;max-width:1100px}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #334155}small,p{color:#94a3b8}a{color:#7dd3fc}section{padding:20px;background:#1e293b;border-radius:10px;margin:20px 0}</style>
<h2>NYU办公室 · 多尺度配准对照</h2><p>同一60帧快照；相同最终几何判据；额外展示反向配准与双向一致性。</p>'''
    html+=f'<section>原点到点：{baseline["accepted_edges"]}/59对，连续前缀{baseline_prefix}帧。<br>多尺度点到平面：共同判据{result["candidate"]["common_gate_accepted_edges"]}/59对；双向判据{result["candidate"]["bidirectional_accepted_edges"]}/59对；连续前缀{len(poses)}帧。</section>'
    html+='<p>残差单位mm；内部匹配残差不代表绝对精度。本实验没有使用RGB特征或光度约束，没有融合或生成正式真值。</p><a href="comparison.json">完整参数、变换与诊断</a>'
    html+='<table><thead><tr><th>相邻帧</th><th>原版</th><th>原版残差</th><th>多尺度共同判据</th><th>多尺度残差</th><th>双向判据</th><th>拒绝原因</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
    (root/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('baseline','candidate','wall_seconds')}))


if __name__=='__main__': main()
