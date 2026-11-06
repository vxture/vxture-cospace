"""Prepare a different-content prefix of one recorded RGB-D scene, without retracking.

Original image bytes and anchor-relative poses are retained. This is an imported
workflow sample, not another field acquisition or an accuracy experiment.
"""
import argparse
import json
from pathlib import Path
import shutil

from experiments.scripts.pack_input_upload import pack
from packages.construction.preview_model import digest
from packages.data.preview_inputs import inspect


def prepare(snapshot, tracking, output, frames):
    snapshot = Path(snapshot).resolve()
    tracking = Path(tracking).resolve()
    output = Path(output).resolve()
    if (output.exists() or output.is_relative_to(snapshot) or snapshot.is_relative_to(output)
            or tracking.is_relative_to(output)):
        raise ValueError('exclusive_output_outside_source_required')
    inspected = inspect(snapshot, tracking)
    if not isinstance(frames, int) or isinstance(frames, bool) or not 1 <= frames < inspected['used_frames']:
        raise ValueError('strictly_shorter_observed_prefix_required')
    original = json.loads((snapshot / 'report.json').read_bytes())
    poses = json.loads(tracking.read_bytes())
    pairs = [p for p in original['pairs'] if p['accepted']][:frames]
    names = {pair[role] for pair in pairs for role in ('depth', 'rgb')}
    provenance = {
        'kind': 'same_recorded_sequence_prefix', 'field_acquisition': False,
        'source_report_sha256': inspected['snapshot_sha256'],
        'source_tracking_sha256': inspected['tracking_sha256'],
        'source_input_frames': inspected['input_frames'],
        'source_used_frames': inspected['used_frames'], 'selected_prefix_frames': frames,
        'anchor': 'original_first_depth_camera', 'poses_reestimated': False,
    }
    report = {k: v for k, v in original.items() if k not in (
        'pairs', 'members', 'selected_pair', 'cloud', 'implementation_sha256',
    )}
    report.update(pairs=pairs, members={n: original['members'][n] for n in sorted(names)}, sample_derivation=provenance)
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'snapshot'
    (target / 'raw').mkdir(parents=True)
    for name in sorted(names):
        shutil.copyfile(snapshot / 'raw' / name, target / 'raw' / name)
    save(target / 'report.json', report)
    new_tracking = {
        'schema_version': poses['schema_version'], 'mode': 'reuse_existing_prefix_poses',
        'source_report_sha256': digest(target / 'report.json'),
        'prefix_T_anchor_camera': poses['prefix_T_anchor_camera'][:frames],
        'sample_derivation': provenance, 'algorithm_ready': False,
        'real_release_ready': False, 'independent_accuracy_verified': False,
        'limitations': ['workflow_sample_only', 'estimated_original_poses', 'not_new_field_acquisition'],
    }
    save(output / 'tracking.json', new_tracking)
    checked = inspect(target, output / 'tracking.json')
    result = pack(target, output / 'tracking.json', output / 'input.zip')
    assert digest(snapshot / 'report.json') == inspected['snapshot_sha256']
    assert digest(tracking) == inspected['tracking_sha256']
    receipt = result | checked | {
        'package_sha256': digest(output / 'input.zip'), 'sample_derivation': provenance,
        'image_bytes_reused': True, 'quality': 'unverified', 'robot_ready': False,
    }
    save(output / 'preparation.json', receipt)
    return receipt


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--tracking', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.snapshot, args.tracking, args.output, args.frames), ensure_ascii=False))
