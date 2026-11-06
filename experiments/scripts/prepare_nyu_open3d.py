"""Freeze rectified RGB-D inputs for the isolated mature odometry experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from packages.data.nyu_rgbd import DEPTH_K,read_pnm,make_cloud
from packages.construction.rgbd_rectify import rasterize_depth_cloud


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('snapshot',type=Path)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    root=args.output; root.mkdir(parents=True,exist_ok=False)
    raw_report=(args.snapshot/'report.json').read_bytes(); source=json.loads(raw_report); frames=[]
    for i,pair in enumerate(p for p in source['pairs'] if p['accepted']):
        images=[]
        for role in ('depth','rgb'):
            name=pair[role]; raw=(args.snapshot/'raw'/name).read_bytes(); m=source['members'][name]
            if len(raw)!=m['bytes'] or hashlib.sha256(raw).hexdigest()!=m['sha256']: raise ValueError('snapshot_integrity')
            images.append(read_pnm(raw,role=='depth'))
        points,colors,_,valid,_=make_cloud(*images,1)
        depth,color,stats=rasterize_depth_cloud(points,colors,valid)
        path=root/f'frame-{i:03}.npz'; np.savez_compressed(path,depth=depth,color=color)
        frames.append({'index':i,'time_us':pair['depth_time_us'],'pair':pair,'path':path.name,
                       'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,**stats})
        if (i+1)%10==0: print(json.dumps({'prepared_frames':i+1}),flush=True)
    report={'schema_version':'cospace.rectified-rgbd-input/0.1','source_snapshot':str(args.snapshot),
            'source_report_sha256':hashlib.sha256(raw_report).hexdigest(),'frames':frames,
            'intrinsic':{'width':640,'height':480,'fx':float(DEPTH_K[0]),'fy':float(DEPTH_K[1]),
                         'cx_zero_based':float(DEPTH_K[2]-1),'cy_zero_based':float(DEPTH_K[3]-1)},
            'frame':'depth_optical','unit':'m','method':'depth_distortion_inverse_then_nearest_z_buffer',
            'depth_invalid_value':0,'depth_inpainted':False,'registration_quality_verified':False,
            'algorithm_ready':False,'real_release_ready':False,
            'limitations':['color_projection_has_no_occlusion_consistency','no_motion_compensation',
                           'nearest_pixel_rectification','no_independent_reference'],
            'implementation_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                ('packages/data/nyu_rgbd.py','packages/construction/rgbd_rectify.py','experiments/scripts/prepare_nyu_open3d.py')}}
    (root/'input.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'prepared_frames':len(frames),'output':str(root)}))


if __name__=='__main__': main()
