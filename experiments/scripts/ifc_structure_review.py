"""Prepare source-frame structural review tasks without inventing connections."""
import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from packages.data.ifc_structure import MAX_RELATIONS
from packages.data.ifc_workspace import load_mesh, read_json, sha, validate_catalog, validate_source
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


def _structure(catalog):
    source = catalog.get('structure', {})
    if (source.get('profile') != 'cospace.ifc-structure-candidate/0.1'
            or source.get('assessment') != 'unverified'
            or source.get('data_kind') != 'ifc_design_candidate'):
        raise ValueError('structure_review_source_required')
    entities, relations = source['entities'], source['relations']
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


def structure_review(root, *, expected_catalog_sha256):
    raw, catalog = read_json(root / 'ifc.json', 8 * 1024 * 1024)
    if sha(raw) != expected_catalog_sha256:
        raise ValueError('structure_review_catalog_digest')
    validate_catalog(catalog)
    validate_source(root, catalog)
    entities, relations, products = _structure(catalog)
    geometry = {}

    def product_summary(identity):
        product = products[identity]
        if identity not in geometry:
            row = {key: product[key] for key in ('global_id', 'ifc_type', 'name', 'geometry_status')}
            if product['geometry_status'] == 'extracted':
                vertices, faces = load_mesh(root, product)
                row.update(mesh=product['mesh'], index_bounds_m=[vertices.min(0).tolist(), vertices.max(0).tolist()],
                           mesh_vertices=len(vertices), mesh_triangles=len(faces))
            geometry[identity] = row
        return geometry[identity]

    tasks = []
    for entity in entities:
        if entity.ifc_type not in ('IfcDoor', 'IfcStair'):
            continue
        identity = entity.entity_id
        direct = [row for row in relations if identity in (row['source_id'], row['target_id'])]
        openings = {row['target_id'] for row in direct if row['kind'] == 'fills' and row['source_id'] == identity}
        children = {row['target_id'] for row in direct if row['kind'] == 'aggregates' and row['source_id'] == identity}
        opening_hosts = [row for row in relations if row['kind'] == 'opening_in' and row['source_id'] in openings]
        related = openings | children | {row['target_id'] for row in opening_hosts}
        tasks.append(dict(
            source_entity_id=identity, source=product_summary(identity),
            source_relations=direct + opening_hosts,
            related_geometry=[product_summary(key) for key in sorted(related)],
            assessment='unverified',
            review=dict(status='pending', space_endpoints=[], evidence_refs=[],
                        required=['space_boundaries', 'opening_sides'] if entity.ifc_type == 'IfcDoor'
                        else ['space_boundaries', 'flight_and_landing_interfaces', 'endpoint_levels'])))
    counts = dict(sorted(Counter(row.role for row in entities).items()))
    return dict(profile='cospace.ifc-structure-review/0.1',
                source_catalog_sha256=expected_catalog_sha256, frame_id=catalog['frame_id'], unit='m',
                data_kind='ifc_design_candidate', declared_role_counts=counts,
                missing_declared_roles=[role for role in ('space', 'door', 'stair', 'distribution_board') if not counts.get(role)],
                declared_levels=[product_summary(row.entity_id) for row in entities if row.ifc_type == 'IfcBuildingStorey'],
                tasks=tasks, confirmed_connections=[], alignment_verified=False, real_release_ready=False,
                limitations=['source_declarations_not_field_facts', 'bounds_for_indexing_only',
                             'no_inferred_room_or_corridor', 'no_door_state_or_clear_width',
                             'no_navigation_or_traversability', 'no_ontology_binding'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = structure_review(args.ifc_root, expected_catalog_sha256=args.ifc_sha256)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
