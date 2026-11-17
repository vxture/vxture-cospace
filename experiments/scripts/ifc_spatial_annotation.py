"""Seed and validate offline spatial annotations against a pinned IFC review."""
import argparse
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from experiments.scripts.ifc_structure_review import structure_review
from packages.data.ifc_workspace import read_json
from packages.spatial.scene_graph import Fixed, Identity, Vector
from packages.spatial.scene_identity import Digest, content_digest

PROFILE = 'cospace.ifc-spatial-annotation/0.1'
SourceId = Annotated[str, Field(min_length=1, max_length=255)]
Scalar = Annotated[float, Field(ge=-1_000_000, le=1_000_000)]
XY = Annotated[list[Scalar], Field(min_length=2, max_length=2)]


class Evidence(Fixed):
    id: Identity
    sha256: Digest


class Area(Fixed):
    id: Identity
    name: str = Field(min_length=1, max_length=160)
    level_id: SourceId
    footprint_xy_m: Annotated[list[XY], Field(min_length=3, max_length=128)]
    z_range_m: Annotated[list[Scalar], Field(min_length=2, max_length=2)]
    evidence_ids: Annotated[list[Identity], Field(min_length=1, max_length=16)]


class Endpoint(Fixed):
    role: Literal['side_a', 'side_b', 'lower', 'upper']
    area_id: Identity
    point_xyz_m: Vector


class ConnectionAnnotation(Fixed):
    source_entity_id: SourceId
    endpoints: Annotated[list[Endpoint], Field(min_length=0, max_length=2)]
    evidence_ids: Annotated[list[Identity], Field(max_length=16)]


class Worksheet(Fixed):
    profile: Literal['cospace.ifc-spatial-annotation/0.1']
    source_review_sha256: Digest
    frame_id: Identity
    unit: Literal['m']
    assessment: Literal['unverified']
    evidence: Annotated[list[Evidence], Field(max_length=1024)]
    areas: Annotated[list[Area], Field(max_length=512)]
    connections: Annotated[list[ConnectionAnnotation], Field(max_length=10_000)]


def seed(review):
    return dict(profile=PROFILE, source_review_sha256=content_digest(review),
                frame_id=review['frame_id'], unit='m', assessment='unverified', evidence=[], areas=[],
                connections=[dict(source_entity_id=task['source_entity_id'], endpoints=[], evidence_ids=[])
                             for task in review['tasks']])


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on(a, b, p):
    return _cross(a, b, p) == 0 and all(min(x, y) <= z <= max(x, y) for x, y, z in zip(a, b, p))


def _intersect(a, b, c, d):
    u, v, w, x = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    return ((u * v < 0 and w * x < 0) or _on(a, b, c) or _on(a, b, d)
            or _on(c, d, a) or _on(c, d, b))


def _edges(poly):
    return list(zip(poly, poly[1:] + poly[:1]))


def _validate_area(area):
    poly = area.footprint_xy_m
    edges = _edges(poly)
    n = len(poly)
    if (area.z_range_m[0] >= area.z_range_m[1] or len(set(map(tuple, poly))) != n
            or abs(sum(_cross(poly[0], a, b) for a, b in edges)) <= 1e-10
            or any(_on(a, b, poly[(i + 2) % n]) or _on(b, poly[(i + 2) % n], a)
                   for i, (a, b) in enumerate(edges))
            or any(_intersect(a, b, c, d) for i, (a, b) in enumerate(edges)
                   for j, (c, d) in enumerate(edges) if i + 1 < j and (i, j) != (0, n - 1))):
        raise ValueError('annotation_invalid_area_geometry')


def _contains(area, point):
    x, y, z = point
    if not area.z_range_m[0] <= z <= area.z_range_m[1]:
        return False
    inside = False
    for a, b in _edges(area.footprint_xy_m):
        if _on(a, b, (x, y)):
            return True
        if (a[1] > y) != (b[1] > y) and x < a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]):
            inside = not inside
    return inside


def _index(rows, key):
    result = {getattr(row, key): row for row in rows}
    if len(result) != len(rows):
        raise ValueError('annotation_duplicate_id')
    return result


def _evidence(ids, known):
    if len(set(ids)) != len(ids) or set(ids) - known.keys():
        raise ValueError('annotation_evidence_reference')


def _validate_connection(connection, ifc_type, areas, evidence):
    _evidence(connection.evidence_ids, evidence)
    if not connection.endpoints:
        return False
    endpoints = _index(connection.endpoints, 'role')
    required = {'side_a', 'side_b'} if ifc_type == 'IfcDoor' else {'lower', 'upper'}
    if endpoints.keys() - required or not connection.evidence_ids:
        raise ValueError('annotation_endpoint_roles_or_evidence')
    for end in endpoints.values():
        if end.area_id not in areas or not _contains(areas[end.area_id], end.point_xyz_m):
            raise ValueError('annotation_endpoint_outside_area')
    if len(endpoints) < 2:
        return False
    first, second = connection.endpoints
    if first.area_id == second.area_id or first.point_xyz_m == second.point_xyz_m:
        raise ValueError('annotation_duplicate_endpoint')
    if ifc_type == 'IfcStair' and endpoints['lower'].point_xyz_m[2] >= endpoints['upper'].point_xyz_m[2]:
        raise ValueError('annotation_stair_endpoint_order')
    return True


def validate_annotations(document, review, *, evidence_root=None):
    worksheet = Worksheet.model_validate(document)
    if worksheet.source_review_sha256 != content_digest(review) or worksheet.frame_id != review['frame_id']:
        raise ValueError('annotation_source_binding')
    evidence = _index(worksheet.evidence, 'id')
    areas = _index(worksheet.areas, 'id')
    levels = {row['global_id'] for row in review['declared_levels']}
    for area in areas.values():
        _evidence(area.evidence_ids, evidence)
        if area.level_id not in levels:
            raise ValueError('annotation_level_reference')
        _validate_area(area)
    tasks = {task['source_entity_id']: task['source']['ifc_type'] for task in review['tasks']}
    connections = _index(worksheet.connections, 'source_entity_id')
    if connections.keys() != tasks.keys():
        raise ValueError('annotation_task_coverage')
    complete = [key for key, row in connections.items() if _validate_connection(row, tasks[key], areas, evidence)]
    completed = set(complete)
    result = dict(profile='cospace.ifc-spatial-annotation-check/0.1',
                worksheet_sha256=content_digest(document), source_review_sha256=worksheet.source_review_sha256,
                area_count=len(areas), complete_annotation_ids=complete,
                pending_annotation_ids=[key for key in tasks if key not in completed],
                assessment='unverified', evidence_content_verified=False,
                confirmed_connections=[], alignment_verified=False, real_release_ready=False)
    if evidence_root is not None:
        from packages.data.evidence_content import check_evidence_content
        result['evidence_receipt'] = check_evidence_content(
            evidence_root, [row.model_dump() for row in worksheet.evidence], document_sha256=content_digest(document))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--worksheet', type=Path, help='Check this worksheet instead of seeding one')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, help='Check worksheet evidence bytes; requires --worksheet')
    args = parser.parse_args()
    if args.evidence_root is not None and args.worksheet is None:
        parser.error('--evidence-root requires --worksheet')
    review = structure_review(args.ifc_root, expected_catalog_sha256=args.ifc_sha256)
    if args.worksheet:
        _, document = read_json(args.worksheet, 8 * 1024 * 1024)
        result = validate_annotations(document, review, evidence_root=args.evidence_root)
    else:
        result = seed(review)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
