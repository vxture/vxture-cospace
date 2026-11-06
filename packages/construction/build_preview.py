"""Visualize completed immutable stages while other stages are still running."""
import json
import re
import numpy as np
from packages.data.input_preview import PreviewUnavailable,sample,bounded
from packages.lifecycle.preview_scope import scope,match


def preview(jobs,space_id,identity,kind):
    if not re.fullmatch(r'build-[A-Za-z0-9-]+',identity) or kind not in ('model','human','agent'):
        raise PreviewUnavailable('build_preview_invalid_request')
    ownership=scope(jobs.directory,space_id)
    try:
        # Do not poll, launch or compose work as a side effect of previewing.
        job=json.loads((jobs.root/identity/'job.json').read_bytes());match(job,ownership)
        ref=job.get('frozen_model')
        if not ref:raise PreviewUnavailable('build_preview_stage_not_ready')
        saved,_=jobs.split.frozen(ref);metadata=saved['metadata'];match(metadata,ownership)
        if metadata.get('source',{}).get('input_binding')!=job.get('input_binding'):
            raise ValueError('build_preview_input_mismatch')
        task_id=None
        if kind!='model':
            task_ref=job.get('view_tasks',{}).get(kind)
            if not task_ref:raise PreviewUnavailable('build_preview_stage_not_ready')
            _,task=jobs.split.task(task_ref)
            if task['state']!='succeeded':raise PreviewUnavailable('build_preview_stage_not_ready')
            match(task,ownership)
            directory,view=jobs.split.manifest(task_ref,ref,kind);match(view,ownership);task_id=task['id']
        if kind=='agent':
            with np.load(directory/view['view']['path'],allow_pickle=False) as arrays:points=(arrays['cells']+.5)*view['view']['resolution_m']
            colors=np.full(points.shape,160,dtype=np.uint8)
        else:
            # A verified human task derives exactly these fixed points and colors.
            with np.load(jobs.root/ref['job_id']/'frozen/spatial.npz',allow_pickle=False) as arrays:
                points=arrays['points'];colors=arrays['colors']
        appearance=metadata.get('appearance') or ('intensity_grayscale_not_rgb' if metadata.get('data_kind')=='real_lidar_sensor_local_candidate' else 'source_rgb')
        return bounded({'profile':'cospace.build-preview/0.1','space_id':space_id,'job_id':identity,
            'input_id':job['input_id'],'kind':kind,'task_id':task_id,'source_sha256':ref['source_model_sha256'],
            'manifest_sha256':ref['manifest_sha256'],'frame_id':metadata['frame_id'],'axes':metadata['axes'],'unit':metadata['unit'],
            'appearance':'surface_cells' if kind=='agent' else appearance,
            'quality':'unverified','robot_ready':False,'limitations':['display_sample_only','not_a_publication','scene_alignment_unverified'],
            **sample(points,colors)})
    except (PreviewUnavailable,PermissionError):raise
    except (OSError,ValueError,KeyError,TypeError) as exc:raise PreviewUnavailable('build_preview_evidence_unavailable') from exc
