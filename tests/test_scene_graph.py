"""Spatial facts must not silently become device navigation decisions."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from experiments.scripts.inspect_scene_graph import load_graph, main
from experiments.scripts.inventory_scene_structure import inventory
from experiments.scripts.scene_graph_sample import sample
from packages.spatial.scene_graph import MAX_DOCUMENT_BYTES, SceneGraph, SceneGraphReader, validate_scene_graph

SCHEMA = Path('contracts/schemas/synthetic-scene-graph-v0.1.schema.json')
EXAMPLE = Path('examples/scene-graph/two-level.synthetic.json')


@pytest.fixture
def graph():
    return sample()


def test_checked_in_contract_and_example_match_models():
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    expected = SceneGraph.model_json_schema()
    assert {k: v for k, v in schema.items() if k not in {'$schema', '$id'}} == expected
    example = load_graph(EXAMPLE)
    assert example == sample()
    Draft202012Validator(schema).validate(example)
    report = validate_scene_graph(example)
    assert report['counts'] == dict(entities=11, geometry=17, relations=12, connections=3, observations=1)
    assert all(report[key] is False for key in ('evidence_verified', 'geometry_verified',
                                               'real_release_ready', 'robot_ready'))


def test_closed_door_keeps_structural_connection_without_device_conclusion(graph):
    reader = SceneGraphReader(graph)
    links = reader.connections('corridor-l1')
    assert {link['mode'] for link in links} == {'opening', 'stair_transition'}
    assert graph['observations'][0]['value'] == 'closed'
    assert all('traversable' not in c and 'reachable' not in c and 'cost' not in c for c in links)


def test_pin_snapshot_and_copy_results(graph):
    reader = SceneGraphReader(graph)
    graph['entities'][-1]['name'] = 'changed'
    first = reader.entity('cabinet')
    first['entity']['name'] = 'changed again'
    first['geometry'].clear()
    assert reader.entity('cabinet')['entity']['name'] == '配电柜'
    assert reader.entity('cabinet')['geometry']
    links = reader.connections('corridor-l1')
    links.clear()
    assert len(reader.connections('corridor-l1')) == 2


@pytest.mark.parametrize('collection', ['entities', 'geometry', 'relations', 'connections',
                                       'observations', 'evidence', 'sources'])
def test_duplicate_ids_rejected(graph, collection):
    graph[collection].append(deepcopy(graph[collection][0]))
    with pytest.raises(ValueError, match='duplicate_'):
        validate_scene_graph(graph)


@pytest.mark.parametrize('change,error', [
    (lambda g: g.update(data_kind='real'), 'scene_graph_structure'),
    (lambda g: g.update(robot_ready=True), 'scene_graph_structure'),
    (lambda g: g['entities'][0].update(traversable=True), 'scene_graph_structure'),
    (lambda g: g['entities'][0].update(revision=True), 'scene_graph_structure'),
    (lambda g: g['entities'][0].update(type_id='missing'), 'entity_type_kind'),
    (lambda g: g['entities'][0].update(geometry_ids=['missing']), 'entity_geometry_binding'),
    (lambda g: g['entities'][0].update(evidence_ids=['missing']), 'invalid_evidence_reference'),
    (lambda g: g['geometry'][0].update(frame_id='other'), 'geometry_frame_mismatch'),
    (lambda g: g['geometry'][0].update(entity_id='missing'), 'entity_geometry_binding'),
    (lambda g: g['geometry'][0]['value']['bounds'][0].__setitem__(0, float('nan')), 'scene_graph_structure'),
    (lambda g: g['geometry'][0]['value']['bounds'][0].__setitem__(0, float('inf')), 'scene_graph_structure'),
    (lambda g: g['geometry'][0]['value']['bounds'][0].__setitem__(0, 1e308), 'scene_graph_structure'),
    (lambda g: g['geometry'][0]['value']['bounds'][1].__setitem__(0, 0), 'invalid_bounds'),
    (lambda g: g['geometry'][0].update(role='reference_point'), 'geometry_role_shape'),
    (lambda g: g['relations'][0].update(target_id='missing'), 'relation_endpoint'),
    (lambda g: g['relations'][0].update(target_id='building'), 'relation_endpoint'),
    (lambda g: g['relations'][0].update(source_id='cabinet'), 'relation_endpoint_kind'),
    (lambda g: g['connections'][0].update(connector_id='cabinet'), 'connection_connector_role'),
    (lambda g: g['connections'][0].update(mode='stair_transition'), 'connection_connector_role'),
    (lambda g: g['connections'][0]['ports'][0].update(space_id='missing'), 'connection_spaces'),
    (lambda g: g['connections'][0]['ports'][0].update(space_id='cabinet'), 'connection_spaces'),
    (lambda g: g['connections'][0]['ports'][0].update(geometry_id='missing'), 'connection_port_binding'),
    (lambda g: g['connections'][0]['ports'][0].update(geometry_id='door-l2-port-a'), 'connection_port_binding'),
    (lambda g: g['connections'][0]['ports'][0].update(geometry_id='door-l1-bounds'), 'connection_port_binding'),
    (lambda g: g['connections'][0]['ports'][0].update(geometry_id='door-l1-port-b'), 'duplicate_connection_port'),
    (lambda g: g['observations'][0].update(entity_id='cabinet'), 'observation_subject_role'),
    (lambda g: g['observations'][0].update(source_id='missing'), 'observation_source'),
    (lambda g: g['observations'][0].update(valid_until='2026-11-15T00:00:00Z'), 'invalid_observation_interval'),
    (lambda g: g['observations'][0].update(observed_at='2026-02-30T00:00:00Z'), 'invalid_timestamp'),
    (lambda g: g['observations'][0].update(received_at='2026-11-16T00:00:00+08:00'), 'utc_required'),
    (lambda g: g['observations'][0].update(received_at='2026-11-15T00:00:00Z'), 'received_before_observed'),
])
def test_invalid_spatial_facts(graph, change, error):
    change(graph)
    with pytest.raises(ValueError, match=error):
        validate_scene_graph(graph)


@pytest.mark.parametrize('field,value', [('vertices', [[0., 0., 0.]]*4)])
def test_degenerate_port_rejected(graph, field, value):
    item = next(g for g in graph['geometry'] if g['role'] == 'connection_port')
    item['value'][field] = value
    with pytest.raises(ValueError, match='invalid_rectangle'):
        validate_scene_graph(graph)


def test_missing_geometry_reverse_binding(graph):
    extra = deepcopy(graph['geometry'][0])
    extra['id'] = 'orphan'
    graph['geometry'].append(extra)
    with pytest.raises(ValueError, match='geometry_entity_binding'):
        validate_scene_graph(graph)


def test_reference_point_does_not_invent_an_object_extent(graph):
    item = next(g for g in graph['geometry'] if g['entity_id'] == 'cabinet')
    item.update(role='reference_point', value={'shape': 'point', 'position': [1., 6., 0.]})
    result = SceneGraphReader(graph).entity('cabinet')
    assert result['geometry'][0]['role'] == 'reference_point'
    assert result['geometry'][0]['value'] == {'shape': 'point', 'position': [1., 6., 0.]}


@pytest.mark.parametrize('vertices', [
    [[0., 0., 0.], [1., 0., 0.], [1., 1., .1], [0., 1., 0.]],
    [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]],
    [[0., 0., 0.], [1., 0., 0.], [1.5, 1., 0.], [.5, 1., 0.]],
])
def test_nonplanar_crossed_or_skewed_ports_rejected(graph, vertices):
    item = next(g for g in graph['geometry'] if g['role'] == 'connection_port')
    item['value']['vertices'] = vertices
    with pytest.raises(ValueError, match='invalid_rectangle'):
        validate_scene_graph(graph)


def test_cross_level_connector_is_not_forced_into_two_spatial_parents(graph):
    graph['relations'].append({'id': 'door-building', 'type': 'part_of', 'source_id': 'door-l1',
                               'target_id': 'building', 'evidence_ids': ['fixture'], 'assessment': 'unverified'})
    assert validate_scene_graph(graph)['metadata_valid']
    assert {p['space_id'] for p in graph['connections'][-1]['ports']} == {'corridor-l1', 'corridor-l2'}


def test_multiple_spatial_parents_not_allowed(graph):
    other = deepcopy(graph['relations'][-1])
    other.update(id='other-parent', source_id='corridor-l1')
    graph['relations'].append(other)
    with pytest.raises(ValueError, match='multiple_parents'):
        validate_scene_graph(graph)


def test_structural_composition_has_own_cycle_rule(graph):
    for a, b in [('door-l1', 'stair'), ('stair', 'door-l1')]:
        graph['relations'].append({'id': 'part-'+a, 'type': 'part_of', 'source_id': a,
                                   'target_id': b, 'evidence_ids': ['fixture'], 'assessment': 'unverified'})
    with pytest.raises(ValueError, match='relation_cycle'):
        validate_scene_graph(graph)


def test_reversed_adjacency_and_duplicate_connection_rejected(graph):
    relation = deepcopy(next(r for r in graph['relations'] if r['type'] == 'adjacent_to'))
    relation.update(id='reverse', source_id=relation['target_id'], target_id=relation['source_id'])
    graph['relations'].append(relation)
    with pytest.raises(ValueError, match='duplicate_relation_assertion'):
        validate_scene_graph(graph)
    graph['relations'].pop()
    connection = deepcopy(graph['connections'][0])
    connection['id'] = 'duplicate-connection'
    graph['connections'].append(connection)
    with pytest.raises(ValueError, match='duplicate_connection_assertion'):
        validate_scene_graph(graph)


def test_late_observation_is_retained_not_resolved(graph):
    event = deepcopy(graph['observations'][0])
    event.update(id='late', value='open', received_at='2026-11-17T00:00:00Z')
    graph['observations'].append(event)
    report = validate_scene_graph(graph)
    assert report['counts']['observations'] == 2
    assert 'no_state_resolution' in report['limitations']


def test_reader_errors(graph):
    reader = SceneGraphReader(graph)
    with pytest.raises(ValueError, match='entity_not_found'):
        reader.entity('missing')
    with pytest.raises(ValueError, match='space_required'):
        reader.connections('cabinet')


def test_document_budget_and_duplicate_keys(tmp_path):
    path = tmp_path/'input.json'
    path.write_bytes(b' '*(MAX_DOCUMENT_BYTES+1))
    with pytest.raises(ValueError, match='document_byte_budget'):
        load_graph(path)
    path.write_text('{"profile":1,"profile":2}', encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate_json_key'):
        load_graph(path)


def test_cli_read_only_success_and_error(monkeypatch, capsys, tmp_path):
    path = tmp_path/'sample.json'
    path.write_text(json.dumps(sample()), encoding='utf-8')
    before = path.read_bytes()
    monkeypatch.setattr('sys.argv', ['inspect', str(path), '--entity', 'cabinet',
                                     '--connections-for', 'corridor-l1'])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)['entity']['entity']['id'] == 'cabinet'
    assert path.read_bytes() == before
    monkeypatch.setattr('sys.argv', ['inspect', str(path), '--entity', 'missing'])
    assert main() == 2
    assert 'entity_not_found' in capsys.readouterr().out


def test_ifc_inventory_counts_not_strings_and_does_not_claim_geometry(tmp_path):
    path = tmp_path/'synthetic.ifc'
    path.write_text("FILE_SCHEMA(('IFC4'));\n#1=IFCSPACE('name #2=IFCDOOR( )');\n"
                    "/* #3=IFCSTAIR(); */\n#4=IFCBUILDINGSTOREY();", encoding='utf-8')
    before = path.read_bytes()
    result = inventory(path)
    assert result['declaration_counts']['IFCSPACE'] == 1
    assert result['declaration_counts']['IFCDOOR'] == result['declaration_counts']['IFCSTAIR'] == 0
    assert not result['geometry_decoded'] and not result['alignment_verified']
    assert path.read_bytes() == before
