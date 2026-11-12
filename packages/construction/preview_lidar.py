"""Derive two preview views from one frozen sensor-local LiDAR frame."""
from packages.views.viewer_entry import write_viewer_entry
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import numpy as np
from packages.data.preview_lidar import read_specimen,FORMAT
from packages.construction.preview_model import PreviewModel,digest,surface_cells


def build(snapshot,output,identity,binding=None,*,freeze_only=False,batch_ref=None):
    checked,points,intensity=read_specimen(snapshot)
    if binding is not None and (binding.get('format')!=FORMAT or any(binding.get(k)!=v for k,v in checked.items())):
        raise ValueError('registered_input_changed')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    # Intensity-derived grayscale is a display attribute, not camera RGB.
    lo,hi=float(intensity.min()),float(intensity.max())
    shade=np.rint(60+180*(intensity-lo)/(hi-lo if hi>lo else 1)).astype(np.uint8)
    colors=np.repeat(shade[:,None],3,axis=1)
    np.savez_compressed(output/'spatial.npz',points=points,intensity=intensity,colors=colors)
    if freeze_only:
        from packages.construction.preview_derivations import freeze
        source={'snapshot':str(Path(snapshot).resolve()),**{k:checked[k] for k in ('snapshot_sha256','bag_sha256','bag_bytes','selected_frame','verified_messages')},
            'format':FORMAT,'source_scope':'sealed_one_second_specimen_not_full_acquisition'}
        if binding is not None:source['input_binding']=binding
        if batch_ref:source['batch_ref']=batch_ref
        metadata={'id':identity,'label':'OS1-16 · 单帧局部点云','frame_id':checked['frame_id'],'axes':['sensor_x','sensor_y','sensor_z'],
            'unit':'m','data_kind':'real_lidar_sensor_local_candidate','source':source,
            **{k:binding[k] for k in ('space_id','project_id') if binding and k in binding},
            'construction':{'input_frames':checked['input_frames'],'used_frames':1,'remaining_frames':checked['input_frames']-1,
                'model_points':len(points),'method':'single_sensor_frame_no_registration','coordinate_scope':'sensor_local',
                'excluded_frames_reason':'single_frame_workflow_validation_by_design','filtered_invalid_returns':True},
            'bounds_m':[points.min(axis=0).astype(float).tolist(),points.max(axis=0).astype(float).tolist()],
            'quality':{'grade':'unverified','independent_accuracy_verified':False,'semantic_annotation':'not_available'},
            'algorithm_ready':False,'real_release_ready':False,'robot_ready':False,
            'limitations':['single_frame','sensor_local_frame','no_global_registration','no_SLAM','no_deskew','unit_from_ros_convention',
                'no_free_space_inference','no_surface_mesh','no_semantic_objects','reference_pose_not_used']}
        freeze(output,metadata);return metadata
    with np.load(output/'spatial.npz',allow_pickle=False) as frozen:
        points=frozen['points'];colors=frozen['colors']
    vertices=np.empty(len(points),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
    for i,name in enumerate(('x','y','z')):vertices[name]=points[:,i]
    for i,name in enumerate(('red','green','blue')):vertices[name]=colors[:,i]
    header=('ply\nformat binary_little_endian 1.0\ncomment sensor-local XYZ unit_m; intensity grayscale; no registration\n'
        f'element vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode('ascii')
    (output/'human.ply').write_bytes(header+vertices.tobytes())
    cells=surface_cells(points,.1);np.savez_compressed(output/'agent.npz',cells=cells)
    display={'points':np.round(points.astype(float),4).tolist(),'colors':colors.tolist(),
             'agent_points':np.round((cells+.5)*.1,4).tolist()}
    (output/'views.js').write_text('window.PREVIEW_VIEWS='+json.dumps(display,separators=(',',':'))+';',encoding='utf-8')
    source={'snapshot':str(Path(snapshot).resolve()),**{k:checked[k] for k in ('snapshot_sha256','bag_sha256','bag_bytes','selected_frame','verified_messages')},
            'format':FORMAT,'source_scope':'sealed_one_second_specimen_not_full_acquisition'}
    if binding is not None:source['input_binding']=binding
    ownership={k:binding[k] for k in ('space_id','project_id') if binding and k in binding}
    model_sha=digest(output/'spatial.npz')
    manifest={'profile':'cospace.real-model-preview/0.1','id':identity,'label':'OS1-16 · 单帧局部点云',
        'created_at':datetime.now(timezone.utc).isoformat(),'frame_id':checked['frame_id'],'axes':['sensor_x','sensor_y','sensor_z'],
        'unit':'m','data_kind':'real_lidar_sensor_local_candidate','source':source,**ownership,
        'construction':{'input_frames':checked['input_frames'],'used_frames':1,'remaining_frames':checked['input_frames']-1,
            'model_points':len(points),'method':'single_sensor_frame_no_registration','coordinate_scope':'sensor_local',
            'excluded_frames_reason':'single_frame_workflow_validation_by_design','filtered_invalid_returns':True},
        'bounds_m':[points.min(axis=0).astype(float).tolist(),points.max(axis=0).astype(float).tolist()],
        'human_view':{'path':'human.ply','source_model_sha256':model_sha,'appearance':'intensity_grayscale_not_rgb'},
        'agent_view':{'path':'agent.npz','resolution_m':.1,'surface_cells':len(cells),'source_model_sha256':model_sha,'unlisted_state':'unknown'},
        'quality':{'grade':'unverified','independent_accuracy_verified':False,'semantic_annotation':'not_available'},
        'events':[{'stage':s,'state':'completed'} for s in ('source_verified','candidate_built','human_view_derived','agent_view_derived')],
        'algorithm_ready':False,'real_release_ready':False,'robot_ready':False,
        'limitations':['single_frame','sensor_local_frame','no_global_registration','no_SLAM','no_deskew','unit_from_ros_convention',
            'no_free_space_inference','no_surface_mesh','no_semantic_objects','reference_pose_not_used'],
        'members':{name:{'sha256':digest(output/name),'bytes':(output/name).stat().st_size} for name in ('spatial.npz','human.ply','agent.npz','views.js')}}
    (output/'model.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    current=PreviewModel(output)
    checks={'surface':current.query(((cells[0]+.5)*.1).tolist()),
            'unknown':current.query(((np.array([cells[:,0].max()+2,0,0])+.5)*.1).tolist()),'same_source_model':True}
    assert checks['surface']['state']=='surface_candidate' and checks['unknown']['state']=='unknown'
    (output/'offline-checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    write_viewer_entry(output,manifest)
    return manifest
