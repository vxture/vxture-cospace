"""Spatial invariants for a deliberately limited synthetic profile."""
import math


def validate_spatial(truth, objects):
    frame = truth['frame']
    if (frame['unit'] != 'm' or frame['handedness'] != 'right'
            or frame['axes'] != ['along_corridor', 'left', 'up']
            or not frame['frame_id'] or not frame['origin_description']):
        raise ValueError('unsupported or incomplete sample coordinate definition')
    bounds = truth['target_scope']
    if len(bounds) != 2 or any(len(row) != 3 for row in bounds):
        raise ValueError('target_scope requires two xyz corners')
    def numeric(value):
        return type(value) is int or (type(value) is float and math.isfinite(value))
    if not all(numeric(v) for row in bounds for v in row):
        raise ValueError('target_scope must be finite numeric coordinates')
    if any(a >= b for a, b in zip(*bounds)):
        raise ValueError('target_scope must have positive extent')
    for obj in objects:
        point = obj['anchor_xyz']
        if len(point) != 3 or not all(numeric(v) for v in point):
            raise ValueError('invalid object anchor')
        if any(v < a or v > b for v, a, b in zip(point, *bounds)):
            raise ValueError('object anchor outside target scope')
