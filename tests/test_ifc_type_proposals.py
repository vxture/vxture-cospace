from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from packages.data.ifc_inspection import digest
from packages.ontology.ifc_mapping import propose_structure_types
from packages.ontology.preview_versions import PreviewOntologies
from packages.ontology.workspace_authoring import WorkspaceOntologies
from packages.service.ifc_type_proposals import TypeProposalRequest, type_proposals
from packages.views.agent.ifc_structure_exchange import build_structure_snapshot
from test_ifc_structure_review import structure_source
from test_ifc_structure_http import declare
from test_ifc_workspace import ifc_secured
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_workspace_ontology_authoring import principal

ROUTE = '/api/scene-ifc/type-proposals'


def ontology():
    value = json.loads(Path('configs/ontology/indoor-equipment-v0.3.json').read_bytes())
    value.update(ontology_id='structure-test', version='1.0.0', title='Test structure vocabulary')
    value['types'] = {'door': value['types']['cabinet'], 'wall': value['types']['cabinet']}
    value['profile'] = 'cospace.preview-ontology/0.1'
    value.pop('relations', None)
    return json.dumps(value).encode()


def mapping(raw, source_type='IfcDoor', target='door'):
    doc = json.loads(raw)
    return {'profile': 'cospace.ifc-ontology-mapping/0.1',
            'ontology_ref': {'ontology_id': doc['ontology_id'], 'version': doc['version'],
                             'sha256': hashlib.sha256(raw).hexdigest()},
            'rules': [{'ifc_type': source_type, 'target_type_id': target}]}


def proposals(env, document=None):
    root, catalog = env
    structure = build_structure_snapshot('space-' + '1' * 16, digest(root / 'ifc.json'), catalog)
    raw = ontology()
    return propose_structure_types(structure, expected_structure_sha256=digest_bytes(structure),
                                   expected_source=json.loads(structure)['source'],
                                   ontology_raw=raw, mapping_document=document or mapping(raw))


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def test_source_ontology_and_mapping_remain_separate(structure_source):
    root, _ = structure_source
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    value = proposals(structure_source)
    assert value == proposals(structure_source)
    assert value['proposed_count'] == 1
    assert value['unmapped_count'] == 5
    door = next(e for e in value['entities'] if e['source_entity_id'] == 'door')
    assert door['target_type_id'] == 'door'
    assert door['element_id'] == 'e00002'
    for field in ('saved', 'instance_validated', 'relationships_mapped', 'ontology_bound',
                  'alignment_verified', 'real_release_ready'):
        assert value[field] is False
    other = proposals(structure_source, mapping(ontology(), target='wall'))
    assert other['mapping_sha256'] != value['mapping_sha256']
    assert other['structure_sha256'] == value['structure_sha256']
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'pin', 'version', 'extra'])
def test_invalid_mapping_is_rejected(structure_source, change):
    doc = mapping(ontology())
    if change == 'duplicate':
        doc['rules'].append(doc['rules'][0])
    elif change == 'unknown':
        doc['rules'][0]['target_type_id'] = 'missing'
    elif change == 'pin':
        doc['ontology_ref']['sha256'] = '0' * 64
    elif change == 'version':
        doc['ontology_ref']['version'] = '2.0.0'
    else:
        doc['confirmed'] = True
    with pytest.raises(ValueError):
        proposals(structure_source, doc)


def test_authorized_read_only_http_and_source_revalidation(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    _, client, _, _, jobs, _, spaces, *_ = env
    pin = declare(root, config)
    store = PreviewOntologies(jobs.root.parent / 'preview-ontologies')
    store.register_bytes(ontology())
    body = {'space_id': spaces[0]['id'], 'catalog_sha256': pin,
            'mapping': mapping(ontology(), 'IfcWall', 'wall')}
    assert client.post(ROUTE, json=body).status_code == 401
    headers, _ = sign_in(env, 'usr_local_test')
    original = access.scene_ifc.catalog
    def denied(*args):
        pytest.fail('unauthorized proposal reached catalog')
    monkeypatch.setattr(access.scene_ifc, 'catalog', denied)
    assert client.post(ROUTE, json=body, headers=headers).status_code == 403
    monkeypatch.setattr(access.scene_ifc, 'catalog', original)
    headers, _ = sign_in(env, 'usr_engineer')
    def no_mesh(*args):
        pytest.fail('type proposal loaded geometry')
    monkeypatch.setattr('packages.data.ifc_workspace.load_mesh', no_mesh)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    result = client.post(ROUTE, json=body, headers=headers)
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    assert result.json()['proposed_count'] == 1
    assert result.json()['saved'] is False
    assert client.post(ROUTE, json=body, headers=headers).json() == result.json()
    assert str(root) not in result.text
    for changes, status in [({'catalog_sha256': '0' * 64}, 409),
                            ({'catalog_sha256': 'bad'}, 422), ({'saved': True}, 422),
                            ({'space_id': spaces[1]['id']}, 403)]:
        assert client.post(ROUTE, json=body | changes, headers=headers).status_code == status
    assert client.post(ROUTE + '?root=private', json=body, headers=headers).status_code == 422
    assert client.get(ROUTE, params={'space_id': spaces[0]['id']}).status_code == 403
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before
    (root / 'source.ifc').write_bytes(b'changed')
    assert client.post(ROUTE, json=body, headers=headers).status_code == 409


def test_private_sealed_rules_cannot_cross_workspace(ifc_secured):
    env, access, root, config = ifc_secured
    pin = declare(root, config)
    store = WorkspaceOntologies(root / 'rules', principal())
    PreviewOntologies(store.private_root).register_bytes(ontology())
    query = TypeProposalRequest(space_id=env[6][0]['id'], catalog_sha256=pin,
                                mapping=mapping(ontology(), 'IfcWall', 'wall'))
    assert type_proposals(access.scene_ifc, store, query)['proposed_count'] == 1
    other = WorkspaceOntologies(store.root, replace(principal(), workspace_id='ws_other'))
    with pytest.raises(ValueError, match='not_found'):
        type_proposals(access.scene_ifc, other, query)
    path = store.path('structure-test', '1.0.0') / 'definition.json'
    path.write_bytes(b'changed')
    with pytest.raises(ValueError):
        type_proposals(access.scene_ifc, store, query)
