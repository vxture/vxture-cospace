"""Measure draft endpoints against pinned IFC meshes, without confirming connections."""
import argparse
import json
from pathlib import Path

import numpy as np

from experiments.scripts.ifc_spatial_annotation import validate_annotations
from experiments.scripts.ifc_structure_review import structure_review
from packages.data.ifc_workspace import load_mesh, read_json, sha
from packages.spatial.scene_identity import content_digest

MAX_ENDPOINTS = 256
MAX_TRIANGLE_EVALUATIONS = 10_000_000
CHUNK_SIZE = 8192


def nearest_surface(point, vertices, faces):
    """Unsigned Euclidean distance; ties use the first source triangle, not a unique interface."""
    point = np.asarray(point, dtype=float)
    best = None
    for start in range(0, len(faces), CHUNK_SIZE):
        a, b, c = np.moveaxis(vertices[faces[start:start + CHUNK_SIZE]], 1, 0)
        nearest = a.copy()
        distances = np.einsum('ij,ij->i', point - nearest, point - nearest)
        for u, v in ((a, b), (b, c), (c, a)):
            edge = v - u
            length2 = np.einsum('ij,ij->i', edge, edge)
            fraction = np.divide(np.einsum('ij,ij->i', point - u, edge), length2,
                                 out=np.zeros_like(length2), where=length2 > 0)
            candidate = u + np.clip(fraction, 0, 1)[:, None] * edge
            delta = point - candidate
            d2 = np.einsum('ij,ij->i', delta, delta)
            take = d2 < distances
            nearest[take], distances[take] = candidate[take], d2[take]
        normal = np.cross(b - a, c - a)
        norm2 = np.einsum('ij,ij->i', normal, normal)
        offset = np.divide(np.einsum('ij,ij->i', point - a, normal), norm2,
                           out=np.zeros_like(norm2), where=norm2 > 0)
        projection = point - offset[:, None] * normal
        inside = norm2 > 0
        for u, v in ((a, b), (b, c), (c, a)):
            inside &= np.einsum('ij,ij->i', np.cross(v - u, projection - u), normal) >= 0
        delta = point - projection
        d2 = np.einsum('ij,ij->i', delta, delta)
        take = inside & (d2 < distances)
        nearest[take], distances[take] = projection[take], d2[take]
        index = int(np.argmin(distances))
        if best is None or distances[index] < best[0]:
            best = (float(distances[index]), start + index, nearest[index].tolist())
    if best is None:
        raise ValueError('annotation_geometry_empty_mesh')
    return dict(distance_m=float(np.sqrt(best[0])), triangle_index=best[1], closest_point_xyz_m=best[2])


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
