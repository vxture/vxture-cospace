"""Independent scalar checks for real cycles and controlled quantization evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); r=json.loads((a.run/'report.json').read_bytes()); checks={}
    def check(name,value):
        checks[name]=bool(value)
        if not value: raise ValueError(name)
    check('fingerprints',all(sha(Path(f))==digest for f,digest in r['implementation_sha256'].items()))
    for name,path in r['input_paths'].items(): check(name+'_input',sha(Path(path))==r[name+'_sha256'])
    check('declared_mode',r['options']['jacobian']=='RGBDOdometryJacobianFromColorTerm' and r['options']['hole_margin_px']==0)
    check('pair_count',len(r['pairs'])==15)
    cfg=r['common_geometry_config']
    def angle(t): return float(np.arccos(np.clip((np.trace(t[:3,:3])-1)/2,-1,1)))
    for i,pair in enumerate(r['pairs']):
        f=pair['forward']; b=pair['reverse']; tf=np.array(f['matrix']); tb=np.array(b['matrix'])
        cycle=tf@tb; ct=float(np.linalg.norm(cycle[:3,3])); cr=angle(cycle)
        check(f'{i}_cycle',np.isclose(ct,pair['cycle_translation_m']) and np.isclose(cr,pair['cycle_rotation_rad']))
        accepted=f['accepted'] and b['accepted'] and ct<=.02 and cr<=.02
        check(f'{i}_accepted',bool(accepted)==pair['accepted'])
        for direction,e in [('forward',f),('reverse',b)]:
            t=np.array(e['matrix']); rot=t[:3,:3]
            valid=(e['solver_success'] and np.allclose(t[3],[0,0,0,1]) and np.allclose(rot.T@rot,np.eye(3),atol=1e-6)
                and abs(np.linalg.det(rot)-1)<1e-6 and e['matched_points']>=cfg['min_matches']
                and e['overlap']>=cfg['min_overlap'] and e['rmse_m']<=cfg['max_rmse_m']
                and e['geometry_ratio']>=cfg['min_geometry_ratio'] and np.linalg.norm(t[:3,3])<=cfg['max_translation_m']
                and angle(t)<=cfg['max_rotation_rad'])
            check(f'{i}_{direction}_gate',bool(valid)==e['accepted'])
            check(f'{i}_{direction}_bands',sum(band['count'] for band in e['bands'])==e['matched_count'] and
                np.isclose(sum(band['squared_error_sum_m2'] for band in e['bands']),e['rmse_m']**2*e['matched_count']))
        if pair['chain_matrix'] is not None:
            difference=np.linalg.inv(np.array(pair['chain_matrix']))@tf
            check(f'{i}_chain_difference',np.isclose(np.linalg.norm(difference[:3,3]),pair['direct_vs_chain_translation_m'])
                  and np.isclose(angle(difference),pair['direct_vs_chain_rotation_rad']))
    for i,row in enumerate(r['resolution']):
        code=row['code']; z=351.3/(1092.5-code); step=351.3/(1091.5-code)-z
        check(f'resolution_{i}',np.isclose(z,row['decoded_m']) and np.isclose(step,row['next_code_step_m']))
    # Independent RNG replay using explicit scalar coding formula, not implementation helpers.
    rng=np.random.default_rng(r['synthetic_seed']); base=rng.uniform(-1,1,(5000,3))
    def quantized(points):
        z=points[:,2]; code=np.rint(1092.5-351.3/z)
        return points*((351.3/(1092.5-code))/z)[:,None]
    for i,s in enumerate(r['synthetic']):
        center=s['center_depth_m']; target=np.column_stack([base[:,0]*center*.3,base[:,1]*center*.2,center+base[:,2]*.15])
        delta=np.array([0.,0.,s['motion_z_m']]); source=target-delta
        clean=np.linalg.norm(source+delta-target,axis=1)
        residual=quantized(source)+delta-quantized(target)
        biased=residual+np.array([.05,0.,0.])
        check(f'synthetic_{i}',np.max(clean)<1e-12 and np.isclose(np.sqrt(np.mean(np.sum(residual**2,axis=1))),s['quantized_true_pose']['rmse_m'])
              and np.isclose(np.sqrt(np.mean(np.sum(biased**2,axis=1))),s['quantized_with_50mm_x_pose_bias']['rmse_m']))
    check('research_only',not r['algorithm_ready'] and not r['real_release_ready'] and not r['independent_accuracy_verified'])
    a.output.mkdir(parents=True,exist_ok=False); shutil.copyfile(a.run/'report.json',a.output/'report.json')
    (a.output/'checks.json').write_text(json.dumps({'checks':checks,'checks_passed':len(checks),
        'report_sha256':sha(a.output/'report.json')},indent=2),encoding='utf-8')
    print(json.dumps({'checks_passed':len(checks)}))


if __name__=='__main__': main()
