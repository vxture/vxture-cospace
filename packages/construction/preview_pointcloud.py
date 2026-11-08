"""Freeze declared existing point coordinates; no registration or reconstruction."""
from pathlib import Path
import numpy as np
from packages.data.preview_pointcloud import read_cloud,FORMAT
from packages.data.preview_pointcloud import source_receipt
from packages.construction.preview_derivations import freeze


def build(snapshot,output,identity,binding=None,*,batch_ref=None,build_admission=None):
    checked,points,colors,doc=read_cloud(snapshot)
    if binding and binding.get('coordinate_revision'):
        from packages.data.input_coordinates import interpret
        checked=interpret(checked,binding)
    if binding is not None and (binding.get('format')!=FORMAT or any(binding.get(k)!=v for k,v in checked.items())):
        raise ValueError('registered_input_changed')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(output/'spatial.npz',points=points,colors=colors)
    source={'format':FORMAT,'snapshot_sha256':checked['snapshot_sha256'],'cloud_sha256':checked['cloud_sha256'],
            'source_scope':'declared_existing_pointcloud','provenance':doc['provenance']}
    if doc.get('source_receipt_path'):source['source_receipt']=source_receipt(snapshot,doc)
    if doc.get('composition_path'):
        from packages.data.pointcloud_composition import read_composition
        source['composition']=read_composition(snapshot,doc)
    if binding is not None:source['input_binding']=binding
    if batch_ref:source['batch_ref']=batch_ref
    if build_admission is not None:
        from packages.construction.build_admission import validate
        validate(build_admission,binding)
        if build_admission['job_id'] != identity:
            raise ValueError('build_admission_job_mismatch')
        source['build_admission']=build_admission
    metadata={'id':identity,'label':binding['label'] if binding else '已有点云',
        'frame_id':checked['frame_id'],'axes':checked['axes'],'unit':'m',
        'data_kind':'existing_pointcloud_candidate','appearance':checked['appearance'],'source':source,
        **{k:binding[k] for k in ('space_id','project_id') if binding and k in binding},
        'construction':{'input_frames':1,'used_frames':1,'model_points':len(points),
            'method':'normalize_declared_pointcloud','coordinate_scope':checked['scope'],
            'scene_alignment':'unverified','coordinate_transform_applied':False},
        'bounds_m':[points.min(axis=0).astype(float).tolist(),points.max(axis=0).astype(float).tolist()],
        'quality':{'grade':'unverified','independent_accuracy_verified':False,'semantic_annotation':'not_available'},
        'algorithm_ready':False,'real_release_ready':False,'robot_ready':False,
        'limitations':['source_declared_coordinates','alignment_unverified','no_registration','no_SLAM',
            'no_free_space_inference','no_surface_mesh','no_semantic_objects','source_provenance_declared_not_reverified']}
    freeze(output,metadata)
    return metadata
