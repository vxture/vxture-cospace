"""Read-only bounded display samples. Never used as construction input."""
import json
import numpy as np
from packages.data.input_descriptions import InputDescriptions
from packages.data.preview_pointcloud import read_cloud,FORMAT

MAX_DISPLAY_POINTS=10_000
MAX_RESPONSE_BYTES=2*1024*1024


class PreviewUnavailable(ValueError):pass


def sample(points,colors):
    if (points.ndim!=2 or points.shape[1]!=3 or not len(points) or colors.shape!=points.shape
            or not np.isfinite(points).all() or not np.isfinite(colors).all()
            or np.any(colors<0) or np.any(colors>255)):
        raise PreviewUnavailable('preview_geometry_invalid')
    stride=max(1,(len(points)+MAX_DISPLAY_POINTS-1)//MAX_DISPLAY_POINTS)
    return {'point_count':len(points),'bounds':[points.min(axis=0).astype(float).tolist(),points.max(axis=0).astype(float).tolist()],
            'sampling':{'method':'file_index_stride','stride':stride,'limit':MAX_DISPLAY_POINTS,'count':len(points[::stride])},
            'points':points[::stride].astype(float).tolist(),'colors':colors[::stride].astype(int).tolist()}


def bounded(value):
    if len(json.dumps(value,separators=(',',':'),allow_nan=False).encode())>MAX_RESPONSE_BYTES:
        raise PreviewUnavailable('preview_response_budget')
    return value


def preview(catalog,identity,space_id):
    record=InputDescriptions(catalog).original(identity,space_id)
    if record['format']!=FORMAT:raise PreviewUnavailable('input_preview_format_unsupported')
    try:
        checked,points,colors,_=read_cloud(record['snapshot'])
        if record.get('coordinate_revision'):
            from packages.data.input_coordinates import interpret
            checked=interpret(checked,record)
        if any(record.get(k)!=v for k,v in checked.items()):raise ValueError('binding')
        return bounded({'profile':'cospace.input-preview/0.1','space_id':space_id,'input_id':identity,'format':FORMAT,
            'snapshot_sha256':checked['snapshot_sha256'],'source_sha256':checked['cloud_sha256'],
            'unit':'m','frame_id':checked['frame_id'],'axes':checked['axes'],'appearance':checked['appearance'],
            'quality':'unverified','robot_ready':False,'limitations':['display_sample_only','scene_alignment_unverified'],
            **sample(points,colors)})
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise PreviewUnavailable('input_preview_evidence_unavailable') from exc
