"""Fit an unverified alignment candidate from source-checked, reviewed controls."""
import argparse
import json
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import Field

from experiments.scripts.ifc_control_review import _read_sources
from packages.construction.ifc_alignment import FramePin, Point, fit_ifc_alignment
from packages.data.ifc_workspace import load_mesh, read_json
from packages.spatial.scene_graph import Fixed, Identity
from packages.spatial.scene_identity import Digest, content_digest


class IfcReference(Fixed):
    global_id: str = Field(min_length=1, max_length=255)
    vertex: int = Field(ge=0)


class CloudReference(Fixed):
    ply_point_index: int = Field(ge=0)


class IfcPoint(Fixed):
    xyz: Point
    reference: IfcReference


class CloudPoint(Fixed):
    xyz: Point
    reference: CloudReference


class Control(Fixed):
    id: Identity
    purpose: Literal['fit', 'check']
    description: str = Field(min_length=1, max_length=240)
    ifc: IfcPoint
    cloud: CloudPoint
    verified: Literal[False]


class Worksheet(Fixed):
    profile: Literal['cospace.ifc-control-review/0.1']
    status: Literal['not_aligned']
    ifc: FramePin
    cloud: FramePin
    cloud_unit_verified: Literal[False]
    alignment_verified: Literal[False]
    pairs: Annotated[list[Control], Field(min_length=6, max_length=256)]


class Evidence(Fixed):
    id: Identity
    sha256: Digest


class ControlEvidence(Fixed):
    control_id: Identity
    evidence: Evidence


class Review(Fixed):
    profile: Literal['cospace.ifc-control-review-record/0.1']
    worksheet_sha256: Digest
    reviewer: Identity
    unit_evidence: Evidence
    controls: Annotated[list[ControlEvidence], Field(min_length=6, max_length=256)]


def reviewed_candidate(document, review, ifc_root, cloud_root, *,
                       expected_ifc_sha256, expected_cloud_sha256, max_check_error_m):
    """Evidence references are reviewer declarations, never automatic verification."""
    worksheet = Worksheet.model_validate(document)
    record = Review.model_validate(review)
    if record.worksheet_sha256 != content_digest(document):
        raise ValueError('review_worksheet_changed')
    catalog, facts, points = _read_sources(
        ifc_root, cloud_root, expected_ifc_sha256=expected_ifc_sha256,
        expected_cloud_sha256=expected_cloud_sha256)
    expected_ifc = dict(frame_id=catalog['frame_id'], unit='m', artifact_sha256=expected_ifc_sha256)
    expected_cloud = dict(frame_id=facts['frame_id'], unit='m', artifact_sha256=expected_cloud_sha256)
    if worksheet.ifc.model_dump() != expected_ifc or worksheet.cloud.model_dump() != expected_cloud:
        raise ValueError('review_source_binding')
    evidence = {row.control_id: row.evidence for row in record.controls}
    if (len(evidence) != len(record.controls)
            or set(evidence) != {p.id for p in worksheet.pairs}):
        raise ValueError('review_control_coverage')
    products = {p['global_id']: p for p in catalog['products']}
    meshes, pairs = {}, []
    for pair in worksheet.pairs:
        ref = pair.ifc.reference
        product = products.get(ref.global_id)
        if product is None or product['geometry_status'] != 'extracted':
            raise ValueError('review_ifc_reference')
        if ref.global_id not in meshes:
            meshes[ref.global_id] = load_mesh(ifc_root, product)[0]
        vertices = meshes[ref.global_id]
        index = pair.cloud.reference.ply_point_index
        if ref.vertex >= len(vertices) or index >= len(points):
            raise ValueError('review_point_index')
        if (not np.array_equal(vertices[ref.vertex], pair.ifc.xyz)
                or not np.array_equal(points[index], pair.cloud.xyz)):
            raise ValueError('review_point_coordinates_changed')
        pairs.append(dict(id=pair.id, purpose=pair.purpose, ifc_m=pair.ifc.xyz,
                          cloud_m=pair.cloud.xyz, evidence_ref=evidence[pair.id].id))
    result = fit_ifc_alignment(
        dict(profile='cospace.ifc-alignment-input/0.1', ifc=expected_ifc, cloud=expected_cloud,
             max_check_error_m=max_check_error_m, pairs=pairs),
        expected_ifc=expected_ifc, expected_cloud=expected_cloud)
    return result | {'review': record.model_dump(), 'review_sha256': content_digest(review),
                     'evidence_content_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worksheet', 'review', 'ifc-root', 'cloud-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--cloud-sha256', required=True)
    parser.add_argument('--max-check-error-m', type=float, required=True)
    args = parser.parse_args()
    _, document = read_json(args.worksheet, 1024 * 1024)
    _, review = read_json(args.review, 1024 * 1024)
    result = reviewed_candidate(
        document, review, args.ifc_root, args.cloud_root,
        expected_ifc_sha256=args.ifc_sha256, expected_cloud_sha256=args.cloud_sha256,
        max_check_error_m=args.max_check_error_m)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
