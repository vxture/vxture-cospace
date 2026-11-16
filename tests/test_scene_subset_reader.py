import json
from pathlib import Path

import pytest

from experiments.scripts.consume_scene_subset import load, main
from experiments.scripts.scene_graph_sample import sample
from packages.spatial.scene_identity import canonical, content_digest, snapshot_ref
from packages.views.agent.scene_reader import SceneSubsetReader
from packages.views.agent.scene_subset import build_scene_subset


@pytest.fixture
def inputs():
    source = sample()
    return source, build_scene_subset(source, ['corridor-l1']), snapshot_ref(source)


def test_catalog_and_entity_queries_are_package_local(inputs):
    source, package, pin = inputs
    reader = SceneSubsetReader(package, pin, source_document=source)
    rows = reader.list_entities(type_id='corridor')['items']
    assert [row['id'] for row in rows] == ['corridor-l1', 'corridor-l2']
    assert reader.list_entities(type_id='cabinet')['outcome'] == 'no_match'
    assert reader.entity('cabinet')['outcome'] == 'out_of_scope'
    result = reader.entity('door-l1')
    assert result['outcome'] == 'found'
    assert result['items'][0]['entity']['assessment'] == 'unverified'
    assert len(result['items'][0]['geometry']) == 3
    assert result['items'][0]['observations'][0]['value'] == 'closed'
    assert result['context']['observation_resolution'] == 'not_applied'
    assert result['context']['validation']['full_scene_coverage'] is False
    assert result['context']['source'] == pin


def test_connection_closure_does_not_expand_dependency_neighbors(inputs):
    source, package, pin = inputs
    reader = SceneSubsetReader(package, pin, source_document=source)
    requested = reader.connections('corridor-l1')
    assert [row['id'] for row in requested['items']] == ['connection-door-l1', 'connection-stair']
    assert requested['incident_connections_complete'] is True
    dependency = reader.connections('corridor-l2')
    assert [row['id'] for row in dependency['items']] == ['connection-stair']
    assert dependency['incident_connections_complete'] is False
    assert reader.connections('door-l2')['outcome'] == 'out_of_scope'
    assert reader.connections('room-l1')['incident_connections_complete'] is False
    # The closed observation does not remove the structural door connection.
    assert reader.connections('door-l1')['items'][0]['id'] == 'connection-door-l1'


def test_package_only_cannot_assert_source_selection_completeness(inputs):
    _, package, pin = inputs
    result = SceneSubsetReader(package, pin).connections('corridor-l1')
    assert result['incident_connections_complete'] is False
    assert result['context']['validation']['source_content_verified'] is False


def test_returned_data_and_input_mutations_do_not_modify_reader(inputs):
    source, package, pin = inputs
    reader = SceneSubsetReader(package, pin, source_document=source)
    source['connections'].clear()
    package['payloads']['structure']['connections'].clear()
    pin['snapshot_id'] = 'changed'
    reader.context['validation']['source_content_verified'] = False
    reader.list_entities()['items'].clear()
    reader.entity('door-l1')['items'][0]['geometry'].clear()
    reader.connections('corridor-l1')['items'].clear()
    assert len(reader.connections('corridor-l1')['items']) == 2
    assert len(reader.entity('door-l1')['items'][0]['geometry']) == 3
    assert reader.context['source']['snapshot_id'] == 'synthetic-snapshot-01'
    assert reader.context['validation']['source_content_verified'] is True


@pytest.mark.parametrize('problem,error', [('pin', 'source_binding'), ('payload', 'component_integrity'),
                                         ('source', 'source_binding'), ('real', 'manifest_structure')])
def test_pin_integrity_and_real_data_rejection(inputs, problem, error):
    source, package, pin = inputs
    if problem == 'pin':
        pin['sha256'] = '0' * 64
    elif problem == 'payload':
        package['payloads']['entities']['entities'][0]['name'] = 'changed'
    elif problem == 'source':
        source['snapshot_id'] = 'other-snapshot'
    elif problem == 'real':
        package['manifest']['data_kind'] = 'real'
    with pytest.raises(ValueError, match=error):
        SceneSubsetReader(package, pin, source_document=source)


def test_self_consistent_omission_is_detected_with_full_source(inputs):
    source, package, pin = inputs
    package['payloads']['structure']['connections'].clear()
    payload = package['payloads']['structure']
    member = next(row for row in package['manifest']['components'] if row['role'] == 'structure')
    member.update(sha256=content_digest(payload), bytes=len(canonical(payload)))
    reader = SceneSubsetReader(package, pin)
    assert reader.connections('corridor-l1')['outcome'] == 'no_match'
    assert reader.connections('corridor-l1')['incident_connections_complete'] is False
    with pytest.raises(ValueError, match='differs_from_source_selection'):
        SceneSubsetReader(package, pin, source_document=source)


@pytest.mark.parametrize('identity', ['', '../door', 1, 'x' * 161])
def test_invalid_query_identity_rejected(inputs, identity):
    _, package, pin = inputs
    reader = SceneSubsetReader(package, pin)
    for query in (reader.entity, reader.connections):
        with pytest.raises(ValueError):
            query(identity)
    with pytest.raises(ValueError):
        reader.list_entities(type_id=identity)


def test_cli_and_bounded_input(inputs, tmp_path, monkeypatch, capsys):
    source, package, pin = inputs
    for name, document in [('package', package), ('pin', pin), ('source', source)]:
        (tmp_path / (name + '.json')).write_text(json.dumps(document), encoding='utf-8')
    arguments = ['consume', '--input-root', str(tmp_path), '--package', str(tmp_path / 'package.json'),
                 '--expected-source', str(tmp_path / 'pin.json'), '--source-document', str(tmp_path / 'source.json'),
                 '--connections-for', 'corridor-l1']
    monkeypatch.setattr('sys.argv', arguments)
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['incident_connections_complete'] is True
    assert result['context']['validation']['real_release_ready'] is False
    (tmp_path / 'pin.json').write_text('{"a":1,"a":2}', encoding='utf-8')
    assert main() == 2
    assert 'duplicate_json_key' in capsys.readouterr().out
    with pytest.raises(ValueError, match='byte_budget'):
        load(tmp_path / 'package.json', tmp_path, 1)
    with pytest.raises(ValueError, match='outside_allowed_root'):
        load(tmp_path / 'package.json', tmp_path / 'source.json', 100)


def test_repository_source_pin_and_consumer_example_agree():
    root = Path('examples/scene-graph')
    source = json.loads((root / 'two-level.synthetic.json').read_bytes())
    pin = json.loads((root / 'source-ref.synthetic.json').read_bytes())
    package = json.loads((root / 'sg1/corridor-subset.synthetic.json').read_bytes())
    assert pin == snapshot_ref(source)
    reader = SceneSubsetReader(package, pin, source_document=source)
    assert reader.connections('corridor-l1')['incident_connections_complete'] is True


@pytest.mark.parametrize('operation', ['--entity', '--connections-for'])
def test_cli_empty_query_does_not_fall_back_to_listing(inputs, tmp_path, monkeypatch, capsys, operation):
    _, package, pin = inputs
    for name, document in [('package', package), ('pin', pin)]:
        (tmp_path / (name + '.json')).write_text(json.dumps(document), encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['consume', '--input-root', str(tmp_path),
                                   '--package', str(tmp_path / 'package.json'),
                                   '--expected-source', str(tmp_path / 'pin.json'), operation, ''])
    assert main() == 2
    assert 'error' in json.loads(capsys.readouterr().out)
