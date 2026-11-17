"""Propose ontology type bindings without changing IFC facts or accepting instances."""
import json
from typing import Annotated, Literal

from pydantic import Field

from packages.ontology.preview_versions import definition, digest, MAX_BYTES
from packages.spatial.scene_graph import Fixed, Identity
from packages.spatial.scene_identity import Digest, content_digest

MAX_CATALOG_BYTES = 8 * 1024 * 1024
IfcClass = Annotated[str, Field(pattern=r'^Ifc[A-Za-z0-9]{1,100}$')]
IfcGlobalId = Annotated[str, Field(pattern=r'^[0-3][A-Za-z0-9_$]{21}$')]


class OntologyPin(Fixed):
    ontology_id: Identity
    version: Identity
    sha256: Digest


class Rule(Fixed):
    ifc_type: IfcClass
    target_type_id: Identity


class Mapping(Fixed):
    profile: Literal['cospace.ifc-ontology-mapping/0.1']
    ontology_ref: OntologyPin
    rules: Annotated[list[Rule], Field(min_length=1, max_length=100)]


class SourceEntity(Fixed):
    entity_id: IfcGlobalId
    ifc_type: IfcClass
    role: Identity
    geometry_product_id: IfcGlobalId


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('mapping_input_duplicate_key')
        result[key] = value
    return result


def _source_entities(raw, expected_sha256):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_CATALOG_BYTES:
        raise ValueError('ifc_mapping_catalog_budget')
    if digest(raw) != expected_sha256:
        raise ValueError('ifc_mapping_catalog_digest')
    catalog = json.loads(raw, object_pairs_hook=_unique_keys)
    structure = catalog.get('structure') if isinstance(catalog, dict) else None
    if (not isinstance(structure, dict) or structure.get('profile') != 'cospace.ifc-structure-candidate/0.1'
            or structure.get('data_kind') != 'ifc_design_candidate' or structure.get('assessment') != 'unverified'):
        raise ValueError('ifc_mapping_structure_required')
    entities = structure.get('entities')
    if not isinstance(entities, list) or len(entities) > 10_000:
        raise ValueError('ifc_mapping_entities_budget')
    result = [SourceEntity.model_validate(entity) for entity in entities]
    if len({entity.entity_id for entity in result}) != len(result):
        raise ValueError('ifc_mapping_duplicate_entity')
    return result


def _rules(mapping, ontology_raw):
    if not isinstance(ontology_raw, bytes) or not 1 <= len(ontology_raw) <= MAX_BYTES:
        raise ValueError('ifc_mapping_ontology_budget')
    if digest(ontology_raw) != mapping.ontology_ref.sha256:
        raise ValueError('ifc_mapping_ontology_digest')
    # Reject ambiguous JSON before reusing the existing versioned ontology validator.
    json.loads(ontology_raw, object_pairs_hook=_unique_keys)
    ontology = definition(ontology_raw)
    if (ontology['ontology_id'], ontology['version']) != (mapping.ontology_ref.ontology_id, mapping.ontology_ref.version):
        raise ValueError('ifc_mapping_ontology_identity')
    rules = {rule.ifc_type: rule.target_type_id for rule in mapping.rules}
    if len(rules) != len(mapping.rules):
        raise ValueError('ifc_mapping_duplicate_rule')
    if set(rules.values()) - ontology['types'].keys():
        raise ValueError('ifc_mapping_unknown_target')
    return rules


def propose_ifc_types(catalog_raw, *, expected_catalog_sha256, ontology_raw, mapping_document):
    """Map exact declared IFC types, not names, geometry roles or inherited IFC classes."""
    mapping = Mapping.model_validate(mapping_document)
    rules = _rules(mapping, ontology_raw)
    entities = _source_entities(catalog_raw, expected_catalog_sha256)
    rows = []
    for entity in entities:
        target = rules.get(entity.ifc_type)
        rows.append({'source_entity_id': entity.entity_id, 'ifc_type': entity.ifc_type,
                     'target_type_id': target, 'status': 'proposed' if target else 'unmapped'})
    return {'profile': 'cospace.ifc-ontology-proposals/0.1', 'source_catalog_sha256': expected_catalog_sha256,
            'ontology_ref': mapping.ontology_ref.model_dump(),
            'mapping_sha256': content_digest(mapping.model_dump()), 'entities': rows,
            'assessment': 'unverified', 'instance_validated': False, 'relationships_mapped': False,
            'real_release_ready': False}


def propose_structure_types(structure_raw, *, expected_structure_sha256, expected_source,
                            ontology_raw, mapping_document):
    """Independent type proposals for exchanged declarations; never mutate the source."""
    from packages.views.agent.ifc_structure_exchange import inspect_structure_snapshot
    mapping = Mapping.model_validate(mapping_document)
    rules = _rules(mapping, ontology_raw)
    snapshot = inspect_structure_snapshot(structure_raw, expected_sha256=expected_structure_sha256,
                                          expected_source=expected_source)
    rows = []
    for entity in snapshot.entities:
        target = rules.get(entity.ifc_type)
        rows.append({'source_entity_id': entity.entity_id, 'element_id': entity.element_id,
                     'ifc_type': entity.ifc_type, 'target_type_id': target,
                     'status': 'proposed' if target else 'unmapped'})
    return {'profile': 'cospace.ifc-structure-type-proposals/0.1',
            'source': snapshot.source.model_dump(), 'structure_sha256': expected_structure_sha256,
            'mapping': mapping.model_dump(),
            'ontology_ref': mapping.ontology_ref.model_dump(),
            'mapping_sha256': content_digest(mapping.model_dump()), 'entities': rows,
            'proposed_count': sum(row['status'] == 'proposed' for row in rows),
            'unmapped_count': sum(row['status'] == 'unmapped' for row in rows),
            'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
            'instance_validated': False, 'relationships_mapped': False, 'ontology_bound': False,
            'alignment_verified': False, 'saved': False, 'real_release_ready': False}
