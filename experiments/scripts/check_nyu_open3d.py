"""Independently check and archive a completed RGB-D experiment (no Open3D)."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from packages.construction.rgbd_diagnostics import interior_mask


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('run',type=Path); p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); report=json.loads((a.run/'comparison.json').read_bytes())
    inputs=json.loads((a.prepared/'input.json').read_bytes()); cfg=report['common_geometry_config']
    checks={}
    def check(name,value):
        checks[name]=bool(value)
        if not value: raise ValueError(name)
    check('prepared_manifest',sha(a.prepared/'input.json')==report['prepared_input_sha256'])
    check('baseline',sha(a.baseline)==report['baseline_sha256'])
    check('source',sha(Path(inputs['source_snapshot'])/'report.json')==report['source_report_sha256'])
    check('prepared_frames',all(sha(a.prepared/f['path'])==f['sha256']
                               and (a.prepared/f['path']).stat().st_size==f['bytes'] for f in inputs['frames']))
    if 'input_masks' in report:
        check('mask_count',len(report['input_masks'])==len(inputs['frames']))
        for i,(f,record) in enumerate(zip(inputs['frames'],report['input_masks'])):
            with np.load(a.prepared/f['path'],allow_pickle=False) as arrays: depth=arrays['depth']
            core=interior_mask(depth,report['options']['hole_margin_px'])
            check(f'mask_{i}',record['frame']==i and record['original_valid_pixels']==int((depth>0).sum())
                  and record['retained_pixels']==int(core.sum())
                  and record['mask_sha256']==hashlib.sha256(core.tobytes()).hexdigest())
    for group,hashes in [('runner',report['implementation_sha256']),('preparation',inputs['implementation_sha256'])]:
        check(group+'_fingerprints',all(sha(Path(path))==digest for path,digest in hashes.items()))
    def rotation_angle(matrix):
        return float(np.arccos(np.clip((np.trace(matrix)-1)/2,-1,1)))
    def common(edge):
        t=np.array(edge['T_previous_current']); r=t[:3,:3]
        valid=(np.isfinite(t).all() and np.allclose(t[3],[0,0,0,1])
               and np.allclose(r.T@r,np.eye(3),atol=1e-6) and abs(np.linalg.det(r)-1)<1e-6)
        return (valid and edge['library_solver_success'] and edge['matched_points']>=cfg['min_matches']
                and edge['overlap']>=cfg['min_overlap'] and edge['rmse_m'] is not None
                and edge['rmse_m']<=cfg['max_rmse_m'] and edge['geometry_ratio']>=cfg['min_geometry_ratio']
                and np.linalg.norm(t[:3,3])<=cfg['max_translation_m']
                and rotation_angle(r)<=cfg['max_rotation_rad'])
    poses=[np.eye(4)]; prefix=True; common_count=0; accepted_count=0
    check('edge_count',len(report['edges'])==len(inputs['frames'])-1==59)
    for i,edge in enumerate(report['edges']):
        check(f'edge_{i}_order',edge['previous_frame']==i and edge['current_frame']==i+1)
        f=common(edge); b=common(edge['reverse']); common_count+=f
        closure=np.array(edge['T_previous_current'])@np.array(edge['reverse']['T_previous_current'])
        translation=float(np.linalg.norm(closure[:3,3])); angle=rotation_angle(closure[:3,:3])
        accepted=bool(f and b and translation<=report['options']['cycle_translation_m']
                      and angle<=report['options']['cycle_rotation_rad'])
        check(f'edge_{i}_decision',f==edge['common_gate_accepted'] and b==edge['reverse']['accepted']
              and accepted==edge['accepted'] and abs(translation-edge['cycle_translation_m'])<1e-10
              and abs(angle-edge['cycle_rotation_rad'])<1e-7)
        accepted_count+=accepted
        if prefix and accepted: poses.append(poses[-1]@np.array(edge['T_previous_current']))
        else: prefix=False
    r=report['result']
    check('counts',common_count==r['common_gate_accepted_edges'] and accepted_count==r['bidirectional_accepted_edges'])
    check('prefix',len(poses)==r['prefix_frames'] and np.allclose(poses,report['prefix_T_anchor_camera']))
    check('completion',r['completed']==(len(poses)==len(inputs['frames'])))
    check('cloud',sha(a.run/'accepted-prefix.ply')==report['cloud_sha256'])
    check('research_only',not report['algorithm_ready'] and not report['real_release_ready']
          and not report['independent_accuracy_verified'])
    a.output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(a.run/'comparison.json',a.output/'comparison.json')
    shutil.copyfile(a.prepared/'input.json',a.output/'prepared-input.json')
    dist=Path('experiments/stack/rgbd-open3d/.venv/Lib/site-packages/open3d-0.19.0.dist-info')
    for name in ('LICENSE.txt','METADATA','WHEEL'):
        shutil.copyfile(dist/name,a.output/('open3d-'+name))
    checks['evidence_sha256']={f.name:sha(f) for f in a.output.iterdir() if f.is_file()}
    checks['result']=r
    (a.output/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps({'checks_passed':sum(v is True for v in checks.values()),'result':r}))


if __name__=='__main__': main()
