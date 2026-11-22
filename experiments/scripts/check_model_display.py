"""Synthetic park display probe, never a survey product or a published business scene."""
import argparse
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import numpy as np

from packages.construction.model_display import ModelDisplays, encoded
from packages.construction.preview_model import digest


def park(root, count=100_000):
    root = Path(root)
    name = 'build-display-probe'
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
    points += [500_000, 600_000, 100]
    colors = np.tile(np.array([126, 166, 190], dtype='u1'), (count, 1))
    colors[walls == 1] = [190, 165, 100]
    np.savez_compressed(output / 'spatial.npz', points=points, colors=colors)
    np.savez_compressed(output / 'agent.npz', cells=np.empty((0, 3), dtype='i8'))
    header = f'ply\nformat binary_little_endian 1.0\nelement vertex {count}\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n'
    packed = np.empty(count, dtype=[('xyz', '<f8', 3), ('rgb', 'u1', 3)])
    packed['xyz'], packed['rgb'] = points, colors
    (output / 'human.ply').write_bytes(header.encode() + packed.tobytes())
    (output / 'views.js').write_bytes(b'window.PREVIEW_VIEWS={"agent_points":[]};')
    members = {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in output.iterdir()}
    canonical = members['spatial.npz']['sha256']
    model = {'profile': 'cospace.real-model-preview/0.1', 'id': name, 'unit': 'm',
             'label': 'Synthetic park performance sample', 'frame_id': 'synthetic_park',
             'axes': ['right', 'forward', 'up'], 'data_kind': 'existing_pointcloud_candidate',
             'construction': {'model_points': count, 'input_frames': 1, 'used_frames': 1},
             'bounds_m': [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
             'human_view': {'path': 'human.ply', 'source_model_sha256': canonical},
             'agent_view': {'path': 'agent.npz', 'source_model_sha256': canonical, 'resolution_m': .1, 'surface_cells': 0},
             'members': members, 'limitations': ['synthetic_performance_sample_not_survey']}
    (output / 'model.json').write_bytes(encoded(model))
    (output.parent / 'job.json').write_bytes(encoded({'id': name, 'state': 'succeeded'}))
    return name


def probe(root, converter, count):
    name = park(root, count)
    service = ModelDisplays(SimpleNamespace(root=Path(root), directory=None), converter)
    service.build('candidate', name)
    display = service.describe('candidate', name)['display']
    assert display['point_count'] == count and display['encoding_error_m'] <= .001
    # Decode the actual native octree output and verify every encoded source point.
    folder = service.root / display['id']
    meta = json.loads((folder / 'metadata.json').read_bytes())
    assert [a['name'] for a in meta['attributes']] == ['position', 'rgb']
    raw = (folder / 'octree.bin').read_bytes()
    assert len(raw) == count * 18
    native = np.frombuffer(raw, dtype=[('xyz', '<i4', 3), ('rgb', '<u2', 3)])
    decoded = native['xyz'].astype(float) * np.array(meta['scale']) + np.array(meta['offset']) + np.array(display['origin_m'])
    with np.load(Path(root) / name / 'output/spatial.npz', allow_pickle=False) as source:
        original = source['points']
    # Native conversion reorders points. Check both directions, not row order or LOD indices.
    from scipy.spatial import cKDTree
    max_error = max(float(cKDTree(original).query(decoded)[0].max()),
                    float(cKDTree(decoded).query(original)[0].max()))
    assert max_error <= .001
    print(json.dumps({'points': count, 'display_id': display['id'], 'encoding_error_m': display['encoding_error_m'],
                      'octree_bytes': len(raw), 'native_roundtrip_error_m': max_error, 'source_points_preserved': True}))


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
