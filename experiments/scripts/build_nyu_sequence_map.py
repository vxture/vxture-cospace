"""Read one whole NYU recording and prepare a bounded existing-map intake.

Open3D stays in the isolated 3.12 environment. No gate tuning, relocalization,
pose bridges or partial successful intake packages. Reports are handover evidence,
not a new trusted acquisition format accepted by the workbench.
"""
import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import zipfile
import numpy as np
from packages.data.nyu_rgbd import timestamp_us, read_pnm, make_cloud, DEPTH_K
from packages.construction.rgbd_rectify import rasterize_depth_cloud
from packages.construction.rgbd_tracking import CONFIG, angle, transform

PAIR_TOLERANCE_US = 20_000
VOXEL_M = .02
MAX_DEPTH_FRAMES = 500
IMPLEMENTATION = (
    'experiments/scripts/build_nyu_sequence_map.py', 'experiments/scripts/run_nyu_open3d.py',
    'packages/data/nyu_rgbd.py', 'packages/construction/rgbd_rectify.py',
    'packages/construction/rgbd_multiscale.py', 'packages/construction/rgbd_tracking.py',
    'experiments/stack/rgbd-open3d/uv.lock')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, doc):
    raw = (json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
    with Path(path).open('xb') as stream:
        stream.write(raw)
    return digest(raw)


def inventory(scene):
    """Freeze all members, including unpaired RGB and accelerometer records."""
    scene = Path(scene).resolve(strict=True)
    members = {}
    paths = sorted(scene.iterdir())
    if len(paths) > 4096:
        raise ValueError('source_file_budget')
    for p in paths:
        if p.is_symlink() or not p.is_file():
            raise ValueError('single_recording_files_only')
        # Do not publish host paths in transferable evidence.
        kind = 'depth' if p.name.startswith('d-') and p.suffix == '.pgm' else (
            'rgb' if p.name.startswith('r-') and p.suffix == '.ppm' else 'auxiliary')
        if p.stat().st_size > 2_000_000:
            raise ValueError('source_member_budget')
        raw = p.read_bytes()
        members[p.name] = {'kind': kind, 'bytes': len(raw), 'sha256': digest(raw)}
    depths = sorted((timestamp_us(n), n) for n, m in members.items() if m['kind'] == 'depth')
    rgbs = sorted((timestamp_us(n), n) for n, m in members.items() if m['kind'] == 'rgb')
    if not 2 <= len(depths) <= MAX_DEPTH_FRAMES or not rgbs:
        raise ValueError('recording_frame_budget_or_missing_images')
    if len({t for t, _ in depths}) != len(depths) or len({t for t, _ in rgbs}) != len(rgbs):
        raise ValueError('duplicate_source_timestamp')
    times = [t for t, _ in rgbs]
    pairs = []
    for t, name in depths:
        pos = bisect_left(times, t)
        nearest = min((i for i in (pos-1, pos) if 0 <= i < len(times)),
                      key=lambda i: (abs(times[i]-t), times[i]))
        gap = times[nearest]-t
        accepted = abs(gap) <= PAIR_TOLERANCE_US
        pairs.append({'depth': name, 'rgb': rgbs[nearest][1], 'depth_time_us': t,
                      'rgb_minus_depth_us': gap, 'accepted': accepted,
                      'reason': None if accepted else 'rgb_outside_fixed_20ms_tolerance'})
    return {'profile': 'cospace.nyu-sequence/0.1', 'scene': scene.name,
            'selection': 'whole_recording', 'clock': 'filename_time_unverified_utc',
            'duration_us': depths[-1][0]-depths[0][0], 'pair_tolerance_us': PAIR_TOLERANCE_US,
            'depth_frames': len(depths), 'rgb_frames': len(rgbs),
            'paired_frames': sum(p['accepted'] for p in pairs), 'pairs': pairs,
            'members': members, 'scene_coverage': None, 'independent_accuracy_verified': False}


def checked_read(scene, name, capture):
    raw = (Path(scene)/name).read_bytes()
    member = capture['members'][name]
    if len(raw) != member['bytes'] or digest(raw) != member['sha256']:
        raise ValueError('source_changed')
    return raw


def voxel_observations(points, colors):
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or colors.shape != points.shape:
        raise ValueError('invalid_map_arrays')
    if not np.isfinite(points).all() or np.abs(points).max() > 1_000_000:
        raise ValueError('invalid_map_coordinates')
    # Keep a measured point and its original color per voxel; no invented surface.
    _, ids = np.unique(np.floor(points/VOXEL_M).astype(np.int64), axis=0, return_index=True)
    ids.sort()
    return points[ids].astype(np.float32), colors[ids].astype(np.uint8)


def binary_ply(points, colors):
    if not 0 < len(points) <= 1_000_000:
        raise ValueError('map_intake_point_budget')
    vertices = np.empty(len(points), dtype=[(n, '<f4') for n in ('x', 'y', 'z')]+
                        [(n, 'u1') for n in ('red', 'green', 'blue')])
    for i, n in enumerate(('x', 'y', 'z')):
        vertices[n] = points[:, i]
    for i, n in enumerate(('red', 'green', 'blue')):
        vertices[n] = colors[:, i]
    header = ('ply\nformat binary_little_endian 1.0\nelement vertex '+str(len(points))+
              '\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red'+
              '\nproperty uchar green\nproperty uchar blue\nend_header\n').encode('ascii')
    return header+vertices.tobytes()


def trace(pairs, load, compute, options):
    """Stop at the first rejected edge; never silently bridge a missing pose."""
    previous = load(pairs[0])
    points, colors = [previous[1][0]], [previous[1][1]]
    poses, edges = [np.eye(4).tolist()], []
    for i, pair in enumerate(pairs[1:], 1):
        current = load(pair)
        forward, reverse = compute(current, previous), compute(previous, current)
        closure = np.array(forward['T_target_source']) @ np.array(reverse['T_target_source'])
        ct, cr = float(np.linalg.norm(closure[:3, 3])), angle(closure[:3, :3])
        if not reverse['accepted']:
            forward['reasons'].append('reverse_registration_rejected')
        if ct > options['cycle_translation_m'] or cr > options['cycle_rotation_rad']:
            forward['reasons'].append('bidirectional_inconsistent')
        forward.update(accepted=not forward['reasons'], reverse=reverse, cycle_translation_m=ct,
                       cycle_rotation_rad=cr, previous_frame=i-1, current_frame=i)
        edges.append(forward)
        if not forward['accepted']:
            break
        pose = np.array(poses[-1]) @ np.array(forward['T_target_source'])
        poses.append(pose.tolist())
        points.append(transform(current[1][0], pose))
        colors.append(current[1][1])
        previous = current
        if i % 20 == 0:
            print(json.dumps({'continuous_frames': len(poses), 'paired_frames': len(pairs)}), flush=True)
    return poses, edges, points, colors


def package_map(root, report_sha, cloud, count, scene):
    """Only called after a complete continuous run and end-of-run source check."""
    snapshot = root/'snapshot'
    snapshot.mkdir()
    (snapshot/'cloud.ply').write_bytes(cloud)
    declaration = {'profile': 'cospace.pointcloud-input/0.1',
                   'cloud': {'path': 'cloud.ply', 'sha256': digest(cloud), 'bytes': len(cloud), 'points': count},
                   'coordinates': {'unit': 'm', 'frame_id': 'first_depth_camera_anchor',
                                   'axes': ['right', 'down', 'forward'], 'scope': 'scene_local',
                                   'scene_alignment': 'unverified'},
                   'provenance': {'kind': 'existing_pointcloud', 'source_manifest_sha256': report_sha,
                                  'source_member_sha256': digest(cloud),
                                  'description': f'NYU {scene}: whole recording, continuous Open3D RGB-D odometry; '
                                  'reconstruction.json SHA256 bound above; first-camera local coordinates; '
                                  'coverage and accuracy unverified. Reports supplied separately in handover.'}}
    write_json(snapshot/'pointcloud.json', declaration)
    write_json(root/'input.json', {'profile': 'cospace.input-upload/0.1', 'format': 'ply_pointcloud'})
    with zipfile.ZipFile(root/'input.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('input.json', 'snapshot/pointcloud.json', 'snapshot/cloud.ply'):
            archive.write(root/name, name)
    return {'path': 'input.zip', 'sha256': digest((root/'input.zip').read_bytes()),
            'bytes': (root/'input.zip').stat().st_size}


def verify_artifacts(root):
    """Check transferable report/map bindings with the normal application reader.

    Integrity is checked, not report authenticity or independent map accuracy.
    """
    from packages.data.preview_pointcloud import read_cloud
    root = Path(root)
    ready = json.loads((root/'ready.json').read_bytes())
    capture_raw, report_raw = (root/'capture.json').read_bytes(), (root/'reconstruction.json').read_bytes()
    capture, report = json.loads(capture_raw), json.loads(report_raw)
    if (ready['capture_sha256'] != digest(capture_raw) or ready['reconstruction_sha256'] != digest(report_raw)
            or report['capture_sha256'] != digest(capture_raw)):
        raise ValueError('handover_report_binding')
    result = report['result']
    pairs = capture['pairs']
    n = sum(p['accepted'] for p in pairs)
    if (capture['profile'] != 'cospace.nyu-sequence/0.1' or capture['selection'] != 'whole_recording'
            or report['profile'] != 'cospace.nyu-sequence-reconstruction/0.1'
            or not result['completed'] or not result['source_unchanged']
            or result['source_depth_frames'] != capture['depth_frames'] or len(pairs) != capture['depth_frames']
            or result['paired_frames'] != capture['paired_frames'] or n != capture['paired_frames']
            or result['used_frames'] != n or result['excluded_depth_frames'] != len(pairs)-n
            or len(report['T_anchor_camera']) != n or len(report['edges']) != n-1
            or any(not e['accepted'] or e['reasons'] or not e['reverse']['accepted'] for e in report['edges'])
            or capture['scene_coverage'] is not None or report['scene_coverage'] is not None
            or report['independent_accuracy_verified'] or report['robot_ready']):
        raise ValueError('handover_incomplete_or_overclaimed')
    poses = np.array(report['T_anchor_camera'])
    if (poses.shape != (n, 4, 4) or not np.isfinite(poses).all() or not np.allclose(poses[0], np.eye(4))
            or not np.allclose(poses[:, 3, :], [0, 0, 0, 1])):
        raise ValueError('handover_poses')
    for i, edge in enumerate(report['edges']):
        if (edge['previous_frame'] != i or edge['current_frame'] != i+1
                or not np.allclose(poses[i] @ np.array(edge['T_target_source']), poses[i+1])):
            raise ValueError('handover_pose_continuity')
    checked, points, _, doc = read_cloud(root/'snapshot')
    if (doc['provenance']['source_manifest_sha256'] != digest(report_raw)
            or doc['provenance']['source_member_sha256'] != checked['cloud_sha256']
            or report['map']['sha256'] != checked['cloud_sha256'] or ready['cloud_sha256'] != checked['cloud_sha256']
            or report['map']['bytes'] != checked['cloud_bytes'] or report['map']['points'] != len(points)
            or doc['coordinates'] != {'unit': 'm', 'frame_id': report['frame_id'], 'axes': report['axes'],
                                     'scope': 'scene_local', 'scene_alignment': 'unverified'}):
        raise ValueError('handover_map_binding')
    package = ready['input_package']
    raw = (root/'input.zip').read_bytes()
    if package['path'] != 'input.zip' or package['sha256'] != digest(raw) or package['bytes'] != len(raw):
        raise ValueError('handover_package_binding')
    with zipfile.ZipFile(root/'input.zip') as archive:
        expected = {'input.json', 'snapshot/pointcloud.json', 'snapshot/cloud.ply'}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError('handover_package_members')
        if any(archive.read(n) != (root/n).read_bytes() for n in expected):
            raise ValueError('handover_package_payload')
    return {'status': 'passed', 'source_depth_frames': len(pairs), 'paired_frames': n,
            'excluded_depth_frames': len(pairs)-n, 'map_points': len(points),
            'capture_sha256': digest(capture_raw), 'reconstruction_sha256': digest(report_raw),
            'cloud_sha256': checked['cloud_sha256'], 'input_package_sha256': package['sha256'],
            'scene_coverage': None, 'independent_accuracy_verified': False}


def reconstruct(scene, root):
    import open3d as o3d
    from experiments.scripts.run_nyu_open3d import OPTIONS, geometric_check
    scene = Path(scene).resolve(strict=True)
    root = Path(root).resolve()
    if root.is_relative_to(scene) or scene.is_relative_to(root):
        raise ValueError('isolated_output_required')
    root.mkdir(parents=True, exist_ok=False)
    implementation = {n: digest(Path(n).read_bytes()) for n in IMPLEMENTATION}
    capture = inventory(scene)
    capture_sha = write_json(root/'capture.json', capture)
    pairs = [p for p in capture['pairs'] if p['accepted']]
    if len(pairs) < 2:
        raise ValueError('insufficient_paired_frames')
    k = DEPTH_K
    intrinsic = o3d.camera.PinholeCameraIntrinsic(640, 480, float(k[0]), float(k[1]), float(k[2]-1), float(k[3]-1))
    options = o3d.pipelines.odometry.OdometryOption(o3d.utility.IntVector(OPTIONS['iterations']),
                                                 OPTIONS['depth_diff_max_m'], 0., 10.)
    jacobian = o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm()

    def load(pair):
        depth = read_pnm(checked_read(scene, pair['depth'], capture), True)
        rgb = read_pnm(checked_read(scene, pair['rgb'], capture))
        full = make_cloud(depth, rgb, 1)
        d, c, _ = rasterize_depth_cloud(full[0], full[1], full[3])
        image = o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(c), o3d.geometry.Image(d),
                    depth_scale=1., depth_trunc=10., convert_rgb_to_intensity=True)
        return image, make_cloud(depth, rgb, 4)

    def compute(a, b):
        ok, matrix, _ = o3d.pipelines.odometry.compute_rgbd_odometry(a[0], b[0], intrinsic, np.eye(4), jacobian, options)
        result = geometric_check(a[1][0], b[1][0], b[1][2], matrix, bool(ok))
        return {**result, 'T_target_source': matrix.tolist(), 'library_solver_success': bool(ok)}

    begin = time.perf_counter()
    poses, edges, points, colors = trace(pairs, load, compute, OPTIONS)
    # Recheck the entire recording, including excluded/unused members.
    unchanged = inventory(scene) == capture and implementation == {n: digest(Path(n).read_bytes()) for n in IMPLEMENTATION}
    completed = len(poses) == len(pairs) and unchanged
    report = {'profile': 'cospace.nyu-sequence-reconstruction/0.1', 'scene': scene.name,
              'capture_sha256': capture_sha, 'method': 'open3d_hybrid_rgbd_odometry_fixed_gates',
              'options': OPTIONS, 'geometry_gates': CONFIG, 'sampling_stride': 4, 'voxel_m': VOXEL_M,
              'open3d': o3d.__version__, 'python': sys.version, 'platform': platform.platform(),
              'result': {'completed': completed, 'source_unchanged': unchanged,
                         'source_depth_frames': capture['depth_frames'], 'paired_frames': len(pairs),
                         'excluded_depth_frames': capture['depth_frames']-len(pairs), 'used_frames': len(poses)},
              'edges': edges, 'T_anchor_camera': poses, 'wall_seconds': time.perf_counter()-begin,
              'frame_id': 'first_depth_camera_anchor', 'axes': ['right', 'down', 'forward'], 'unit': 'm',
              'scene_coverage': None, 'independent_accuracy_verified': False, 'robot_ready': False,
              'limitations': ['no_loop_closure_or_pose_graph', 'no_independent_reference',
                             'color_registration_not_independently_verified', 'no_free_space_inference',
                             'no_surface_fusion_or_inpainting', 'filename_time_unverified_utc'],
              'implementation_sha256': implementation}
    cloud = None
    if completed:
        all_points, all_colors = np.concatenate(points), np.concatenate(colors)
        map_points, map_colors = voxel_observations(all_points, all_colors)
        cloud = binary_ply(map_points, map_colors)
        report['map'] = {'sha256': digest(cloud), 'bytes': len(cloud), 'points': len(map_points),
                         'sampled_observations': len(all_points),
                         'bounds_m': [map_points.min(axis=0).tolist(), map_points.max(axis=0).tolist()]}
    report_sha = write_json(root/'reconstruction.json', report)
    if not completed:
        print(json.dumps({'status': 'rejected', 'result': report['result'],
                          'reasons': (edges[-1]['reasons'] if edges else []) + ([] if unchanged else ['source_or_tool_changed'])}), flush=True)
        return False
    bundle = package_map(root, report_sha, cloud, report['map']['points'], scene.name)
    from packages.data.preview_pointcloud import read_cloud
    read_cloud(root/'snapshot')
    write_json(root/'ready.json', {'profile': 'cospace.nyu-map-handover/0.1',
               'capture_sha256': capture_sha, 'reconstruction_sha256': report_sha,
               'cloud_sha256': digest(cloud), 'input_package': bundle,
               'scene_coverage': None, 'independent_accuracy_verified': False})
    verify_artifacts(root)
    print(json.dumps({'status': 'ready', 'result': report['result'], 'map': report['map'], 'input_package': bundle}), flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not reconstruct(args.scene, args.output):
        raise SystemExit(3)


if __name__ == '__main__':
    main()
