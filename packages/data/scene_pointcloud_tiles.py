"""Offline display derivatives; full encoded records remain in the intake store."""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from packages.data.scene_pointcloud_intake import digest, local_xyz
from packages.data.scene_pointcloud_region import SceneRegions
from packages.data.scene_pointcloud_verify import member, read_shard

PROFILE = 'cospace.scene-pointcloud-tiles/0.1'
STEPS = (.25, 1., 4.)
MAX_TILE_POINTS = 50_000


def prepare_tiles(root, expected_sha256, output, progress=None):
    store = SceneRegions(root, expected_sha256)
    output = Path(output).resolve()
    if output.exists() or store.root.is_relative_to(output) or output.is_relative_to(store.root):
        raise ValueError('exclusive_tile_output_required')
    output.mkdir(parents=True)
    tiles = []
    try:
        for source_no, source in enumerate(store.scene['sources']):
            groups = defaultdict(list)
            for shard in source['shards']:
                groups[tuple(shard['tile'])].append(shard)
            for key, shards in sorted(groups.items()):
                chosen = [dict() for _ in STEPS]
                lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
                count = 0
                for shard in shards:
                    records, indices = read_shard(member(store.root, shard['path']), shard)
                    xyz = local_xyz(records, source, store.scene['origin'])
                    if not (np.floor(xyz/store.scene['tile_size']).astype(np.int64) == key).all():
                        raise ValueError('tile_spatial_binding')
                    rgb = (np.column_stack([records[n] for n in ('red','green','blue')]).astype(np.uint32)//256).astype(np.uint8)
                    lo = np.minimum(lo, xyz.min(axis=0)); hi = np.maximum(hi, xyz.max(axis=0)); count += len(xyz)
                    for step, selected in zip(STEPS, chosen):
                        keys = np.floor(xyz/step).astype(np.int64)
                        order = np.lexsort((indices, keys[:,2], keys[:,1], keys[:,0]))
                        ordered = keys[order]
                        starts = np.r_[0, np.flatnonzero(np.any(np.diff(ordered,axis=0),axis=1))+1]
                        for i in order[starts]:
                            cell = tuple(int(v) for v in keys[i]); ordinal = int(indices[i])
                            old = selected.get(cell)
                            if old is None or ordinal < old[0]:
                                selected[cell] = (ordinal, xyz[i].copy(), rgb[i].copy())
                            if len(selected) > MAX_TILE_POINTS:
                                raise ValueError('display_tile_budget_choose_smaller_intake_tiles_or_coarser_lod')
                identity = 't'+str(len(tiles)).zfill(5)
                lods = []
                for level, (step, selected) in enumerate(zip(STEPS, chosen)):
                    values = [selected[k] for k in sorted(selected)]
                    positions = np.asarray([v[1] for v in values],dtype='<f4')
                    colors = np.asarray([v[2] for v in values],dtype='u1')
                    path = output/f'{identity}-{level}.bin'
                    path.write_bytes(positions.tobytes()+colors.tobytes())
                    lods.append(dict(level=level, step=step, points=len(values), bytes=path.stat().st_size, sha256=digest(path)))
                tiles.append(dict(id=identity, source=source_no, bounds=[lo.tolist(),hi.tolist()], source_points=count, lods=lods))
                if progress: progress(dict(source=source['name'], tiles=len(tiles)))
        if digest(store.root/'scene.json') != expected_sha256: raise ValueError('scene_manifest_changed')
        doc = dict(profile=PROFILE, scene_manifest_sha256=expected_sha256, name=store.scene['scene_name'],
                   origin=store.scene['origin'], unit_basis=store.scene['unit_basis'], alignment_verified=False,
                   sources=[dict(name=s['name'], sha256=s['sha256'], points=s['points'], bounds=s['local_bounds']) for s in store.scene['sources']],
                   tiles=tiles, layout='float32_xyz_then_uint8_rgb', display_only=True,
                   sampling='lowest_source_ordinal_per_voxel', max_tile_points=MAX_TILE_POINTS)
        (output/'index.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return doc
    except Exception:
        (output/'failed.json').write_text('{"state":"failed"}',encoding='utf-8')
        raise
