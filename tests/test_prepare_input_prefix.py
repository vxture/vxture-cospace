"""Sample preparation preserves source bytes/poses; no geometry accuracy claims."""
import json
import pytest

from experiments.scripts.prepare_input_prefix import prepare
from packages.construction.preview_model import digest
from packages.data.preview_inputs import inspect
from test_preview_inputs import source


def two_frame_source(tmp_path):
    snapshot, tracking = source(tmp_path)
    report = json.loads((snapshot / 'report.json').read_bytes())
    report['pairs'] *= 2
    report.update(cloud={'old': 'not_retained'}, selected_pair={'old': 'not_retained'})
    (snapshot / 'report.json').write_text(json.dumps(report), encoding='utf-8')
    poses = json.loads(tracking.read_bytes())
    poses.update(schema_version='cospace.open3d-rgbd-experiment/0.1',
                 source_report_sha256=digest(snapshot / 'report.json'))
    poses['prefix_T_anchor_camera'] *= 2
    tracking.write_text(json.dumps(poses), encoding='utf-8')
    return snapshot, tracking


def test_prefix_retains_bytes_and_anchor_and_records_real_derivation(tmp_path):
    snapshot, tracking = two_frame_source(tmp_path / 'source')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    output = tmp_path / 'prefix'
    receipt = prepare(snapshot, tracking, output, 1)
    assert all(p.read_bytes() == data for p, data in before.items())
    assert receipt['used_frames'] == receipt['input_frames'] == 1
    assert receipt['sample_derivation']['source_input_frames'] == 2
    assert receipt['sample_derivation']['field_acquisition'] is False
    report = json.loads((output / 'snapshot/report.json').read_bytes())
    assert 'cloud' not in report and 'selected_pair' not in report
    for name in report['members']:
        assert (output / 'snapshot/raw' / name).read_bytes() == (snapshot / 'raw' / name).read_bytes()
    poses = json.loads((output / 'tracking.json').read_bytes())
    assert poses['prefix_T_anchor_camera'] == json.loads(tracking.read_bytes())['prefix_T_anchor_camera'][:1]
    assert inspect(output / 'snapshot', output / 'tracking.json')['used_frames'] == 1
    assert receipt['snapshot_sha256'] != digest(snapshot / 'report.json')


@pytest.mark.parametrize('count', [0, 2, 3, True])
def test_requires_strictly_shorter_observed_prefix(tmp_path, count):
    snapshot, tracking = two_frame_source(tmp_path / 'source')
    with pytest.raises(ValueError, match='strictly_shorter_observed_prefix_required'):
        prepare(snapshot, tracking, tmp_path / 'output', count)
    assert not (tmp_path / 'output').exists()


def test_output_cannot_replace_or_nest_source(tmp_path):
    snapshot, tracking = two_frame_source(tmp_path / 'source')
    for output in (snapshot, snapshot / 'nested', tmp_path / 'source'):
        with pytest.raises(ValueError, match='exclusive_output_outside_source_required'):
            prepare(snapshot, tracking, output, 1)
