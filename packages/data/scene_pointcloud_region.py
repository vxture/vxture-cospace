"""Offline indexed region reads and explicit bounded multi-source PLY derivation."""
import json
import math
from pathlib import Path

import numpy as np

from packages.data.scene_pointcloud_intake import PROFILE, digest, local_xyz
from packages.data.scene_pointcloud_verify import member, read_shard
from packages.data.pointcloud_composition import source_set_digest
from packages.data.preview_pointcloud import read_cloud


class RegionBudgetExceeded(ValueError):
    pass


class SceneRegions:
    def __init__(self, root, expected_sha256):
        self.root = Path(root).resolve()
        self.sha256 = expected_sha256
        if digest(self.root/'scene.json') != expected_sha256:
            raise ValueError('scene_manifest_changed')
        self.scene = json.loads((self.root/'scene.json').read_bytes())
        if self.scene['profile'] != PROFILE or self.scene['state'] != 'complete':
            raise ValueError('scene_not_complete')

    def read(self, source_names, bounds, *, limit=250_000, voxel_size=0.):
        bounds = np.asarray(bounds, dtype=float)
        if (bounds.shape != (2, 3) or not np.isfinite(bounds).all() or np.any(bounds[0] >= bounds[1])
                or np.abs(bounds).max() > 1_000_000 or type(limit) is not int or not 1 <= limit <= 1_000_000
                or isinstance(voxel_size, bool) or not math.isfinite(voxel_size)
                or not (voxel_size == 0 or .001 <= voxel_size <= 100)
                or not source_names or len(set(source_names)) != len(source_names)):
            raise ValueError('invalid_region_request')
        if digest(self.root/'scene.json') != self.sha256:
            raise ValueError('scene_manifest_changed')
        sources = {s['name']: s for s in self.scene['sources']}
        if any(name not in sources for name in source_names):
            raise ValueError('unknown_scene_source')
        selected, exact_points, exact_colors, exact_refs = {}, [], [], []
        rows, loaded, skipped, retained = [], 0, 0, 0
        for source_no, name in enumerate(source_names):
            source = sources[name]
            matched = 0
            for shard in source['shards']:
                lo, hi = np.array(shard['local_bounds'])
                # Half-open ROI: lower <= point < upper; tile max is inclusive.
                if np.any(hi < bounds[0]) or np.any(lo >= bounds[1]):
                    skipped += 1
                    continue
                records, indices = read_shard(member(self.root, shard['path']), shard)
                loaded += 1
                xyz = local_xyz(records, source, self.scene['origin'])
                mask = ((xyz >= bounds[0]) & (xyz < bounds[1])).all(axis=1)
                xyz, indices, records = xyz[mask], indices[mask], records[mask]
                matched += len(xyz)
                if not len(xyz):
                    continue
                colors = (np.column_stack([records[n] for n in ('red', 'green', 'blue')]).astype(np.uint32)//256).astype(np.uint8)
                if voxel_size == 0:
                    retained += len(xyz)
                    if retained > limit:
                        raise RegionBudgetExceeded('region_exceeds_budget_choose_smaller_bounds_or_explicit_voxel_size')
                    exact_points.append(xyz); exact_colors.append(colors)
                    exact_refs.extend((source_no, int(i)) for i in indices)
                else:
                    keys = np.floor(xyz/voxel_size).astype(np.int64)
                    order = np.lexsort((indices, keys[:, 2], keys[:, 1], keys[:, 0]))
                    ordered = keys[order]
                    starts = np.r_[0, np.flatnonzero(np.any(np.diff(ordered, axis=0), axis=1))+1]
                    for i in order[starts]:
                        key = tuple(int(v) for v in keys[i])
                        rank = (source_no, int(indices[i]))
                        old = selected.get(key)
                        if old is None or rank < old[0]:
                            # Own the tiny representatives rather than retaining
                            # a view into each entire decoded chunk in memory.
                            selected[key] = (rank, xyz[i].copy(), colors[i].copy())
                            if len(selected) > limit:
                                raise RegionBudgetExceeded('voxel_result_exceeds_budget_choose_coarser_resolution')
            rows.append(dict(name=name, sha256=source['sha256'], source_points=source['points'], matched_points=matched))
        matched_total = sum(s['matched_points'] for s in rows)
        if matched_total == 0:
            raise ValueError('empty_region')
        if voxel_size:
            values = [selected[k] for k in sorted(selected)]
            refs = [v[0] for v in values]
            points = np.array([v[1] for v in values])
            colors = np.array([v[2] for v in values], dtype=np.uint8)
        else:
            order = sorted(range(len(exact_refs)), key=exact_refs.__getitem__)
            points = np.concatenate(exact_points)[order]
            colors = np.concatenate(exact_colors)[order]
            refs = [exact_refs[i] for i in order]
        return dict(points=points, colors=colors, source_ordinals=np.array(refs, dtype=np.uint64),
                    sources=rows, matched_points=matched_total, retained_points=len(points),
                    bounds_local=bounds.tolist(), voxel_size=float(voxel_size),
                    shards_loaded=loaded, shards_skipped=skipped)

    def prepare(self, output, source_names, bounds, *, limit=250_000, voxel_size=0.):
        output = Path(output).resolve()
        if output.exists() or self.root.is_relative_to(output):
            raise ValueError('exclusive_region_output_required')
        result = self.read(source_names, bounds, limit=limit, voxel_size=voxel_size)
        output.mkdir(parents=True, exist_ok=False)
        snapshot = output/'snapshot'; snapshot.mkdir()
        vertices = np.empty(len(result['points']), dtype=[(n, '<f4') for n in ('x', 'y', 'z')]+[(n, 'u1') for n in ('red', 'green', 'blue')])
        for i, name in enumerate(('x', 'y', 'z')):
            vertices[name] = result['points'][:, i]
        for i, name in enumerate(('red', 'green', 'blue')):
            vertices[name] = result['colors'][:, i]
        header = ('ply\nformat binary_little_endian 1.0\nelement vertex '+str(len(vertices))+'\n'
                  'property float x\nproperty float y\nproperty float z\n'
                  'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode()
        cloud = snapshot/'cloud.ply'; cloud.write_bytes(header+vertices.tobytes())
        binding = dict(path='cloud.ply', sha256=digest(cloud), bytes=cloud.stat().st_size, points=len(vertices))
        coordinates = dict(unit='m', frame_id='scene_local_'+self.sha256[:16], axes=['source_x','source_y','source_z'],
                           scope='scene_local', scene_alignment='unverified')
        description = ('场景多来源按声明坐标组合；未配准。来源优先级按所选顺序；'
                       f"范围内{result['matched_points']}点，保留{len(vertices)}点；体素步长{voxel_size}；"
                       f"单位依据{self.scene['unit_basis']}；原始全量分块仍保留。")
        receipt = dict(profile='cospace.pointcloud-composition/0.1', scene_manifest_sha256=self.sha256,
                       sources=result['sources'], origin=self.scene['origin'], bounds_local=result['bounds_local'],
                       unit_basis=self.scene['unit_basis'], voxel_size=result['voxel_size'],
                       selection_method='all_points' if voxel_size == 0 else 'first_source_then_lowest_ordinal_per_voxel',
                       matched_points=result['matched_points'], retained_points=len(vertices), alignment_verified=False,
                       cloud=binding, coordinates=coordinates, description=description)
        receipt_path = snapshot/'composition.json'
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        doc = dict(profile='cospace.pointcloud-input/0.1', cloud=binding, coordinates=coordinates,
                   provenance=dict(kind='existing_pointcloud', source_manifest_sha256=digest(receipt_path),
                                   source_member_sha256=source_set_digest(result['sources']), description=description),
                   composition_path='composition.json')
        (snapshot/'pointcloud.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
        read_cloud(snapshot)
        np.save(output/'source-ordinals.npy', result['source_ordinals'], allow_pickle=False)
        report = {k: v for k, v in result.items() if k not in ('points', 'colors', 'source_ordinals')}
        report.update(scene_manifest_sha256=self.sha256, composition_sha256=digest(receipt_path),
                      source_ordinals_sha256=digest(output/'source-ordinals.npy'))
        (output/'region.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
        return report
