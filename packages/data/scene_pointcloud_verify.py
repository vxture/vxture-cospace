"""Independent offline shard verification with disk-backed source-order rebuild."""
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from packages.data.scene_pointcloud_intake import PROFILE, MAX_CHUNK, MAX_SHARDS, digest, local_xyz


def member(root, relative):
    path = root/relative
    if Path(relative).is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('invalid_scene_member_path')
    return path


def read_shard(path, shard):
    if path.stat().st_size != shard['bytes'] or digest(path) != shard['sha256']:
        raise ValueError('shard_integrity')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if (len(infos) != 2 or {i.filename for i in infos} != {'records.npy', 'source_indices.npy'}
                or sum(i.file_size for i in infos) > MAX_CHUNK*34+8192):
            raise ValueError('shard_archive_budget')
    with np.load(path, allow_pickle=False) as data:
        records, indices = data['records'], data['source_indices']
    if (records.ndim != 1 or records.dtype.itemsize != 26 or records.dtype.hasobject
            or not {'X', 'Y', 'Z', 'red', 'green', 'blue'}.issubset(records.dtype.names or ())
            or indices.dtype != np.dtype('<u8') or indices.shape != records.shape
            or len(records) != shard['points'] or not 1 <= len(records) <= MAX_CHUNK):
        raise ValueError('shard_layout')
    return records, indices


def verify(root, *, source_root=None, sample_limit=20_000):
    """Check every record and its original ordinal, not just count/hash metadata.

    A temporary memmap reconstructs one source at a time. The reconstructed byte
    stream must hash identically to the decoded source stream recorded at intake.
    Returns small deterministic samples for engineering overview generation only.
    """
    root = Path(root).resolve()
    scene = json.loads((root/'scene.json').read_bytes())
    origin = np.asarray(scene['origin'], dtype=float)
    if (scene['profile'] != PROFILE or scene['state'] != 'complete'
            or not 1 <= len(scene['sources']) <= 32 or not 1 <= sample_limit <= 100_000
            or not 0 < scene['total_shards'] <= MAX_SHARDS
            or origin.shape != (3,) or not np.isfinite(origin).all()
            or not np.isfinite(scene['tile_size']) or scene['tile_size'] <= 0
            or scene['unit_basis'] not in ('assumed_metre_for_flow_validation', 'verified_metre')):
        raise ValueError('invalid_scene_manifest')
    report = dict(profile='cospace.scene-pointcloud-verification/0.1',
                  scene_manifest_sha256=digest(root/'scene.json'), sources=[], attachments=[])
    samples = []
    for source in scene['sources']:
        count = source['points']
        if not 0 < count <= 200_000_000 or not source['shards']:
            raise ValueError('source_verification_budget')
        covered = np.zeros(count, dtype=bool)
        sample_points, sample_colors, sample_ids = [], [], []
        stride = (count + sample_limit - 1)//sample_limit
        with tempfile.TemporaryDirectory(prefix='cospace-source-verify-', dir=root.parent) as temporary:
            restored = None
            try:
                for shard in source['shards']:
                    records, indices = read_shard(member(root, shard['path']), shard)
                    if restored is None:
                        restored = np.memmap(Path(temporary)/'source-records.bin', mode='w+', dtype=records.dtype, shape=(count,))
                    if records.dtype != restored.dtype:
                        raise ValueError('mixed_source_record_layout')
                    if indices.max() >= count or len(np.unique(indices)) != len(indices) or covered[indices].any():
                        raise ValueError('duplicate_or_out_of_range_source_index')
                    covered[indices] = True
                    restored[indices] = records
                    xyz = local_xyz(records, source, scene['origin'])
                    if (not np.isfinite(xyz).all()
                            or not (np.floor(xyz/scene['tile_size']).astype(np.int64) == shard['tile']).all()
                            or not np.allclose([xyz.min(axis=0), xyz.max(axis=0)], shard['local_bounds'], rtol=0, atol=1e-7)):
                        raise ValueError('shard_spatial_bounds_mismatch')
                    chosen = indices % stride == 0
                    sample_points.append(xyz[chosen])
                    rgb = np.column_stack([records[n][chosen] for n in ('red', 'green', 'blue')])
                    sample_colors.append((rgb.astype(np.uint32)//256).astype(np.uint8))
                    sample_ids.append(indices[chosen])
                if not covered.all():
                    raise ValueError('incomplete_source_coverage')
                encoded = hashlib.sha256()
                for start in range(0, count, MAX_CHUNK):
                    encoded.update(restored[start:start+MAX_CHUNK].tobytes())
                if encoded.hexdigest() != source['encoded_records_sha256']:
                    raise ValueError('source_record_reconstruction_mismatch')
            finally:
                if restored is not None:
                    restored.flush()
                    restored._mmap.close()
        if source_root is not None:
            original = member(Path(source_root).resolve(), source['name'])
            if digest(original) != source['sha256'] or original.stat().st_size != source['bytes']:
                raise ValueError('original_source_changed')
        ids = np.concatenate(sample_ids)
        order = np.argsort(ids)
        samples.append(dict(name=source['name'], points=np.concatenate(sample_points)[order],
                            colors=np.concatenate(sample_colors)[order], source_indices=ids[order]))
        report['sources'].append(dict(name=source['name'], points=count, coverage_complete=True,
                                      source_order_record_hash_matched=True, shards=len(source['shards']),
                                      original_file_rechecked=source_root is not None,
                                      overview_points=len(ids), overview_stride=stride))
    for attachment in scene['attachments']:
        path = member(root, attachment['path'])
        if digest(path) != attachment['sha256'] or path.stat().st_size != attachment['bytes']:
            raise ValueError('attachment_integrity')
        if source_root is not None and digest(member(Path(source_root).resolve(), attachment['name'])) != attachment['sha256']:
            raise ValueError('original_attachment_changed')
        report['attachments'].append(dict(name=attachment['name'], bytes_matched=True, geometry_parsed=False))
    if (sum(s['points'] for s in report['sources']) != scene['total_points']
            or sum(s['shards'] for s in report['sources']) != scene['total_shards']):
        raise ValueError('scene_totals_mismatch')
    report.update(total_points=scene['total_points'], passed=True)
    return report, samples
