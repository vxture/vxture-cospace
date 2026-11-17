"""Measure draft endpoints against pinned IFC meshes, without confirming connections."""
import argparse
import json
from pathlib import Path

from packages.spatial.ifc_annotations import validate_annotations
from packages.construction.ifc_structure_review import structure_review
from packages.data.ifc_workspace import load_mesh, read_json, sha
from packages.spatial.scene_identity import content_digest

MAX_ENDPOINTS = 256
MAX_TRIANGLE_EVALUATIONS = 10_000_000
CHUNK_SIZE = 8192


def nearest_surface(point, vertices, faces):
    from packages.spatial.mesh_distance import nearest_surface as measure
    return measure(point, vertices, faces, chunk_size=CHUNK_SIZE)


def _task_endpoints(root, task, endpoints, products):
    results = [dict(source_entity_id=task['source_entity_id'], role=end['role'], area_id=end['area_id'],
                    point_xyz_m=end['point_xyz_m'], targets=[], unavailable_geometry_ids=[])
               for end in endpoints]
    for target in [task['source'], *task['related_geometry']]:
        identity = target['global_id']
        if target['geometry_status'] != 'extracted':
            for result in results:
                result['unavailable_geometry_ids'].append(identity)
            continue
        vertices, faces = load_mesh(root, products[identity])
        for result in results:
            result['targets'].append(dict(
                source_entity_id=identity, ifc_type=target['ifc_type'], mesh_sha256=target['mesh']['sha256'],
                **nearest_surface(result['point_xyz_m'], vertices, faces)))
    return results


def endpoint_geometry(root, *, expected_catalog_sha256, document):
    review = structure_review(root, expected_catalog_sha256=expected_catalog_sha256)
    check = validate_annotations(document, review)
    connections = {row['source_entity_id']: row for row in document['connections']}
    count = sum(len(row['endpoints']) for row in connections.values())
    if count > MAX_ENDPOINTS:
        raise ValueError('annotation_geometry_endpoint_budget')
    raw, catalog = read_json(root / 'ifc.json', 8 * 1024 * 1024)
    if sha(raw) != expected_catalog_sha256:
        raise ValueError('annotation_geometry_catalog_changed')
    products = {row['global_id']: row for row in catalog['products']}
    plans = [(task, connections[task['source_entity_id']]['endpoints']) for task in review['tasks']
             if connections[task['source_entity_id']]['endpoints']]
    evaluations = sum(len(endpoints) * target['mesh_triangles'] for task, endpoints in plans
                      for target in [task['source'], *task['related_geometry']]
                      if target['geometry_status'] == 'extracted')
    if evaluations > MAX_TRIANGLE_EVALUATIONS:
        raise ValueError('annotation_geometry_triangle_budget')
    rows = [row for task, endpoints in plans for row in _task_endpoints(root, task, endpoints, products)]
    return dict(profile='cospace.ifc-endpoint-geometry/0.1',
                source_catalog_sha256=expected_catalog_sha256, source_review_sha256=content_digest(review),
                worksheet_sha256=check['worksheet_sha256'], frame_id=review['frame_id'], unit='m',
                method='unsigned_point_to_triangle_surface', tie_policy='lowest_source_triangle_index',
                triangle_evaluations=evaluations, endpoints=rows,
                pending_annotation_ids=check['pending_annotation_ids'], assessment='unverified',
                confirmed_connections=[], alignment_verified=False, real_release_ready=False,
                limitations=['ifc_design_geometry_only', 'nearest_within_each_declared_target_only',
                             'distance_not_interface_or_side_confirmation', 'no_distance_acceptance_threshold',
                             'no_signed_inside_outside_or_collision_test', 'no_field_or_evidence_content_verification',
                             'no_ontology_binding', 'no_navigation_or_traversability'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--worksheet', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _, document = read_json(args.worksheet, 8 * 1024 * 1024)
    result = endpoint_geometry(args.ifc_root, expected_catalog_sha256=args.ifc_sha256, document=document)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
