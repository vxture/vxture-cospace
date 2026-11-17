"""Point classification against validated single-ring, constant-height candidates."""
import math

from packages.spatial.ifc_annotations import _contains, _edges


def _edge_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    fraction = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(point[0] - a[0] - fraction * dx, point[1] - a[1] - fraction * dy)


def classify_region(area, point, tolerance):
    """Caller validates area and finite bounded point/tolerance first.

    A tolerance band extends to both sides of the prism boundary. This is a
    distance in the annotation frame, not a survey accuracy or field guarantee.
    """
    low, high = area.z_range_m
    edge = min(_edge_distance(point, a, b) for a, b in _edges(area.footprint_xy_m))
    xy_inside = _contains(area, [point[0], point[1], (low + high) / 2])
    z_outside = max(low - point[2], point[2] - high, 0.0)
    inside = xy_inside and z_outside == 0
    if inside:
        distance = min(edge, point[2] - low, high - point[2])
    else:
        distance = math.hypot(0.0 if xy_inside else edge, z_outside)
    if distance <= tolerance:
        return {'classification': 'boundary_candidate', 'boundary_distance_m': distance}
    if inside:
        return {'classification': 'interior', 'boundary_distance_m': distance}
    return None
