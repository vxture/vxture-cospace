"""New multi-frame route; old first-frame registrations keep their original meaning."""
from pathlib import Path
import time
import numpy as np
import scipy
from packages.data.preview_lidar import read_specimen,MULTIFRAME_FORMAT
from packages.construction.lidar_mapping import register_pair,CONFIG,METHOD,transform
from packages.construction.lidar_process import LidarRecorder,FRAME,AXES
from packages.construction.preview_derivations import freeze
from packages.construction.preview_model import digest


def build(snapshot,output,job):
    checked,frames=read_specimen(snapshot,sequence=True)
    binding=job['input_binding']
    if binding.get('format')!=MULTIFRAME_FORMAT or any(binding.get(k)!=v for k,v in checked.items()):raise ValueError('registered_input_changed')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    recorder=LidarRecorder(output.parent/'process',job,checked)
    pose=np.eye(4);points=[];colors=[];trajectory=[];start=time.perf_counter()
    try:
        for i,frame in enumerate(frames):
            if i:
                result=register_pair(frame['points'],frames[i-1]['points'])
                if not result['accepted']:
                    recorder.reject(i,result)
                    raise ValueError('lidar_registration_rejected_frame_'+str(i))
                pose=pose@np.array(result['T_previous_current'])
            else:result={'accepted':True,'basis':'identity_anchor_not_estimated'}
            p=transform(frame['points'],pose);intensity=frame['intensity']
            # Fixed intensity transfer keeps colors stable across actual frames.
            shade=np.rint(60+180*np.clip(intensity,0,255)/255).astype(np.uint8)
            c=np.repeat(shade[:,None],3,axis=1)
            points.append(p);colors.append(c);recorder.record_scan(frame,pose,p,c,result)
            trajectory.append({k:recorder.value['frames'][-1][k] for k in ('index','header_ns','recorded_ns','message_sha256','pose','registration')})
            print(f'lidar frame {i+1}/{len(frames)} committed; model cells {len(recorder.seen)}',flush=True)
        p=np.concatenate(points);c=np.concatenate(colors);input_points=len(p)
        _,ids=np.unique(np.floor(p/.05).astype(np.int64),axis=0,return_index=True)
        p=p[ids].astype(np.float32);c=c[ids]
        np.savez_compressed(output/'spatial.npz',points=p,colors=c)
        process=recorder.complete(p,c,output/'spatial.npz')
        source={'snapshot':str(Path(snapshot).resolve()),'format':MULTIFRAME_FORMAT,'input_binding':binding,
            **{k:checked[k] for k in ('snapshot_sha256','bag_sha256','bag_bytes','selected_frame','verified_messages')},
            'source_scope':'sealed_one_second_specimen_not_full_acquisition'}
        if job.get('batch_ref'):source['batch_ref']=job['batch_ref']
        metadata={'id':job['id'],'label':'OS1-16 · 多帧局部建图','frame_id':FRAME,'axes':AXES,'unit':'m',
            **{k:job[k] for k in ('space_id','project_id')},'data_kind':'real_lidar_multiframe_candidate',
            'source':source,'appearance':'intensity_grayscale_not_rgb',
            'construction':{'input_frames':len(frames),'used_frames':len(frames),'remaining_frames':0,
                'sampled_input_points':input_points,'model_points':len(p),'voxel_sample_m':.05,
                'method':METHOD,'coordinate_scope':'first_lidar_anchor','config':CONFIG,
                'runtime':{'numpy':np.__version__,'scipy':scipy.__version__},
                'implementation_sha256':{str(path):digest(path) for path in (
                    Path('packages/construction/lidar_mapping.py'),Path('packages/construction/preview_lidar_mapping.py'),Path('packages/data/preview_lidar.py'))},
                'trajectory':trajectory,'wall_seconds':time.perf_counter()-start},
            'construction_process':process,'bounds_m':[p.min(axis=0).astype(float).tolist(),p.max(axis=0).astype(float).tolist()],
            'quality':{'grade':'unverified','independent_accuracy_verified':False,'semantic_annotation':'not_available'},
            'algorithm_ready':False,'real_release_ready':False,'robot_ready':False,
            'limitations':['short_sequence','estimated_lidar_poses','no_loop_closure','no_global_registration','no_deskew',
                'imu_not_used','reference_pose_not_used','clock_sync_unverified','unit_from_ros_convention',
                'no_free_space_inference','no_surface_mesh','no_semantic_objects']}
        freeze(output,metadata)
        return metadata
    except Exception:
        if recorder.value['state']=='recording':recorder.fail()
        raise
