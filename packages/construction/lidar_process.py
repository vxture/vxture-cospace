"""Actual laser-derived poses and added model points, using the common chunk writer."""
import hashlib
import json
import re
import zipfile
import numpy as np
from packages.construction.build_process import Recorder,write,now,matrix,MAX_STORED,MAX_POINTS
from packages.construction.preview_model import digest
from packages.data.input_preview import sample,bounded
from packages.lifecycle.preview_scope import match

PROFILE='cospace.lidar-build-process/0.1'
FRAME='first_lidar_anchor'
AXES=['sensor_x','sensor_y','sensor_z']


class LidarRecorder(Recorder):
    def __init__(self,root,job,source):
        from pathlib import Path
        self.root=Path(root);self.root.mkdir();self.seen={};self.points=[];self.colors=[]
        count=source['input_frames']
        if not 2<=count<=20:raise ValueError('lidar_sequence_frame_budget')
        self.value={'profile':PROFILE,'job_id':job['id'],'space_id':job['space_id'],
            'project_id':job['project_id'],'input_id':job['input_id'],'input_binding':job['input_binding'],
            'snapshot_sha256':source['snapshot_sha256'],'bag_sha256':source['bag_sha256'],
            'revision':0,'state':'recording','frame_id':FRAME,'axes':AXES,'unit':'m',
            'input_frames':count,'available_frames':count,'processed_frames':0,'excluded_frames':0,
            'excluded_reason':None,'source_clock':'ros_header_unverified_utc',
            'origin_time_us':source['selected_frame']['header_ns']//1000,
            'point_count':0,'frames':[],'updated_at':now(),'source_model_sha256':None,
            'rejection':None}
        write(self.root/'process.json',self.value)

    def record_scan(self,frame,pose,points,colors,registration):
        evidence=frame['evidence']
        self.append(evidence['header_ns']//1000,pose,points,colors,
            {'message_sha256':evidence['sha256'],'header_ns':str(evidence['header_ns']),
             'recorded_ns':str(evidence['recorded_ns']),'registration':registration})

    def reject(self,index,result):
        self.value['rejection']={'index':index,'registration':result}
        self.fail()

    def complete(self,points,colors,model):
        ref=super().complete(points,colors,model)
        return ref|{'profile':PROFILE}


def read_lidar_process(jobs,job,ownership):
    identity=job['id'];path=jobs.root/identity/'process/process.json'
    base={'profile':PROFILE,'space_id':job['space_id'],'job_id':identity,'input_id':job['input_id'],'supported':True}
    if not path.exists() and job['state'] in ('queued','running'):return base|{'ready':False,'job_state':job['state']}
    if path.stat().st_size>1024*1024:raise ValueError('process_index_budget')
    raw=path.read_bytes();v=json.loads(raw);match(v,ownership);binding=job['input_binding']
    if (binding['format']!='ros1_lidar_multiframe_icp' or v['profile']!=PROFILE or v['job_id']!=identity or
        v['input_id']!=job['input_id'] or v['input_binding']!=binding or v['snapshot_sha256']!=binding['snapshot_sha256'] or
        v['bag_sha256']!=binding['bag_sha256'] or v['frame_id']!=FRAME or v['axes']!=AXES or v['unit']!='m' or
        v['source_clock']!='ros_header_unverified_utc' or v['state'] not in ('recording','completed','failed')):
        raise ValueError('process_binding_mismatch')
    frames=v['frames'];count=len(frames);available=binding['input_frames']
    if (not 2<=available<=20 or v['input_frames']!=available or v['available_frames']!=available or
        v['processed_frames']!=count or not 0<=count<=available or v['excluded_frames']!=0 or
        v['revision']!=count+(v['state']!='recording') or v['state']=='completed' and count!=available):
        raise ValueError('process_frames_invalid')
    ref=job.get('frozen_model')
    if ref:
        frozen,_=jobs.split.frozen(ref)
        if (frozen['metadata'].get('construction_process')!={'profile':PROFILE,'job_id':identity,'sha256':hashlib.sha256(raw).hexdigest()} or
            v['source_model_sha256']!=ref['source_model_sha256'] or v['state']!='completed' or
            frozen['metadata']['construction']['trajectory']!=[
                {k:f[k] for k in ('index','header_ns','recorded_ns','message_sha256','pose','registration')} for f in frames]):
            raise ValueError('process_frozen_mismatch')
    points=[];colors=[];first=[];total=0;stored=0
    for i,f in enumerate(frames):
        matrix(f['pose']);source=binding['sequence_frames'][i]
        if (f['index']!=i or f['chunk']!=f'frame-{i:04d}.npz' or f['header_ns']!=str(source['header_ns']) or
            f['recorded_ns']!=str(source['recorded_ns']) or f['message_sha256']!=source['sha256'] or
            f['source_time_us']!=source['header_ns']//1000 or f['relative_time_us']!=f['source_time_us']-v['origin_time_us'] or
            f['relative_time_us']<0 or (i==0 and f['relative_time_us']!=0) or
            (i and f['source_time_us']<=frames[i-1]['source_time_us']) or
            (i and not f['registration']['accepted']) or (i==0 and not np.array_equal(f['pose'],np.eye(4)))):
            raise ValueError('process_frame_invalid')
        if i:
            relative=matrix(f['registration']['T_previous_current'])
            if not np.allclose(np.array(frames[i-1]['pose'])@relative,f['pose'],atol=1e-8):raise ValueError('process_pose_chain')
        chunk=path.parent/f['chunk'];stored+=f['bytes']
        if (not re.fullmatch('[a-f0-9]{64}',f['sha256']) or stored>MAX_STORED or chunk.stat().st_size!=f['bytes'] or digest(chunk)!=f['sha256']):
            raise ValueError('process_chunk_integrity')
        with zipfile.ZipFile(chunk) as z:
            if sum(n.file_size for n in z.infolist())>16*1024*1024:raise ValueError('process_chunk_budget')
        with np.load(chunk,allow_pickle=False) as a:
            if set(a.files)!={'points','colors'}:raise ValueError('process_arrays_invalid')
            p=a['points'];c=a['colors']
        if p.dtype!=np.float32 or c.dtype!=np.uint8 or p.ndim!=2 or p.shape[1]!=3 or c.shape!=p.shape or not np.isfinite(p).all() or len(p)!=f['added_points'] or f['input_points']<len(p):
            raise ValueError('process_arrays_invalid')
        total+=len(p)
        if total!=f['point_count'] or total>MAX_POINTS:raise ValueError('process_point_budget')
        points.append(p);colors.append(c);first.extend([i]*len(p))
    if total!=v['point_count']:raise ValueError('process_count_invalid')
    result=base|{k:v[k] for k in ('snapshot_sha256','bag_sha256','revision','frame_id','axes','unit','input_frames',
        'available_frames','processed_frames','excluded_frames','excluded_reason','source_clock','updated_at','source_model_sha256','rejection')}
    result.update(ready=True,state=job['state'] if v['state']=='recording' and job['state'] in ('failed','interrupted') else v['state'],
        job_state=job['state'],quality='unverified',robot_ready=False,appearance='intensity_grayscale_not_rgb',
        limitations=['estimated_lidar_poses','prerecorded_source','not_live_acquisition','no_loop_closure','no_deskew','display_sample_only'],
        frames=[{k:f[k] for k in ('index','relative_time_us','source_time_us','pose','input_points','added_points','point_count',
            'processed_at','header_ns','recorded_ns','message_sha256','registration')} for f in frames])
    if total:
        geometry=sample(np.concatenate(points),np.concatenate(colors))
        result.update(geometry,first_seen_frames=first[::geometry['sampling']['stride']])
    else:result.update(point_count=0,bounds=[[0,0,0],[0,0,0]],points=[],colors=[],first_seen_frames=[],sampling={'method':'file_index_stride','stride':1,'count':0,'limit':10000})
    return bounded(result)
