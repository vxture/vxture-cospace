"""Track a fixed short snapshot, stopping the trajectory at the first rejected edge."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from packages.data.nyu_rgbd import make_cloud,read_pnm,ply_bytes
from packages.construction.rgbd_tracking import CONFIG,register_pair,transform


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('snapshot',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); root=args.output
    root.mkdir(parents=True,exist_ok=False)
    raw_report=(args.snapshot/'report.json').read_bytes(); report=json.loads(raw_report)
    def load(pair):
        arrays=[]
        for role in ('depth','rgb'):
            name=pair[role]; raw=(args.snapshot/'raw'/name).read_bytes()
            member=report['members'][name]
            if len(raw)!=member['bytes'] or hashlib.sha256(raw).hexdigest()!=member['sha256']:
                raise ValueError('snapshot_integrity')
            arrays.append(read_pnm(raw,role=='depth'))
        return make_cloud(*arrays)
    pairs=[p for p in report['pairs'] if p['accepted']]
    if len(pairs)<2: raise ValueError('insufficient_frames')
    previous=load(pairs[0]); world=np.eye(4)
    poses=[{'frame':0,'time_us':pairs[0]['depth_time_us'],'T_anchor_camera':world.tolist()}]
    accumulated=[previous[0]]; colors=[previous[1]]; color_valid=[previous[3]]; edges=[]; last_added=0
    for i,pair in enumerate(pairs[1:],1):
        current=load(pair)
        result=register_pair(current[0],previous[0],previous[2])
        result.update(previous_frame=i-1,current_frame=i,dt_us=pair['depth_time_us']-pairs[i-1]['depth_time_us'])
        edges.append(result)
        if not result['accepted']: break
        world=world@np.array(result['T_previous_current'])
        poses.append({'frame':i,'time_us':pair['depth_time_us'],'T_anchor_camera':world.tolist()})
        if i%5==0 or i==len(pairs)-1:
            accumulated.append(transform(current[0],world)); colors.append(current[1]); color_valid.append(current[3])
            last_added=i
        previous=current
    if last_added!=len(poses)-1:
        accumulated.append(transform(previous[0],world)); colors.append(previous[1]); color_valid.append(previous[3])
    points=np.concatenate(accumulated); rgb=np.concatenate(colors); valid=np.concatenate(color_valid)
    # Reuse vertex encoding but override its local frame annotation for accumulated points.
    cloud=ply_bytes(points,rgb,valid).replace(b'frame depth_optical',b'frame first_depth_camera_anchor')
    (root/'accumulated.ply').write_bytes(cloud)
    result={'schema_version':'cospace.rgbd-tracking-experiment/0.1','source_snapshot':str(args.snapshot),
            'source_report_sha256':hashlib.sha256(raw_report).hexdigest(),'config':CONFIG,
            'method':'projective_trimmed_point_to_point_icp','uses_rgb_for_tracking':False,
            'total_frames':len(pairs),'tracked_frames':len(poses),'completed':len(poses)==len(pairs),
            'poses':poses,'edges':edges,'accumulated_point_count':len(points),
            'accumulation_stride_frames':5,'cloud_sha256':hashlib.sha256(cloud).hexdigest(),
            'algorithm_ready':False,'real_release_ready':False,'independent_accuracy_verified':False,
            'limitations':['no_loop_closure','no_global_optimization','no_rgb_features','no_independent_reference',
                          'projective_matches_can_be_ambiguous','accumulation_not_tsdf_or_occupancy'],
            'implementation_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                  ('packages/data/nyu_rgbd.py','packages/construction/rgbd_tracking.py','experiments/scripts/track_nyu_short_scene.py')}}
    (root/'tracking.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'completed':result['completed'],'tracked_frames':len(poses),'edges':len(edges),
                     'last_edge':edges[-1] if edges else None}))


if __name__=='__main__': main()
