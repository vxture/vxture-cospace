import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from packages.spatial.scene_identity import canonical
from packages.views.agent.ifc_declaration_context import DeclarationContextQuery, query_declaration_context
from test_ifc_structure_exchange import snapshot
from test_ifc_structure_review import structure_source


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def node_context(raw, source, query, expected=None):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    uri = Path('examples/scene-graph/consumers/query-ifc-context.mjs').resolve().as_uri()
    script = ('import {queryDeclarationContext} from ' + json.dumps(uri) + ';'
              "let text='';for await(const chunk of process.stdin){text+=chunk;}const p=JSON.parse(text);"
              "try{process.stdout.write(JSON.stringify(queryDeclarationContext(Buffer.from(p.raw,'base64'),p.expected,p.query)));}"
              "catch(e){process.stderr.write(e.message);process.exitCode=1;}")
    payload = {'raw': base64.b64encode(raw).decode(), 'expected': {'sha256': expected or sha(raw), 'source': source},
               'query': query}
    return subprocess.run([node, '--input-type=module', '-e', script], input=json.dumps(payload),
                          text=True, capture_output=True, timeout=30, check=False, shell=False)


def both(raw, query):
    source = json.loads(raw)['source']
    result = query_declaration_context(raw, expected_sha256=sha(raw), expected_source=source, query=query)
    node = node_context(raw, source, query)
    assert node.returncode == 0, node.stderr
    assert json.loads(node.stdout) == result
    return result


def edge(identity, kind, source, target):
    return {'ifc_relation_id': identity, 'kind': kind, 'source_id': source, 'target_id': target}


def test_door_opening_host_context_and_explicit_boundary(structure_source, monkeypatch):
    raw = snapshot(structure_source)
    def never(*args):
        pytest.fail('context query loaded mesh')
    monkeypatch.setattr('packages.data.ifc_workspace.load_mesh', never)
    value = both(raw, {'element_id': 'e00002'})
    assert value['subject']['entity_id'] == 'door'
    assert {e['entity_id']: e['hop_distance'] for e in value['entities']} == {'door': 0, 'opening': 1}
    assert value['relations'] == [edge('rel-0', 'fills', 'door', 'opening')]
    assert value['boundary_entity_ids'] == ['opening']
    assert value['has_more'] is True
    expanded = both(raw, {'element_id': 'e00002', 'max_hops': 2})
    assert {e['entity_id']: e['hop_distance'] for e in expanded['entities']} == {'wall': 2, 'door': 0, 'opening': 1}
    assert expanded['has_more'] is False
    assert expanded['boundary_entity_ids'] == []
    assert expanded['relations'] == json.loads(raw)['relations'][:2]
    assert expanded['ontology_bound'] is expanded['alignment_verified'] is expanded['real_release_ready'] is False
    assert both(raw, {'element_id': 'e00002', 'max_hops': 2}) == expanded


def test_relation_filter_and_isolated_entity(structure_source):
    raw = snapshot(structure_source)
    value = both(raw, {'element_id': 'e00002', 'max_hops': 4, 'relation_kinds': ['fills']})
    assert len(value['entities']) == 2
    assert value['has_more'] is False
    isolated = both(raw, {'element_id': 'e00000'})
    assert len(isolated['entities']) == 1
    assert isolated['relations'] == isolated['boundary_entity_ids'] == []
    assert isolated['has_more'] is False


def test_all_relation_directions_are_preserved_without_inferred_containment(structure_source):
    doc = json.loads(snapshot(structure_source))
    doc['entities'].extend([
        doc['entities'][0] | {'entity_id': 'level', 'element_id': 'e00006', 'ifc_type': 'IfcBuildingStorey', 'source_role': 'level'},
        doc['entities'][0] | {'entity_id': 'space', 'element_id': 'e00007', 'ifc_type': 'IfcSpace', 'source_role': 'space'},
    ])
    doc['relations'].extend([edge('contained', 'contained_in', 'wall', 'level'),
                             edge('part', 'aggregates', 'building', 'level'),
                             edge('boundary', 'space_boundary', 'space', 'wall')])
    raw = canonical(doc)
    value = both(raw, {'element_id': 'e00001', 'max_hops': 4})
    assert value['relations'] == [r for r in doc['relations'] if r['kind'] != 'aggregates' or r['source_id'] == 'building']
    assert not any(r['source_id'] == 'door' and r['target_id'] == 'level' for r in value['relations'])
    flight = both(raw, {'element_id': 'e00005'})
    assert flight['relations'] == [edge('rel-2', 'aggregates', 'stair', 'flight')]
    assert 'confirmed_connections' not in value


def test_cycles_and_multiple_source_parents_remain_explicit(structure_source):
    doc = json.loads(snapshot(structure_source))
    doc['relations'].extend([edge('cycle', 'contained_in', 'wall', 'door'),
                             edge('parent-a', 'contained_in', 'door', 'building'),
                             edge('parent-b', 'contained_in', 'door', 'stair')])
    value = both(canonical(doc), {'element_id': 'e00002', 'max_hops': 4})
    assert len(value['entities']) == len(doc['entities'])
    assert value['has_more'] is False
    assert value['relations'] == doc['relations']


def test_induced_edges_at_frontier_and_source_order_are_preserved(structure_source):
    doc = json.loads(snapshot(structure_source))
    doc['relations'].append(edge('shortcut', 'contained_in', 'door', 'wall'))
    doc['relations'].reverse()
    doc['entities'].reverse()
    value = both(canonical(doc), {'element_id': 'e00002'})
    assert {e['entity_id']: e['hop_distance'] for e in value['entities']} == {'door': 0, 'wall': 1, 'opening': 1}
    assert value['has_more'] is False
    assert [e['entity_id'] for e in value['entities']] == ['opening', 'door', 'wall']
    assert value['relations'] == [r for r in doc['relations'] if r['kind'] != 'aggregates']


@pytest.mark.parametrize('query', [
    {}, {'element_id': 'missing'}, {'element_id': 'e00002', 'max_hops': 0},
    {'element_id': 'e00002', 'max_hops': 5}, {'element_id': 'e00002', 'max_hops': True},
    {'element_id': 'e00002', 'max_hops': '2'}, {'element_id': 'e00002', 'relation_kinds': []},
    {'element_id': 'e00002', 'relation_kinds': ['fills', 'fills']},
    {'element_id': 'e00002', 'relation_kinds': ['connects_spaces']},
    {'element_id': 'e00002', 'relation_kinds': None}, {'element_id': 'e00002', 'path': '../private'},
])
def test_invalid_queries_rejected_by_both(structure_source, query):
    raw = snapshot(structure_source)
    expected, source = sha(raw), json.loads(raw)['source']
    with pytest.raises(ValueError):
        query_declaration_context(raw, expected_sha256=expected, expected_source=source, query=query)
    assert node_context(raw, source, query).returncode != 0


@pytest.mark.parametrize('failure', ['element', 'source', 'digest', 'damage', 'dangling', 'promote', 'duplicate_json'])
def test_unknown_element_or_invalid_snapshot_never_becomes_empty_context(structure_source, failure):
    raw = snapshot(structure_source)
    expected, source = sha(raw), json.loads(raw)['source']
    query = {'element_id': 'e00002'}
    if failure == 'element':
        query['element_id'] = 'e99999'
    elif failure == 'source':
        source['space_id'] = 'space-' + '2' * 16
    elif failure == 'digest':
        expected = '0' * 64
    elif failure == 'damage':
        raw += b'!'
    elif failure == 'duplicate_json':
        raw = b'{"assessment":"unverified",' + raw[1:]
        expected = sha(raw)
    else:
        doc = json.loads(raw)
        if failure == 'dangling':
            doc['relations'][0]['target_id'] = 'missing'
        else:
            doc['real_release_ready'] = True
        raw = canonical(doc)
        expected = sha(raw)
    with pytest.raises(ValueError):
        query_declaration_context(raw, expected_sha256=expected, expected_source=source, query=query)
    assert node_context(raw, source, query, expected).returncode != 0


def test_entity_budget_rejects_without_partial_result(structure_source):
    doc = json.loads(snapshot(structure_source))
    for i in range(512):
        identity = f'extra-{i}'
        doc['entities'].append(doc['entities'][0] | {'entity_id': identity, 'element_id': f'e{i + 6:05}'})
        doc['relations'].append(edge(f'extra-rel-{i}', 'aggregates', 'door', identity))
    raw = canonical(doc)
    expected, source = sha(raw), doc['source']
    query = {'element_id': 'e00002'}
    with pytest.raises(ValueError, match='entity_budget'):
        query_declaration_context(raw, expected_sha256=expected, expected_source=source, query=query)
    node = node_context(raw, source, query)
    assert node.returncode != 0
    assert 'entity_budget' in node.stderr


def test_relation_budget_rejects_without_partial_result(structure_source):
    doc = json.loads(snapshot(structure_source))
    doc['relations'] = [edge(f'multiple-{i}', 'fills', 'door', 'opening') for i in range(2049)]
    raw = canonical(doc)
    expected, source = sha(raw), doc['source']
    query = {'element_id': 'e00002'}
    with pytest.raises(ValueError, match='relation_budget'):
        query_declaration_context(raw, expected_sha256=expected, expected_source=source, query=query)
    node = node_context(raw, source, query)
    assert node.returncode != 0
    assert 'relation_budget' in node.stderr


def test_schema_matches_runtime():
    path = Path('contracts/schemas/ifc-declaration-context-request-v0.1.schema.json')
    assert json.loads(path.read_bytes()) == DeclarationContextQuery.model_json_schema()


def test_node_host_arguments_are_not_satisfied_by_sparse_arrays_or_prototypes():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    uri = Path('examples/scene-graph/consumers/query-ifc-context.mjs').resolve().as_uri()
    script = ('import {queryDeclarationContext} from ' + json.dumps(uri) + ';'
              "const inputs=[[{element_id:'e00002',relation_kinds:new Array(1)},'context_relation_kinds'],"
              "[Object.create({element_id:'e00002'}),'context_element_id']];"
              "for(const [query,expected] of inputs){try{queryDeclarationContext(Buffer.alloc(0),{},query);"
              "throw new Error('accepted_invalid_query');}catch(e){if(e.message!==expected){throw e;}}}")
    subprocess.run([node, '--input-type=module', '-e', script], check=True, timeout=30, shell=False)
