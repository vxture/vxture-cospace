import json
from pathlib import Path

import pytest

from packages.ontology.ifc_mapping import propose_ifc_types
from packages.ontology.preview_versions import digest

DOOR_ID = '0I3GdQ0kvBE9R$mRpMZQPH'
BOARD_ID = '1' + 'B'*21

@pytest.fixture
def inputs():
    ontology = Path('configs/ontology/indoor-equipment-v0.3.json').read_bytes()
    entities = [{'entity_id': DOOR_ID, 'ifc_type': 'IfcDoor',
                 'role': 'door', 'geometry_product_id': DOOR_ID},
                {'entity_id': BOARD_ID, 'ifc_type': 'IfcElectricDistributionBoard',
                 'role': 'distribution_board', 'geometry_product_id': BOARD_ID}]
    catalog = {'structure': {'profile': 'cospace.ifc-structure-candidate/0.1',
                            'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
                            'entities': entities}}
    mapping = {'profile': 'cospace.ifc-ontology-mapping/0.1',
               'ontology_ref': {'ontology_id': 'indoor-equipment', 'version': '0.3.0',
                                'sha256': digest(ontology)},
               'rules': [{'ifc_type': 'IfcElectricDistributionBoard', 'target_type_id': 'cabinet'}]}
    return json.dumps(catalog).encode(), ontology, mapping


def run(inputs, expected=None):
    raw, ontology, mapping = inputs
    return propose_ifc_types(raw, expected_catalog_sha256=expected or digest(raw),
                             ontology_raw=ontology, mapping_document=mapping)


def test_preserves_unmapped_sources_and_does_not_promote_proposals(inputs):
    result = run(inputs)
    assert result['entities'] == [
        {'source_entity_id': DOOR_ID, 'ifc_type': 'IfcDoor', 'target_type_id': None, 'status': 'unmapped'},
        {'source_entity_id': BOARD_ID, 'ifc_type': 'IfcElectricDistributionBoard',
         'target_type_id': 'cabinet', 'status': 'proposed'},
    ]
    assert not result['instance_validated']
    assert not result['relationships_mapped']
    assert not result['real_release_ready']
    assert result['source_catalog_sha256'] == digest(inputs[0])
    assert result == run(inputs)


@pytest.mark.parametrize('field, replacement, error', [
    ('sha256', '0'*64, 'ontology_digest'),
    ('version', '0.4.0', 'ontology_identity'),
    ('ontology_id', 'another', 'ontology_identity'),
])
def test_ontology_pin(inputs, field, replacement, error):
    inputs[2]['ontology_ref'][field] = replacement
    with pytest.raises(ValueError, match=error):
        run(inputs)


def test_catalog_pin(inputs):
    with pytest.raises(ValueError, match='catalog_digest'):
        run(inputs, '0'*64)


def test_rule_changes_do_not_rewrite_ifc(inputs):
    first = run(inputs)
    inputs[2]['rules'][0]['target_type_id'] = 'control_cabinet'
    second = run(inputs)
    assert first['source_catalog_sha256'] == second['source_catalog_sha256']
    assert first['mapping_sha256'] != second['mapping_sha256']
    assert second['entities'][1]['target_type_id'] == 'control_cabinet'


@pytest.mark.parametrize('duplicate,error', [(False, 'unknown_target'), (True, 'duplicate_rule')])
def test_invalid_rules(inputs, duplicate, error):
    rules = inputs[2]['rules']
    if duplicate:
        rules.append(rules[0])
    else:
        rules[0]['target_type_id'] = 'not-in-ontology'
    with pytest.raises(ValueError, match=error):
        run(inputs)


@pytest.mark.parametrize('raw, error', [
    (b'{"structure":1,"structure":2}', 'duplicate_key'),
    (b'{"structure":null}', 'structure_required'),
])
def test_reject_ambiguous_or_non_candidate_input(inputs, raw, error):
    with pytest.raises(ValueError, match=error):
        run((raw, *inputs[1:]))
