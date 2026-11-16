"""Fit a local BIM-to-cloud alignment candidate from explicit correspondences."""
from typing import Annotated, Literal

import numpy as np
from pydantic import Field

from packages.construction.rgbd_tracking import rigid_fit, transform
from packages.spatial.scene_graph import Fixed, Identity
from packages.spatial.scene_identity import Digest, content_digest

Coordinate = Annotated[float, Field(ge=-10_000_000, le=10_000_000)]
Point = Annotated[list[Coordinate], Field(min_length=3, max_length=3)]


class FramePin(Fixed):
    frame_id: Identity
    artifact_sha256: Digest
    unit: Literal['m']


class Pair(Fixed):
    id: Identity
    evidence_ref: Identity
    purpose: Literal['fit', 'check']
    ifc_m: Point
    cloud_m: Point


class AlignmentInput(Fixed):
    profile: Literal['cospace.ifc-alignment-input/0.1']
    ifc: FramePin
    cloud: FramePin
    max_check_error_m: Annotated[float, Field(gt=0, le=10)]
    pairs: Annotated[list[Pair], Field(min_length=6, max_length=256)]


def _groups(pairs):
    # Exact duplicates cannot masquerade as additional or held-out controls.
    keys = ([p.id for p in pairs], [p.evidence_ref for p in pairs],
            [tuple(p.ifc_m) for p in pairs], [tuple(p.cloud_m) for p in pairs])
    if any(len(set(values)) != len(values) for values in keys):
        raise ValueError('alignment_duplicate_control')
    return [_coordinates([p for p in pairs if p.purpose == purpose]) for purpose in ('fit', 'check')]


def _coordinates(pairs):
    if len(pairs) < 3:
        raise ValueError('alignment_requires_three_points_per_group')
    source, target = (np.array([getattr(p, field) for p in pairs], dtype=np.float64)
                      for field in ('ifc_m', 'cloud_m'))
    for points in (source, target):
        singular = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
        if singular[1] <= max(1e-6, singular[0] * 1e-4):
            raise ValueError('alignment_degenerate_control_geometry')
    return source, target


def _residuals(pair, matrix):
    source, target = pair
    errors = np.linalg.norm(transform(source, matrix) - target, axis=1)
    return {'count': len(errors), 'rmse_m': float(np.sqrt(np.mean(errors**2))),
            'max_m': float(errors.max())}


def fit_ifc_alignment(document, *, expected_ifc, expected_cloud):
    """Compare against pinned frame references; no automatic verification or adoption."""
    request = AlignmentInput.model_validate(document)
    if request.ifc.model_dump() != expected_ifc or request.cloud.model_dump() != expected_cloud:
        raise ValueError('alignment_source_binding')
    if request.ifc.frame_id == request.cloud.frame_id:
        raise ValueError('alignment_requires_distinct_frames')
    fit, check = _groups(request.pairs)
    matrix = rigid_fit(*fit)
    fit_metrics = _residuals(fit, matrix)
    check_metrics = _residuals(check, matrix)
    meets_limit = check_metrics['max_m'] <= request.max_check_error_m
    return {
        'profile': 'cospace.ifc-alignment-candidate/0.1',
        'input_sha256': content_digest(request.model_dump()),
        'ifc': request.ifc.model_dump(), 'cloud': request.cloud.model_dump(),
        'transform_direction': 'ifc_to_cloud', 'matrix_ifc_to_cloud': matrix.tolist(),
        'fit': fit_metrics, 'check': check_metrics, 'max_check_error_m': request.max_check_error_m,
        'status': 'review_required' if meets_limit else 'check_limit_exceeded',
        'alignment_verified': False, 'control_evidence_verified': False, 'real_release_ready': False,
    }
