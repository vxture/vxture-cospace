"""P28 whole-recording bookkeeping and continuity, independent of Open3D."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from experiments.scripts import build_nyu_sequence_map as tool
from packages.data.preview_pointcloud import read_cloud
from packages.data.input_uploads import unpack


def recording(tmp_path):
    root = tmp_path/'office'; root.mkdir()
    for name in ('d-100.000000-1.pgm', 'd-100.050000-2.pgm', 'd-103.000000-3.pgm',
                 'r-99.990000-1.ppm', 'r-100.010000-2.ppm', 'r-103.010000-3.ppm',
                 'a-100.000000-1.dump'):
        (root/name).write_bytes(name.encode())
    return root


def test_inventory_whole_recording_ties_exclusions_auxiliary_and_source_integrity(tmp_path):
    root = recording(tmp_path); doc = tool.inventory(root)
    assert doc['selection'] == 'whole_recording' and doc['duration_us'] == 3_000_000
    assert doc['depth_frames'] == 3 and doc['paired_frames'] == 2
    assert doc['pairs'][0]['rgb'] == 'r-99.990000-1.ppm'  # deterministic earlier tie
    assert not doc['pairs'][1]['accepted'] and doc['pairs'][1]['reason']
    assert doc['members']['a-100.000000-1.dump']['kind'] == 'auxiliary'
    assert len(doc['members']) == 7 and doc['scene_coverage'] is None
    name = doc['pairs'][0]['depth']; assert tool.checked_read(root, name, doc)
    (root/name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='source_changed'): tool.checked_read(root, name, doc)


def test_inventory_refuses_missing_duplicate_or_nested_sources(tmp_path):
    root = tmp_path/'empty'; root.mkdir()
    with pytest.raises(ValueError, match='missing_images'): tool.inventory(root)
    root = recording(tmp_path); (root/'d-100.000000-999.pgm').write_bytes(b'duplicate')
    with pytest.raises(ValueError, match='duplicate_source_timestamp'): tool.inventory(root)
    (root/'nested').mkdir()
    with pytest.raises(ValueError, match='single_recording_files_only'): tool.inventory(root)


def observations(i):
    return i, (np.array([[0., 0., 1.], [.011, 0., 1.]]), np.full((2, 3), i, dtype='u1'))


def solver(reject=None, reverse_only=False, inconsistent=False):
    def compute(a, b):
        m = np.eye(4); m[0, 3] = (a[0]-b[0])*.01
        if inconsistent: m[0, 3] = .1
        accepted = a[0] != reject if not reverse_only else b[0] != reject
        return {'accepted': accepted, 'reasons': [] if accepted else ['test_rejection'], 'T_target_source': m.tolist()}
    return compute


OPTIONS = {'cycle_translation_m': .02, 'cycle_rotation_rad': .02}


def test_continuous_trace_composes_real_transforms_and_stops_at_first_failure():
    loaded = []
    def load(i): loaded.append(i); return observations(i)
    poses, edges, points, _ = tool.trace(list(range(5)), load, solver(reject=2), OPTIONS)
    assert loaded == [0, 1, 2] and len(poses) == 2 and len(points) == 2
    assert not edges[-1]['accepted'] and edges[-1]['current_frame'] == 2
    assert poses[-1][0][3] == pytest.approx(.01)
    assert points[-1][0, 0] == pytest.approx(.01)


@pytest.mark.parametrize('kwargs,reason', [({'reject': 2, 'reverse_only': True}, 'reverse_registration_rejected'),
                                         ({'inconsistent': True}, 'bidirectional_inconsistent')])
def test_reverse_or_cycle_failure_never_becomes_a_pose(kwargs, reason):
    poses, edges, points, _ = tool.trace(list(range(5)), observations, solver(**kwargs), OPTIONS)
    assert reason in edges[-1]['reasons'] and len(poses) < 5
    assert len(poses) == len(points) == len(edges)


def test_voxel_keeps_observations_without_filling_holes_and_binary_intake(tmp_path):
    points = np.array([[.001, 0., 1.], [.009, 0., 1.], [.031, 0., 1.]])
    colors = np.array([[1, 2, 3], [9, 9, 9], [4, 5, 6]], dtype='u1')
    p, c = tool.voxel_observations(points, colors)
    assert len(p) == 2 and c.tolist() == [[1, 2, 3], [4, 5, 6]]
    bundle = tool.package_map(tmp_path, 'a'*64, tool.binary_ply(p, c), len(p), 'test-office')
    checked, actual, actual_colors, doc = read_cloud(tmp_path/'snapshot')
    np.testing.assert_array_equal(actual, p); np.testing.assert_array_equal(actual_colors, c)
    assert checked['frame_id'] == 'first_depth_camera_anchor' and doc['provenance']['source_manifest_sha256'] == 'a'*64
    assert bundle['sha256'] == tool.digest((tmp_path/'input.zip').read_bytes())
    expanded = tmp_path/'expanded'; expanded.mkdir()
    assert unpack(tmp_path/'input.zip', expanded)[0] == 'ply_pointcloud'
    with pytest.raises(FileExistsError): tool.write_json(tmp_path/'input.json', {})


@pytest.mark.parametrize('bad', [np.array([[np.nan, 0., 1.]]), np.array([[1e8, 0., 1.]]), np.empty((0, 3))])
def test_nonfinite_unsafe_empty_maps_rejected(bad):
    with pytest.raises(ValueError): tool.voxel_observations(bad, np.zeros(bad.shape, dtype='u1'))


def artifacts(tmp_path):
    source = recording(tmp_path)
    root = tmp_path/'handover'; root.mkdir()
    capture = tool.inventory(source); capture_sha = tool.write_json(root/'capture.json', capture)
    poses, edges, points, colors = tool.trace([0, 1], observations, solver(), OPTIONS)
    p, c = tool.voxel_observations(np.concatenate(points), np.concatenate(colors)); cloud = tool.binary_ply(p, c)
    report = {'profile': 'cospace.nyu-sequence-reconstruction/0.1', 'capture_sha256': capture_sha,
              'result': {'completed': True, 'source_unchanged': True, 'source_depth_frames': 3,
                         'paired_frames': 2, 'used_frames': 2, 'excluded_depth_frames': 1},
              'edges': edges, 'T_anchor_camera': poses, 'scene_coverage': None,
              'independent_accuracy_verified': False, 'robot_ready': False, 'frame_id': 'first_depth_camera_anchor',
              'axes': ['right', 'down', 'forward'], 'map': {'sha256': tool.digest(cloud), 'bytes': len(cloud), 'points': len(p)}}
    report_sha = tool.write_json(root/'reconstruction.json', report)
    bundle = tool.package_map(root, report_sha, cloud, len(p), 'test-office')
    ready = {'capture_sha256': capture_sha, 'reconstruction_sha256': report_sha,
             'cloud_sha256': tool.digest(cloud), 'input_package': bundle}
    tool.write_json(root/'ready.json', ready)
    return root


def test_transferable_reports_cloud_and_package_are_bound(tmp_path):
    root = artifacts(tmp_path); result = tool.verify_artifacts(root)
    assert result['status'] == 'passed' and result['source_depth_frames'] == 3 and result['paired_frames'] == 2
    assert result['excluded_depth_frames'] == 1 and result['scene_coverage'] is None


@pytest.mark.parametrize('member', ['capture.json', 'reconstruction.json', 'snapshot/cloud.ply', 'input.zip'])
def test_handover_tampering_rejected(tmp_path, member):
    root = artifacts(tmp_path); path = root/member; path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError): tool.verify_artifacts(root)


@pytest.mark.parametrize('change', [lambda r: r['result'].update(completed=False),
                                  lambda r: r['result'].update(source_unchanged=False),
                                  lambda r: r['result'].update(used_frames=1),
                                  lambda r: r.update(scene_coverage=1.0),
                                  lambda r: r.update(robot_ready=True),
                                  lambda r: r['edges'][0].update(current_frame=3),
                                  lambda r: r['edges'][0].update(accepted=False)])
def test_self_consistent_report_digest_does_not_hide_incomplete_or_false_claim(tmp_path, change):
    root = artifacts(tmp_path); report = json.loads((root/'reconstruction.json').read_bytes()); change(report)
    raw = json.dumps(report).encode(); (root/'reconstruction.json').write_bytes(raw)
    ready = json.loads((root/'ready.json').read_bytes()); ready['reconstruction_sha256'] = tool.digest(raw)
    (root/'ready.json').write_text(json.dumps(ready))
    with pytest.raises(ValueError): tool.verify_artifacts(root)
