"""Synthetic park display probe, never a survey product or a published business scene."""
import argparse
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import numpy as np

from packages.construction.model_display import AGENT_SOURCE, ModelDisplays, encoded
from packages.construction.preview_model import digest, surface_cells

SPATIAL_SOURCE = 'spatial.npz'


def park(root, count=100_000, layout='grid', *, dual=False):
    root = Path(root)
    name = 'build-linear-probe' if layout == 'linear' else 'build-display-probe'
    output = root / name / 'output'
    output.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(20261123)
    points = rng.random((count, 3))
    building = rng.integers(0, 24, count)
    points[:, 0] = (building % 6) * 40 + points[:, 0] * 24
    points[:, 1] = (building // 6) * 45 + points[:, 1] * 28
    points[:, 2] *= 18
    walls = np.arange(count) % 3
    points[walls == 0, 0] = (building[walls == 0] % 6) * 40
    points[walls == 1, 2] = 18
    points[walls == 2, 1] = (building[walls == 2] // 6) * 45
    if layout == 'linear':
        points[:, 0] *= 4
        points[:, 1] *= .2
    points += [500_000, 600_000, 100]
    colors = np.tile(np.array([126, 166, 190], dtype='u1'), (count, 1))
    colors[walls == 1] = [190, 165, 100]
    np.savez_compressed(output / SPATIAL_SOURCE, points=points, colors=colors)
    cells = surface_cells(points, .1) if dual else np.empty((0, 3), dtype='i8')
    np.savez_compressed(output / AGENT_SOURCE, cells=cells)
    header = f'ply\nformat binary_little_endian 1.0\nelement vertex {count}\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n'
    packed = np.empty(count, dtype=[('xyz', '<f8', 3), ('rgb', 'u1', 3)])
    packed['xyz'], packed['rgb'] = points, colors
    (output / 'human.ply').write_bytes(header.encode() + packed.tobytes())
    if not dual:
        (output / 'views.js').write_bytes(b'window.PREVIEW_VIEWS={"agent_points":[]};')
    members = {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in output.iterdir()}
    canonical = members[SPATIAL_SOURCE]['sha256']
    model = {'profile': 'cospace.real-model-preview/0.1', 'id': name, 'unit': 'm',
             'label': 'Synthetic park performance sample', 'frame_id': 'synthetic_park',
             'axes': ['right', 'forward', 'up'], 'data_kind': 'existing_pointcloud_candidate',
             'construction': {'model_points': count, 'input_frames': 1, 'used_frames': 1},
             'bounds_m': [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
             'human_view': {'path': 'human.ply', 'source_model_sha256': canonical},
             'agent_view': {'path': AGENT_SOURCE, 'source_model_sha256': canonical, 'resolution_m': .1, 'surface_cells': len(cells)},
             'members': members, 'limitations': ['synthetic_performance_sample_not_survey']}
    (output / 'model.json').write_bytes(encoded(model))
    (output.parent / 'job.json').write_bytes(encoded({'id': name, 'state': 'succeeded'}))
    return name


def probe(root, converter, count):
    name = park(root, count, dual=True)
    service = ModelDisplays(SimpleNamespace(root=Path(root), directory=None), converter)
    service.build('candidate', name)
    service.build('candidate', name, agent=True)
    descriptors = service.describe('candidate', name)
    display, agent = descriptors['display'], descriptors['agent_display']
    assert display['point_count'] == count and display['encoding_error_m'] <= .001
    assert display['origin_m'] == agent['origin_m'] and display['model_to_display'] == agent['model_to_display']
    source = Path(root) / name / 'output'
    with np.load(source / SPATIAL_SOURCE, allow_pickle=False) as data:
        original = data['points']
    with np.load(source / AGENT_SOURCE, allow_pickle=False) as data:
        cells = data['cells']
    centers = (cells.astype(np.float64) + .5) * descriptors['model']['agent_view']['resolution_m']
    assert agent['point_count'] == len(cells) and agent['sample_m'] == centers[0].tolist()
    visual_error, visual_bytes = verify_native(service.root, display, original)
    agent_error, agent_bytes = verify_native(service.root, agent, centers)
    print(json.dumps({'points': count, 'display_id': display['id'], 'encoding_error_m': display['encoding_error_m'],
                      'octree_bytes': visual_bytes, 'native_roundtrip_error_m': visual_error, 'source_points_preserved': True,
                      'agent_units': len(cells), 'agent_octree_bytes': agent_bytes, 'agent_roundtrip_error_m': agent_error}))


def verify_native(root, descriptor, original):
    # Decode the actual native octree output and verify both ranges of the matching.
    folder = root / descriptor['id']
    meta = json.loads((folder / 'metadata.json').read_bytes())
    assert [a['name'] for a in meta['attributes']] == ['position', 'rgb']
    raw = (folder / 'octree.bin').read_bytes()
    assert len(raw) == len(original) * 18
    native = np.frombuffer(raw, dtype=[('xyz', '<i4', 3), ('rgb', '<u2', 3)])
    local = native['xyz'].astype(float) * np.array(meta['scale']) + np.array(meta['offset'])
    decoded = local @ np.array(descriptor['model_to_display']) + np.array(descriptor['origin_m'])
    # Native conversion reorders points. Check both directions, not row order or LOD indices.
    from scipy.spatial import cKDTree
    max_error = max(float(cKDTree(original).query(decoded)[0].max()),
                    float(cKDTree(decoded).query(original)[0].max()))
    assert max_error <= .001
    return max_error, len(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--converter', required=True)
    parser.add_argument('--points', type=int, default=100_000)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if not 1_000 <= args.points <= 10_000_000:
        parser.error('points must be within the explicit performance-probe budget')
    if args.root:
        probe(args.root, args.converter, args.points)
    else:
        with tempfile.TemporaryDirectory() as root:
            probe(Path(root) / 'jobs', args.converter, args.points)


if __name__ == '__main__':
    main()
