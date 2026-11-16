"""Validate pinned IFC source declarations independently of ontology and field adoption."""
from typing import Literal

from pydantic import Field

from packages.data.ifc_structure import MAX_RELATIONS
from packages.spatial.scene_graph import Fixed, Identity


class Entity(Fixed):
    entity_id: str = Field(min_length=1, max_length=255)
    ifc_type: str = Field(pattern='^Ifc[A-Za-z0-9]+$', max_length=110)
    role: Identity
    geometry_product_id: str = Field(min_length=1, max_length=255)


class Relation(Fixed):
    ifc_relation_id: str = Field(min_length=1, max_length=255)
    kind: Literal['aggregates', 'contained_in', 'opening_in', 'fills', 'space_boundary']
    source_id: str = Field(min_length=1, max_length=255)
    target_id: str = Field(min_length=1, max_length=255)


def validate_structure(catalog):
    source = catalog.get('structure', {})
    if (not isinstance(source, dict) or source.get('profile') != 'cospace.ifc-structure-candidate/0.1'
            or source.get('assessment') != 'unverified'
            or source.get('data_kind') != 'ifc_design_candidate'):
        raise ValueError('structure_review_source_required')
    entities, relations = source.get('entities'), source.get('relations')
    if not isinstance(entities, list) or len(entities) > 10_000:
        raise ValueError('structure_review_entity_budget')
    if not isinstance(relations, list) or len(relations) > MAX_RELATIONS:
        raise ValueError('structure_review_relation_budget')
    entities = [Entity.model_validate(row) for row in entities]
    relations = [Relation.model_validate(row).model_dump() for row in relations]
    ids = {row.entity_id for row in entities}
    products = {row['global_id']: row for row in catalog['products']}
    if len(ids) != len(entities) or any(
            row.geometry_product_id != row.entity_id
            or row.geometry_product_id not in products
            or products[row.geometry_product_id]['ifc_type'] != row.ifc_type for row in entities):
        raise ValueError('structure_review_entity_binding')
    keys = {tuple(row.values()) for row in relations}
    if len(keys) != len(relations) or any(
            row['source_id'] not in ids or row['target_id'] not in ids
            or row['source_id'] == row['target_id'] for row in relations):
        raise ValueError('structure_review_relation_binding')
    return entities, relations, products
