"""Offline full-resolution LAS/LAZ partitioning. Not a workbench upload adapter.

laspy/lazrs are optional preprocessing dependencies, imported only by the reader.
Shards retain the encoded point record and source ordinal without sampling.
"""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np

PROFILE = 'cospace.scene-pointcloud-intake/0.1'
MAX_CHUNK = 250_000
MAX_SHARDS = 100_000


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def las_reader(path):
    try:
        import laspy
    except ImportError as exc:
        raise ValueError('install_isolated_las_preprocessing_dependencies') from exc
    with laspy.open(path) as reader:
        yield reader


def inspect_source(path, opener):
    with opener(path) as reader:
        header = reader.header
        if header.point_format.id != 2 or header.point_format.size != 26:
            raise ValueError('only_las_point_format_2_supported')
        bounds = np.array([header.mins, header.maxs], dtype=float)
        scales = np.array(header.scales, dtype=float)
        offsets = np.array(header.offsets, dtype=float)
        count = int(header.point_count)
        if (bounds.shape != (2, 3) or not np.isfinite(bounds).all()
                or np.any(bounds[0] > bounds[1]) or not 0 < count <= 200_000_000
                or scales.shape != (3,) or offsets.shape != (3,)
                or not np.isfinite(scales).all() or not np.isfinite(offsets).all()
                or np.any(scales <= 0)):
            raise ValueError('invalid_las_header')
        return dict(name=path.name, bytes=path.stat().st_size, sha256=digest(path),
                    point_format=2, record_bytes=26, points=count,
                    scales=scales.tolist(), offsets=offsets.tolist(), header_bounds=bounds.tolist())


def local_xyz(records, source, origin):
    xyz = np.column_stack([records[axis] for axis in ('X', 'Y', 'Z')]).astype(np.float64)
    return xyz * source['scales'] + source['offsets'] - origin


def intake(sources, output, *, scene_name, tile_size=20., chunk_points=MAX_CHUNK,
           unit_basis, ifc=None, opener=las_reader, progress=None):
    """Exclusive local result; scene.json exists only after complete success.

    Coordinates remain source encoded XYZ. A shared display origin is explicit,
    not evidence of alignment, a CRS, or a verified metre conversion.
    """
    if (type(chunk_points) is not int or not 1 <= chunk_points <= MAX_CHUNK
            or isinstance(tile_size, bool) or not math.isfinite(tile_size) or tile_size <= 0
            or unit_basis not in ('assumed_metre_for_flow_validation', 'verified_metre')
            or not isinstance(scene_name, str) or not scene_name.strip()):
        raise ValueError('invalid_intake_parameters')
    supplied = [Path(p).absolute() for p in sources]
    supplied_ifc = Path(ifc).absolute() if ifc is not None else None
    if (not 1 <= len(supplied) <= 32 or any(p.is_symlink() or not p.is_file() for p in supplied)
            or supplied_ifc is not None and (supplied_ifc.is_symlink() or not supplied_ifc.is_file())):
        raise ValueError('invalid_source_files')
    sources = [p.resolve() for p in supplied]
    ifc = supplied_ifc.resolve() if supplied_ifc else None
    if len(set(sources)) != len(sources) or len({p.name.casefold() for p in sources}) != len(sources):
        raise ValueError('duplicate_source')
    output = Path(output).resolve()
    if output.exists() or any(p.is_relative_to(output) for p in sources + ([ifc] if ifc else [])):
        raise ValueError('exclusive_output_required')
    inventory = [inspect_source(p, opener) for p in sources]
    origin = np.floor(np.min([s['header_bounds'][0] for s in inventory], axis=0))
    # Tile keys use safe int64 arithmetic; no CRS inference from these bounds.
    if max(np.abs(np.array(s['header_bounds']) - origin).max() / tile_size for s in inventory) > 1e12:
        raise ValueError('tile_index_budget')
    ifc_before = digest(ifc) if ifc else None
    output.mkdir(parents=True, exist_ok=False)
    state = output/'intake-state.json'
    state.write_text(json.dumps(dict(state='running', profile=PROFILE)), encoding='utf-8')
    result = dict(profile=PROFILE, scene_name=scene_name.strip(), state='complete',
                  origin=origin.tolist(), transform='local = raw_XYZ * scales + offsets - origin',
                  inverse='raw_XYZ = (local + origin - offsets) / scales',
                  unit_basis=unit_basis, unit_verified=unit_basis == 'verified_metre',
                  crs='unknown', alignment_verified=False, tile_size=tile_size,
                  sampling='none', merged=False, sources=inventory, attachments=[],
                  robot_ready=False, production_ready=False)
    total_shards = 0
    try:
        for source_no, (path, source) in enumerate(zip(sources, inventory)):
            directory = output/f'source-{source_no:02d}'
            directory.mkdir()
            shards = []
            seen = 0
            encoded = hashlib.sha256()
            actual_min = np.full(3, np.inf)
            actual_max = np.full(3, -np.inf)
            with opener(path) as reader:
                for chunk in reader.chunk_iterator(chunk_points):
                    records = np.array(chunk.array, copy=True)
                    if (records.dtype.hasobject or records.dtype.itemsize != 26
                            or not {'X', 'Y', 'Z'}.issubset(records.dtype.names or ())
                            or not 1 <= len(records) <= chunk_points or seen + len(records) > source['points']):
                        raise ValueError('invalid_point_chunk')
                    encoded.update(records.tobytes())
                    xyz = local_xyz(records, source, origin)
                    if not np.isfinite(xyz).all():
                        raise ValueError('invalid_decoded_coordinate')
                    actual_min = np.minimum(actual_min, xyz.min(axis=0))
                    actual_max = np.maximum(actual_max, xyz.max(axis=0))
                    keys = np.floor(xyz / tile_size).astype(np.int64)
                    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
                    ordered_keys = keys[order]
                    edges = np.r_[0, np.flatnonzero(np.any(np.diff(ordered_keys, axis=0), axis=1)) + 1, len(order)]
                    for start, stop in zip(edges[:-1], edges[1:]):
                        total_shards += 1
                        if total_shards > MAX_SHARDS:
                            raise ValueError('shard_count_budget')
                        ids = order[start:stop]
                        target = directory/f'part-{len(shards):06d}.npz'
                        np.savez_compressed(target, records=records[ids], source_indices=ids.astype(np.uint64)+seen)
                        bounds = [xyz[ids].min(axis=0).tolist(), xyz[ids].max(axis=0).tolist()]
                        shards.append(dict(path=target.relative_to(output).as_posix(), points=len(ids),
                                           tile=keys[ids[0]].tolist(), local_bounds=bounds,
                                           sha256=digest(target), bytes=target.stat().st_size))
                    seen += len(records)
                    if progress:
                        progress(dict(source=path.name, decoded=seen, expected=source['points'], shards=len(shards)))
            if seen != source['points']:
                raise ValueError('source_point_count_mismatch')
            # Full payload bounds are checked rather than trusting the LAS header.
            actual = np.array([actual_min, actual_max]) + origin
            if not np.allclose(actual, source['header_bounds'], rtol=0, atol=1e-7):
                raise ValueError('source_header_bounds_mismatch')
            if digest(path) != source['sha256'] or path.stat().st_size != source['bytes']:
                raise ValueError('source_changed_during_intake')
            source.update(decoded_points=seen, retained_points=seen, discarded_points=0,
                          local_bounds=[actual_min.tolist(), actual_max.tolist()],
                          encoded_records_sha256=encoded.hexdigest(), shards=shards)
        if ifc:
            target = output/'attachments'/ifc.name
            target.parent.mkdir()
            shutil.copyfile(ifc, target)
            if digest(ifc) != ifc_before or digest(target) != ifc_before:
                raise ValueError('ifc_changed_during_intake')
            result['attachments'].append(dict(name=ifc.name, path=target.relative_to(output).as_posix(),
                                              sha256=ifc_before, bytes=target.stat().st_size,
                                              geometry_parsed=False, alignment_verified=False))
        # An early source may change while subsequent large files are processed.
        for path, source in zip(sources, inventory):
            if digest(path) != source['sha256'] or path.stat().st_size != source['bytes']:
                raise ValueError('source_changed_during_intake')
        result.update(total_points=sum(s['retained_points'] for s in inventory), total_shards=total_shards)
        # Manifest rename is the completion marker. Failed partial data remains
        # explicit for inspection and cannot masquerade as a completed scene.
        temp = output/'scene.pending.json'
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        state.write_text(json.dumps(dict(state='complete', profile=PROFILE)), encoding='utf-8')
        temp.rename(output/'scene.json')
        return result
    except Exception as exc:
        state.write_text(json.dumps(dict(state='failed', profile=PROFILE, error_type=type(exc).__name__)), encoding='utf-8')
        raise
