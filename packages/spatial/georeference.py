"""Evaluate pinned metric registration parameters; never approve geographic use."""
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.spatial.scene_identity import content_digest

Text = Annotated[str, Field(min_length=1, max_length=160)]
Digest = Annotated[str, Field(pattern='^[a-f0-9]{64}$')]
Coordinate = Annotated[float, Field(ge=-10_000_000, le=10_000_000)]
Point = Annotated[list[Coordinate], Field(min_length=3, max_length=3)]
Row = Annotated[list[Coordinate], Field(min_length=4, max_length=4)]


class Fixed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class ModelFrame(Fixed):
    space_id: Text
    candidate_id: Text
    manifest_sha256: Digest
    model_sha256: Digest
    frame_id: Text
    unit: Literal['m']
    axes: Annotated[list[Text], Field(min_length=3, max_length=3)]
    handedness: Literal['right']
    bounds_m: Annotated[list[Point], Field(min_length=2, max_length=2)]

    @model_validator(mode='after')
    def coordinates(self):
        if len(set(self.axes)) != 3 or any(a >= b for a, b in zip(*self.bounds_m)):
            raise ValueError('registration_source_frame')
        return self


class TargetFrame(Fixed):
    frame_id: Text
    title: Text
    kind: Literal['engineering', 'projected']
    horizontal_reference: Text
    definition_ref: Text
    evidence_ref: Text
    unit: Literal['m']
    axes: Literal['east_north_up']
    vertical_reference: Text
    # A metric target does not itself supply a geographic projection adapter.
    geographic_adapter: Literal['not_connected']


class Control(Fixed):
    id: Text
    purpose: Literal['fit', 'check']
    source_m: Point
    target_m: Point
    evidence_ref: Text


class Limits(Fixed):
    horizontal_m: Annotated[float, Field(gt=0, le=10)]
    vertical_m: Annotated[float, Field(gt=0, le=10)]


class RegistrationInput(Fixed):
    profile: Literal['cospace.spatial-registration-input/0.1']
    synthetic: bool
    source: ModelFrame
    target: TargetFrame
    method: Literal['provided_rigid_3d']
    direction: Literal['source_to_target']
    matrix: Annotated[list[Row], Field(min_length=4, max_length=4)]
    controls: Annotated[list[Control], Field(min_length=6, max_length=128)]
    check_limits: Limits


def evaluate_registration(document, *, expected_source):
    """Expected source must come from the host's authorized fixed model loader.

    B07a only checks supplied rigid parameters. No fitting, CRS conversion,
    persistence, professional approval or map-location capability is implied.
    """
    request = RegistrationInput.model_validate(document)
    if request.source.model_dump() != expected_source:
        raise ValueError('registration_source_binding')
    if request.source.frame_id == request.target.frame_id:
        raise ValueError('registration_distinct_frames_required')
    matrix = np.asarray(request.matrix, dtype=np.float64)
    rotation = matrix[:3, :3]
    if (not np.array_equal(matrix[3], [0, 0, 0, 1])
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8, rtol=0)
            or abs(np.linalg.det(rotation) - 1) > 1e-8):
        raise ValueError('registration_proper_rigid_transform_required')
    controls = request.controls
    for values in ([p.id for p in controls], [tuple(p.source_m) for p in controls],
                   [tuple(p.target_m) for p in controls]):
        if len(set(values)) != len(values):
            raise ValueError('registration_duplicate_control')
    lower, upper = np.asarray(request.source.bounds_m)
    source = np.asarray([p.source_m for p in controls])
    if np.any(source < lower) or np.any(source > upper):
        raise ValueError('registration_control_outside_scope')
    for purpose in ('fit', 'check'):
        group = [p for p in controls if p.purpose == purpose]
        if len(group) < 3:
            raise ValueError('registration_three_controls_per_group_required')
        # Checking different coordinates is not proof of field independence.
        for field in ('source_m', 'target_m'):
            coordinates = np.asarray([getattr(p, field) for p in group])
            singular = np.linalg.svd(coordinates - coordinates.mean(0), compute_uv=False)
            if singular[1] <= max(1e-6, singular[0] * 1e-4):
                raise ValueError('registration_degenerate_control_geometry')
    rows = []
    for point in controls:
        predicted = rotation @ np.asarray(point.source_m) + matrix[:3, 3]
        delta = predicted - point.target_m
        horizontal, vertical = float(np.linalg.norm(delta[:2])), float(abs(delta[2]))
        rows.append(dict(id=point.id, purpose=point.purpose, predicted_m=predicted.tolist(),
                         delta_m=delta.tolist(), horizontal_m=horizontal, vertical_m=vertical,
                         within_limits=(horizontal <= request.check_limits.horizontal_m
                                        and vertical <= request.check_limits.vertical_m)))
    metrics = {}
    for purpose in ('fit', 'check'):
        group = [p for p in rows if p['purpose'] == purpose]
        metrics[purpose] = dict(count=len(group),
            horizontal_rmse_m=float(np.sqrt(np.mean([p['horizontal_m'] ** 2 for p in group]))),
            vertical_rmse_m=float(np.sqrt(np.mean([p['vertical_m'] ** 2 for p in group]))),
            max_horizontal_m=max(p['horizontal_m'] for p in group),
            max_vertical_m=max(p['vertical_m'] for p in group))
    passed = all(p['within_limits'] for p in rows if p['purpose'] == 'check')
    return dict(profile='cospace.spatial-registration-candidate/0.1',
        input_sha256=content_digest(request.model_dump()), metrics=metrics, controls=rows,
        calculation_status='checks_passed' if passed else 'check_limits_exceeded',
        review_status='not_reviewed', control_evidence_verified=False,
        can_focus_geographic_map=False, robot_ready=False)
