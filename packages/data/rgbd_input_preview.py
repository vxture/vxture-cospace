"""Read-only, bounded NYU image/pose display; never a construction input."""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

import numpy as np

from packages.data.input_descriptions import InputDescriptions
from packages.data.input_preview import PreviewUnavailable
from packages.data.nyu_rgbd import read_pnm, timestamp_us

PROFILE = 'cospace.rgbd-input-preview/0.1'
FORMAT = 'nyu_rgbd_with_existing_poses'
RULE = 'nyu-depth-metres-nearest-rgba/0.1'
MAX_INDEX = 1024 * 1024
MAX_FRAME = 2 * 1024 * 1024
MAX_MEMBER = 2_000_000
SAFE = 2**53-1


def encoded(value, limit):
    if len(json.dumps(value, separators=(',', ':'), allow_nan=False).encode()) > limit:
        raise ValueError('response_budget')
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def read_checked(path, expected, size=None, limit=MAX_MEMBER):
    if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('digest')
    with Path(path).open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit or size is not None and len(raw) != size or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('source_integrity')
    return raw


def integer(value, signed=False):
    return type(value) is int and (-SAFE if signed else 0) <= value <= SAFE


def pose(value):
    m = np.asarray(value, dtype=float)
    if (m.shape != (4, 4) or not np.isfinite(m).all() or not np.allclose(m[3], [0, 0, 0, 1], atol=1e-8, rtol=0)
            or not np.allclose(m[:3, :3].T @ m[:3, :3], np.eye(3), atol=1e-4, rtol=0)
            or abs(np.linalg.det(m[:3, :3])-1) > 1e-4):
        raise ValueError('pose')
    return m.tolist()


def _directory(catalog, identity, space_id):
    record = InputDescriptions(catalog).original(identity, space_id)
    if record['format'] != FORMAT:
        raise ValueError('format_unsupported')
    source = json.loads(read_checked(Path(record['snapshot'])/'report.json', record['snapshot_sha256']), object_pairs_hook=unique)
    tracking = json.loads(read_checked(record['tracking'], record['tracking_sha256']), object_pairs_hook=unique)
    if source['schema_version'] != 'cospace.nyu-short-scene/0.1' or tracking['source_report_sha256'] != record['snapshot_sha256']:
        raise ValueError('manifest_binding')
    pairs = source['pairs']
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 500 or any(not isinstance(p,dict) or type(p.get('accepted')) is not bool for p in pairs):
        raise ValueError('frame_budget')
    accepted = [(i, p) for i, p in enumerate(pairs) if p['accepted']]
    matrices = tracking['prefix_T_anchor_camera']
    if (not isinstance(matrices, list) or not 1 <= len(matrices) <= len(accepted)
            or len(accepted) != record['input_frames'] or len(matrices) != record['used_frames']):
        raise ValueError('frame_counts')
    matrices = [pose(m) for m in matrices]
    frames = []
    for index, (source_index, pair) in enumerate(accepted):
        frame = {'index': index, 'source_index': source_index, 'pose': matrices[index] if index < len(matrices) else None}
        for role, suffix in [('depth', 'pgm'), ('rgb', 'ppm')]:
            name = pair[role]
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.'+suffix, name) or len(name) > 200:
                raise ValueError('member_name')
            member = source['members'][name]
            if (not integer(member['bytes']) or not 0 < member['bytes'] <= MAX_MEMBER
                    or not isinstance(member['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', member['sha256'])):
                raise ValueError('member_declaration')
            frame[role] = name
            frame[role+'_sha256'] = member['sha256']
        stamp = pair.get('depth_time_us')
        if stamp is None:
            try:
                stamp = timestamp_us(pair['depth'])
            except ValueError:
                stamp = None
        if stamp is not None and not integer(stamp):
            raise ValueError('source_time')
        delta = pair.get('rgb_minus_depth_us')
        if delta is not None and not integer(delta, signed=True):
            raise ValueError('pair_time')
        frame.update(source_time_us=stamp, pair_delta_us=delta)
        frames.append(frame)
    times = [f['source_time_us'] for f in frames]
    timed = all(t is not None for t in times)
    if timed and any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('frame_order')
    for frame in frames:
        frame['relative_time_us'] = frame['source_time_us']-times[0] if timed else None
    value = {'profile': PROFILE, 'space_id': space_id, 'input_id': identity,
             'snapshot_sha256': record['snapshot_sha256'], 'tracking_sha256': record['tracking_sha256'],
             'input_frames': len(frames), 'pose_frames': len(matrices), 'frames': frames,
             'source_clock': 'filename_time_unverified_utc' if source.get('clock') == 'filename_time_unverified_utc' else 'unverified',
             'frame_id': 'first_depth_camera_anchor', 'axes': ['right', 'down', 'forward'], 'unit': 'm',
             'quality': 'unverified', 'robot_ready': False, 'payload_checked': False,
             'limitations': ['recorded_rgbd', 'estimated_poses', 'scene_alignment_unverified', 'preview_not_preflight']}
    return encoded(value, MAX_INDEX), record, source


def directory(catalog, identity, space_id):
    try:
        return _directory(catalog, identity, space_id)[0]
    except PermissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        raise PreviewUnavailable('rgbd_preview_evidence_unavailable') from exc


def png(pixels):
    height, width, channels = pixels.shape
    def chunk(kind, raw):
        return struct.pack('>I', len(raw))+kind+raw+struct.pack('>I', zlib.crc32(kind+raw) & 0xffffffff)
    raw = b''.join(b'\0'+row.tobytes() for row in pixels)
    result = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6 if channels == 4 else 2, 0, 0, 0))
              +chunk(b'IDAT', zlib.compress(raw))+chunk(b'IEND', b''))
    return 'data:image/png;base64,'+base64.b64encode(result).decode('ascii')


def depth_display(depth):
    code = depth.astype(float)
    with np.errstate(divide='ignore', invalid='ignore'):
        metres = 351.3/(1092.5-code)
    valid = (code >= 600) & (code < 2047) & np.isfinite(metres) & (metres > 0) & (metres <= 10)
    t = np.where(valid, metres/10, 0)
    rgba = np.stack([t*255, (1-np.abs(2*t-1))*255, (1-t)*255, valid*255], axis=-1).astype(np.uint8)
    rgba[~valid] = 0
    return rgba[::2, ::2], int(valid.sum())


def frame(catalog, identity, space_id, index):
    try:
        if not integer(index):
            raise ValueError('frame_index')
        value, record, source = _directory(catalog, identity, space_id)
        if index >= len(value['frames']):
            raise ValueError('frame_index')
        selected = value['frames'][index]
        images = {}
        raw_root = (Path(record['snapshot'])/'raw').resolve()
        for role in ('rgb', 'depth'):
            name = selected[role]
            path = raw_root/name
            if not path.resolve().is_relative_to(raw_root):
                raise ValueError('member_path')
            member = source['members'][name]
            images[role] = read_pnm(read_checked(path, member['sha256'], member['bytes']), role == 'depth')
        rgba, valid_count = depth_display(images['depth'])
        return encoded({'profile': PROFILE, 'kind': 'frame', 'space_id': space_id, 'input_id': identity,
                        'snapshot_sha256': value['snapshot_sha256'], 'tracking_sha256': value['tracking_sha256'],
                        'frame': selected, 'source_size': [640, 480], 'display_size': [320, 240],
                        'display_rule': RULE, 'depth_range_m': [0, 10], 'invalid_depth': 'transparent',
                        'valid_depth_pixels': valid_count, 'rgb_png': png(images['rgb'][::2, ::2]), 'depth_png': png(rgba),
                        'payload_checked': 'selected_pair_only', 'quality': 'unverified', 'robot_ready': False}, MAX_FRAME)
    except PermissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        raise PreviewUnavailable('rgbd_preview_frame_unavailable') from exc
