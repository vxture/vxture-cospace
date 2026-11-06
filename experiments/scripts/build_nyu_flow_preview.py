"""Replay existing input/poses into one candidate and two derived preview views."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import numpy as np
from packages.data.nyu_rgbd import read_pnm,make_cloud,ply_bytes
from packages.construction.rgbd_tracking import transform
from packages.construction.preview_model import digest,surface_cells,PreviewModel


def main():
    p=argparse.ArgumentParser(); p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--tracking',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--candidate-id')
    p.add_argument('--input-binding',type=Path)
    p.add_argument('--freeze-only',action='store_true')
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    source=json.loads((a.snapshot/'report.json').read_bytes()); tracking=json.loads(a.tracking.read_bytes())
    if digest(a.snapshot/'report.json')!=tracking['source_report_sha256']: raise ValueError('source_mismatch')
    binding=json.loads(a.input_binding.read_bytes())['input_binding'] if a.input_binding else None
    if binding and (digest(a.snapshot/'report.json')!=binding['snapshot_sha256'] or digest(a.tracking)!=binding['tracking_sha256']):
        raise ValueError('registered_input_changed')
    pairs=[pair for pair in source['pairs'] if pair['accepted']]; poses=tracking['prefix_T_anchor_camera']
    if not 1<=len(poses)<=len(pairs): raise ValueError('invalid_prefix')
    recorder=None;process_ref=None
    if a.input_binding:
        job=json.loads(a.input_binding.read_bytes())
        if job.get('process_profile'):
            from packages.construction.build_process import Recorder
            recorder=Recorder(a.input_binding.parent/'process',job,digest(a.snapshot/'report.json'),digest(a.tracking),pairs,poses)
    points=[]; colors=[]; input_members=set()
    try:
        for pair,pose in zip(pairs,poses):
            images=[]
            for role in ['depth','rgb']:
                name=pair[role]; file=a.snapshot/'raw'/name; member=source['members'][name]
                if digest(file)!=member['sha256'] or file.stat().st_size!=member['bytes']: raise ValueError('input_integrity')
                images.append(read_pnm(file.read_bytes(),role=='depth')); input_members.add(name)
            cloud=make_cloud(*images,8); frame_points=transform(cloud[0],np.array(pose))
            points.append(frame_points); colors.append(cloud[1])
            if recorder:recorder.record(pair,pose,frame_points,cloud[1],source['members'])
    except Exception:
        if recorder:recorder.fail()
        raise
    points=np.concatenate(points); colors=np.concatenate(colors); source_count=len(points)
    # Stable first observed sample in each 5cm cell: no meshing or hole filling.
    _,ids=np.unique(np.floor(points/.05).astype(np.int64),axis=0,return_index=True)
    points=points[ids].astype(np.float32); colors=colors[ids]
    np.savez_compressed(a.output/'spatial.npz',points=points,colors=colors)
    if recorder:
        try:process_ref=recorder.complete(points,colors,a.output/'spatial.npz')
        except Exception:
            recorder.fail();raise
    if a.freeze_only:
        from packages.construction.preview_derivations import freeze
        metadata={'id':a.candidate_id,'frame_id':'first_depth_camera_anchor','axes':['right','down','forward'],'unit':'m',
            'data_kind':'real_rgbd_candidate','source':{'snapshot':str(a.snapshot),'snapshot_sha256':digest(a.snapshot/'report.json'),
                'tracking':str(a.tracking),'tracking_sha256':digest(a.tracking),'verified_image_members':len(input_members)},
            'construction':{'input_frames':len(pairs),'used_frames':len(poses),'remaining_frames':len(pairs)-len(poses),
                'sampled_input_points':source_count,'model_points':len(points),'voxel_sample_m':.05,'method':'existing_prefix_pose_accumulation_then_first_sample_per_cell'},
            'bounds_m':[points.min(axis=0).astype(float).tolist(),points.max(axis=0).astype(float).tolist()],
            'quality':{'grade':'unverified','independent_accuracy_verified':False,'semantic_annotation':'not_available'},
            'algorithm_ready':False,'real_release_ready':False,'robot_ready':False,
            'limitations':['partial_sequence','estimated_poses','no_surface_mesh','no_free_space_inference','no_semantic_objects']}
        if binding:
            metadata['source']['input_binding']=binding
            metadata.update({k:binding[k] for k in ('space_id','project_id') if k in binding})
            if batch_ref:=json.loads(a.input_binding.read_bytes()).get('batch_ref'):metadata['source']['batch_ref']=batch_ref
        if process_ref:metadata['construction_process']=process_ref
        freeze(a.output,metadata);print(json.dumps({'model_id':a.candidate_id,'stage':'model_frozen'}));return
    # Both views derive only from the frozen candidate, not separate source processing.
    with np.load(a.output/'spatial.npz',allow_pickle=False) as canonical:
        points=canonical['points']; colors=canonical['colors']
    (a.output/'human.ply').write_bytes(ply_bytes(points,colors,np.ones(len(points),bool)))
    cells=surface_cells(points,.1); np.savez_compressed(a.output/'agent.npz',cells=cells)
    sample=np.arange(0,len(points),max(1,int(np.ceil(len(points)/35000))))
    display={'points':np.round(points[sample].astype(float),4).tolist(),'colors':colors[sample].tolist(),
        'agent_points':np.round((cells+.5)*.1,4).tolist()}
    (a.output/'views.js').write_text('window.PREVIEW_VIEWS='+json.dumps(display,separators=(',',':'))+';',encoding='utf-8')
    events=[{'stage':s,'state':'completed'} for s in ['source_verified','candidate_built','human_view_derived','agent_view_derived']]
    manifest={'profile':'cospace.real-model-preview/0.1','id':a.candidate_id or 'nyu-office-preview-'+digest(a.output/'spatial.npz')[:12],
        'created_at':datetime.now(timezone.utc).isoformat(),'frame_id':'first_depth_camera_anchor',
        'axes':['right','down','forward'],'unit':'m','data_kind':'real_rgbd_candidate',
        'source':{'snapshot':str(a.snapshot),'snapshot_sha256':digest(a.snapshot/'report.json'),
                  'tracking':str(a.tracking),'tracking_sha256':digest(a.tracking),'verified_image_members':len(input_members)},
        'construction':{'input_frames':len(pairs),'used_frames':len(poses),'remaining_frames':len(pairs)-len(poses),
                        'sampled_input_points':source_count,'model_points':len(points),'voxel_sample_m':.05,
                        'method':'existing_prefix_pose_accumulation_then_first_sample_per_cell'},
        'bounds_m':[points.min(axis=0).astype(float).tolist(),points.max(axis=0).astype(float).tolist()],
        'human_view':{'path':'human.ply','source_model_sha256':digest(a.output/'spatial.npz')},
        'agent_view':{'path':'agent.npz','resolution_m':.1,'surface_cells':len(cells),
                      'source_model_sha256':digest(a.output/'spatial.npz'),'unlisted_state':'unknown'},
        'quality':{'grade':'unverified','independent_accuracy_verified':False,'semantic_annotation':'not_available'},
        'events':events,'algorithm_ready':False,'real_release_ready':False,'robot_ready':False,
        'limitations':['partial_sequence','estimated_poses','no_surface_mesh','no_free_space_inference','no_semantic_objects'],
        'members':{name:{'sha256':digest(a.output/name),'bytes':(a.output/name).stat().st_size}
                   for name in ['spatial.npz','human.ply','agent.npz','views.js']}}
    if binding:
        if a.input_binding and (batch_ref:=json.loads(a.input_binding.read_bytes()).get('batch_ref')):manifest['source']['batch_ref']=batch_ref
        manifest['source']['input_binding']=binding
        for key in ('space_id','project_id'):
            if key in binding: manifest[key]=binding[key]
    (a.output/'model.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    model=PreviewModel(a.output); surface_point=((cells[0]+.5)*.1).tolist(); unknown_point=(points.max(axis=0)+10).tolist()
    checks={'surface':model.query(surface_point),'unknown':model.query(unknown_point),
            'same_source_model':manifest['human_view']['source_model_sha256']==manifest['agent_view']['source_model_sha256']}
    if checks['surface']['state']!='surface_candidate' or checks['unknown']['state']!='unknown' or not checks['same_source_model']:
        raise ValueError('preview_flow_check')
    (a.output/'offline-checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    template=Path('experiments/templates/nyu-flow-preview.html')
    shutil.copyfile(template,a.output/'index.html')
    print(json.dumps({'model_id':manifest['id'],**manifest['construction'],'agent_cells':len(cells)}))


if __name__=='__main__': main()
