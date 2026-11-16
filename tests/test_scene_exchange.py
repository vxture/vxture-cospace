import json
from pathlib import Path
import shutil
import subprocess

import pytest

from experiments.scripts.scene_graph_sample import sample
from packages.spatial.scene_identity import snapshot_ref
from packages.views.agent.scene_exchange import write_exchange
from packages.views.agent.scene_subset import build_scene_subset

NODE = shutil.which('node')
CONSUMER = Path('examples/scene-graph/consumers/read-subset.mjs')


@pytest.fixture
def exchange(tmp_path):
    source = sample()
    pin = snapshot_ref(source)
    directory = tmp_path / 'exchange'
    package = build_scene_subset(source, ['corridor-l1'])
    write_exchange(package, pin, directory, allowed_root=tmp_path)
    pin_path = tmp_path / 'pin.json'
    pin_path.write_text(json.dumps(pin), encoding='utf-8')
    return directory, pin_path, pin


def run_consumer(exchange, operation='connections', identity='corridor-l1'):
    if not NODE:
        pytest.skip('Node.js required for independent consumer')
    directory, pin_path, _ = exchange
    return subprocess.run([NODE, str(CONSUMER), str(directory), str(pin_path), operation, identity],
                          capture_output=True, text=True, encoding='utf-8', timeout=15)


def test_independent_consumer_verifies_exact_bytes_including_python_float_serialization(exchange):
    directory, _, _ = exchange
    assert b'1.9' in (directory / 'geometry.json').read_bytes()
    result = run_consumer(exchange)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [row['id'] for row in report['items']] == ['connection-door-l1', 'connection-stair']
    assert report['incident_connections_complete'] is report['real_release_ready'] is False
    assert json.loads(run_consumer(exchange, 'entity', 'door-l1').stdout)['items'][0]['entity']['id'] == 'door-l1'
    assert json.loads(run_consumer(exchange, 'entity', 'cabinet').stdout)['outcome'] == 'out_of_scope'


@pytest.mark.parametrize('problem', ['digest', 'missing', 'pin', 'profile', 'dependencies', 'bytes', 'reference', 'nonfinite'])
def test_independent_consumer_rejects_bad_exchange(exchange, problem):
    from hashlib import sha256
    directory, pin_path, pin = exchange
    path = directory / 'manifest.json'
    wrapper = json.loads(path.read_bytes())
    if problem == 'digest':
        (directory / 'geometry.json').write_bytes(b'[]')
    elif problem == 'missing':
        (directory / 'structure.json').unlink()
    elif problem == 'pin':
        pin['sha256'] = '0' * 64
        pin_path.write_text(json.dumps(pin), encoding='utf-8')
    elif problem == 'profile':
        wrapper['manifest']['data_kind'] = 'real'
    elif problem == 'dependencies':
        wrapper['manifest']['components'][1]['depends_on'] = []
    elif problem == 'bytes':
        wrapper['manifest']['components'][0]['bytes'] = 3 * 1024 * 1024
    elif problem == 'reference':
        payload = json.loads((directory / 'structure.json').read_bytes())
        payload['connections'][0]['ports'][0]['space_id'] = 'missing'
        raw = json.dumps(payload).encode()
        (directory / 'structure.json').write_bytes(raw)
        entry = next(row for row in wrapper['manifest']['components'] if row['role'] == 'structure')
        entry.update(bytes=len(raw), sha256=sha256(raw).hexdigest())
    elif problem == 'nonfinite':
        raw = (directory / 'geometry.json').read_bytes().replace(b'1.9', b'1e999', 1)
        (directory / 'geometry.json').write_bytes(raw)
        entry = next(row for row in wrapper['manifest']['components'] if row['role'] == 'geometry')
        entry.update(bytes=len(raw), sha256=sha256(raw).hexdigest())
    path.write_text(json.dumps(wrapper), encoding='utf-8')
    assert run_consumer(exchange).returncode == 2


def test_export_refuses_wrong_source_or_existing_output(tmp_path):
    source = sample()
    pin = snapshot_ref(source)
    package = build_scene_subset(source, ['corridor-l1'])
    with pytest.raises(ValueError, match='source_binding'):
        write_exchange(package, dict(pin, sha256='0' * 64), tmp_path / 'wrong')
    assert not (tmp_path / 'wrong').exists()
    with pytest.raises(FileExistsError):
        write_exchange(package, pin, tmp_path, allowed_root=tmp_path.parent)


def test_end_to_end_trial_two_consumers_and_all_state_outcomes(tmp_path):
    if not NODE:
        pytest.skip('Node.js required for independent consumer')
    from experiments.scripts.scene_evolution_trial import run_trial
    report = run_trial(tmp_path / 'trial', allowed_root=tmp_path)
    assert report['independent_consumers_agree'] is True
    assert report['state_statuses'] == {key: key for key in ('known', 'expired', 'unavailable', 'unknown', 'conflict')}
    assert report['real_release_ready'] is False
    assert (tmp_path / 'trial/index.html').is_file()


def test_output_root_and_member_names_cannot_escape(tmp_path):
    from packages.infrastructure.local_output import new_output_directory, write_member
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    outside = tmp_path / 'outside'
    with pytest.raises(ValueError, match='outside_allowed_root'):
        new_output_directory(allowed / '../outside', allowed_root=allowed)
    assert not outside.exists()
    root = new_output_directory(allowed / 'new', allowed_root=allowed)
    with pytest.raises(ValueError, match='member_name'):
        write_member(root, '../outside', b'bad')
    write_member(root, 'one.json', b'{}')
    with pytest.raises(FileExistsError):
        write_member(root, 'one.json', b'changed')
