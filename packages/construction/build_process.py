"""Job-owned, atomic frame evidence; readers never poll or launch construction."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import zipfile
import numpy as np
from packages.construction.preview_model import digest
from packages.data.input_preview import PreviewUnavailable, sample, bounded
from packages.lifecycle.preview_scope import scope, match

PROFILE = 'cospace.build-process/0.1'
MAX_FRAMES = 500
MAX_POINTS = 2_500_000
MAX_STORED = 128 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    # Windows readers/virus scanners may briefly deny replacing an open file.
    # Keep the last complete index visible and bound retries to under one second.
    for attempt in range(20):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 19:raise
            time.sleep(min(.005*(attempt+1), .05))


def matrix(value):
    a = np.asarray(value, dtype=float)
    if (a.shape != (4, 4) or not np.isfinite(a).all() or
        not np.allclose(a[3], [0, 0, 0, 1], atol=1e-8) or
        not np.allclose(a[:3, :3].T @ a[:3, :3], np.eye(3), atol=1e-4) or
        not np.isclose(np.linalg.det(a[:3, :3]), 1, atol=1e-4)):
        raise ValueError('process_pose_invalid')
    return a


class Recorder:
    def __init__(self, root, job, source, tracking, pairs, poses):
        self.root = Path(root); self.root.mkdir()
        if not 1 <= len(poses) <= len(pairs) <= MAX_FRAMES:
            raise ValueError('process_frame_budget')
        self.seen = {}; self.points = []; self.colors = []
        self.value = {'profile': PROFILE, 'job_id': job['id'], 'space_id': job['space_id'],
            'project_id': job['project_id'], 'input_id': job['input_id'], 'input_binding': job['input_binding'],
            'snapshot_sha256': source, 'tracking_sha256': tracking, 'revision': 0, 'state': 'recording',
            'frame_id': 'first_depth_camera_anchor', 'axes': ['right', 'down', 'forward'], 'unit': 'm',
            'input_frames': len(pairs), 'available_frames': len(poses), 'processed_frames': 0,
            'excluded_frames': len(pairs)-len(poses), 'excluded_reason': 'no_existing_prefix_pose',
            'source_clock': 'filename_time_unverified_utc', 'origin_time_us': pairs[0]['depth_time_us'],
            'point_count': 0, 'frames': [], 'updated_at': now(), 'source_model_sha256': None}
        write(self.root/'process.json', self.value)

    def record(self, pair, pose, points, colors, members):
        self.append(pair['depth_time_us'],pose,points,colors,{
            'depth':pair['depth'],'rgb':pair['rgb'],
            'depth_sha256':members[pair['depth']]['sha256'],'rgb_sha256':members[pair['rgb']]['sha256']})

    def append(self, stamp, pose, points, colors, evidence):
        matrix(pose)
        if (points.ndim!=2 or points.shape[1]!=3 or colors.shape!=points.shape or
            colors.dtype!=np.uint8 or not np.isfinite(points).all()):
            raise ValueError('process_arrays_invalid')
        index = len(self.value['frames'])
        if type(stamp) is not int or not 0<=stamp<=2**53-1 or stamp < self.value['origin_time_us'] or (
            index and stamp <= self.value['frames'][-1]['source_time_us']):
            raise ValueError('process_time_invalid')
        if index >= self.value['available_frames'] or not np.isfinite(points).all():
            raise ValueError('process_frame_invalid')
        selected = []
        # Match the existing float64 floor/first-observation rule before float32 storage.
        cells = np.floor(points/.05)
        if np.max(np.abs(cells), initial=0) > 2**52:
            raise ValueError('process_coordinates_invalid')
        for i, cell in enumerate(cells):
            key = tuple(cell.astype(np.int64))
            if key not in self.seen:
                self.seen[key] = len(self.seen); selected.append(i)
        if len(self.seen) > MAX_POINTS:
            raise ValueError('process_point_budget')
        p = points[selected].astype(np.float32); c = colors[selected].astype(np.uint8)
        self.points.append(p); self.colors.append(c)
        name = f'frame-{index:04d}.npz'; target = self.root/name
        with target.with_suffix('.tmp').open('wb') as stream:
            np.savez_compressed(stream, points=p, colors=c)
        target.with_suffix('.tmp').replace(target)
        frame = {'index': index, 'source_time_us': stamp, 'relative_time_us': stamp-self.value['origin_time_us'],
            'pose': np.asarray(pose).tolist(), **evidence,
            'input_points': len(points), 'added_points': len(p), 'point_count': len(self.seen),
            'chunk': name, 'sha256': digest(target), 'bytes': target.stat().st_size, 'processed_at': now()}
        self.value['frames'].append(frame)
        self.value.update(processed_frames=index+1, point_count=len(self.seen), revision=index+1, updated_at=now())
        write(self.root/'process.json', self.value)

    def complete(self, points, colors, model):
        if not len(points) or len(self.value['frames']) != self.value['available_frames']:
            raise ValueError('process_incomplete')
        p = np.concatenate(self.points); c = np.concatenate(self.colors)
        order = np.array([self.seen[k] for k in sorted(self.seen)], dtype=np.int64)
        if not np.array_equal(p[order], points) or not np.array_equal(c[order], colors):
            raise ValueError('process_final_geometry_mismatch')
        self.value.update(state='completed', revision=self.value['revision']+1, updated_at=now(),
                          source_model_sha256=digest(model))
        write(self.root/'process.json', self.value)
        return {'profile': PROFILE, 'job_id': self.value['job_id'], 'sha256': digest(self.root/'process.json')}

    def fail(self):
        self.value.update(state='failed', revision=self.value['revision']+1, updated_at=now())
        write(self.root/'process.json', self.value)


def read_process(jobs, space_id, identity):
    if not re.fullmatch(r'build-[A-Za-z0-9-]+', identity):
        raise PreviewUnavailable('build_process_invalid_request')
    ownership = scope(jobs.directory, space_id)
    try:
        root = jobs.root/identity; job = json.loads((root/'job.json').read_bytes()); match(job, ownership)
        if not job.get('process_profile'):
            return {'profile': PROFILE, 'supported': False, 'space_id': space_id, 'job_id': identity,
                    'input_id': job['input_id'], 'reason': 'process_not_recorded'}
        if job['process_profile']=='cospace.lidar-build-process/0.1':
            from packages.construction.lidar_process import read_lidar_process
            return read_lidar_process(jobs,job,ownership)
        if job['process_profile'] != PROFILE:
            raise ValueError('process_profile_invalid')
        path = root/'process/process.json'
        if not path.exists():
            if job['state'] in ('queued', 'running'):
                return {'profile': PROFILE, 'supported': True, 'ready': False, 'space_id': space_id,
                        'job_id': identity, 'input_id': job['input_id'], 'job_state': job['state']}
            raise ValueError('process_missing')
        if path.stat().st_size > 1024*1024:
            raise ValueError('process_index_budget')
        raw = path.read_bytes(); value = json.loads(raw); match(value, ownership)
        binding = job['input_binding']
        if (value['profile'] != PROFILE or value['job_id'] != identity or value['input_id'] != job['input_id'] or
            value['input_binding'] != binding or value['snapshot_sha256'] != binding['snapshot_sha256'] or
            value['tracking_sha256'] != binding['tracking_sha256'] or value['frame_id'] != 'first_depth_camera_anchor' or
            value['axes'] != ['right', 'down', 'forward'] or value['unit'] != 'm' or
            value['state'] not in ('recording', 'completed', 'failed')):
            raise ValueError('process_binding_mismatch')
        frames = value['frames']; count = value['processed_frames']; available = value['available_frames']
        if (type(count) is not int or not 0 <= count <= available <= value['input_frames'] <= MAX_FRAMES or
            available < 1 or count != len(frames) or value['excluded_frames'] != value['input_frames']-available or
            value['source_clock'] != 'filename_time_unverified_utc' or
            value['revision'] != count+(value['state'] != 'recording')):
            raise ValueError('process_frames_invalid')
        if value['state'] == 'completed' and count != available:
            raise ValueError('process_incomplete')
        ref = job.get('frozen_model')
        if ref:
            saved, _ = jobs.split.frozen(ref)
            if (saved['metadata'].get('construction_process') != {'profile': PROFILE, 'job_id': identity,
                    'sha256': __import__('hashlib').sha256(raw).hexdigest()} or
                value['source_model_sha256'] != ref['source_model_sha256'] or value['state'] != 'completed'):
                raise ValueError('process_frozen_mismatch')
        points = []; colors = []; first = []; total = 0; stored = 0
        for i, f in enumerate(frames):
            matrix(f['pose'])
            if (f['index'] != i or f['chunk'] != f'frame-{i:04d}.npz' or
                type(f['source_time_us']) is not int or f['relative_time_us'] != f['source_time_us']-value['origin_time_us'] or
                f['relative_time_us'] < 0 or i == 0 and f['relative_time_us'] != 0 or
                i and f['source_time_us'] <= frames[i-1]['source_time_us']):
                raise ValueError('process_frame_invalid')
            for key in ('sha256', 'depth_sha256', 'rgb_sha256'):
                if not re.fullmatch('[a-f0-9]{64}', f[key]): raise ValueError('process_digest_invalid')
            chunk = path.parent/f['chunk']; stored += f['bytes']
            if (stored > MAX_STORED or f['bytes'] != chunk.stat().st_size or digest(chunk) != f['sha256']):
                raise ValueError('process_chunk_integrity')
            with zipfile.ZipFile(chunk) as archive:
                if sum(n.file_size for n in archive.infolist()) > 16*1024*1024:
                    raise ValueError('process_chunk_budget')
            with np.load(chunk, allow_pickle=False) as arrays:
                if set(arrays.files) != {'points', 'colors'}:raise ValueError('process_arrays_invalid')
                p = arrays['points']; c = arrays['colors']
            if (p.ndim != 2 or p.shape[1] != 3 or p.dtype != np.float32 or c.dtype != np.uint8 or
                p.shape != c.shape or not np.isfinite(p).all() or len(p) != f['added_points'] or
                f['input_points'] < len(p)):
                raise ValueError('process_arrays_invalid')
            total += len(p)
            if total != f['point_count'] or total > MAX_POINTS:raise ValueError('process_point_budget')
            points.append(p); colors.append(c); first.extend([i]*len(p))
        if total != value['point_count']:raise ValueError('process_count_invalid')
        state = value['state']
        if state == 'recording' and job['state'] in ('failed', 'interrupted'):state = job['state']
        response = {k: value[k] for k in ('profile', 'space_id', 'job_id', 'input_id', 'snapshot_sha256',
            'tracking_sha256', 'revision', 'frame_id', 'axes', 'unit', 'input_frames', 'available_frames',
            'processed_frames', 'excluded_frames', 'excluded_reason', 'source_clock', 'updated_at', 'source_model_sha256')}
        response.update(supported=True, ready=True, state=state, job_state=job['state'],
                        quality='unverified', robot_ready=False, appearance='source_rgb',
                        limitations=['estimated_camera_poses', 'prerecorded_source', 'not_live_acquisition', 'display_sample_only'],
                        frames=[{k: f[k] for k in ('index', 'relative_time_us', 'source_time_us', 'pose', 'input_points',
                            'added_points', 'point_count', 'processed_at', 'depth_sha256', 'rgb_sha256')} for f in frames])
        if total:
            geometry = sample(np.concatenate(points), np.concatenate(colors))
            response.update(geometry, first_seen_frames=first[::geometry['sampling']['stride']])
        else:
            response.update(point_count=0, bounds=[[0,0,0],[0,0,0]], points=[], colors=[], first_seen_frames=[],
                            sampling={'method':'file_index_stride', 'stride':1, 'count':0, 'limit':10000})
        return bounded(response)
    except (PermissionError, PreviewUnavailable):
        raise
    except (OSError, ValueError, KeyError, TypeError, OverflowError, zipfile.BadZipFile) as exc:
        raise PreviewUnavailable('build_process_evidence_unavailable') from exc
