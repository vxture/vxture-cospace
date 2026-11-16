"""Prepare source-frame structural review tasks without inventing connections."""
import argparse
from collections import Counter
import json
from pathlib import Path
from packages.data.ifc_structure_read import validate_structure as _structure
from packages.data.ifc_workspace import load_mesh, read_json, sha, validate_catalog, validate_source


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
