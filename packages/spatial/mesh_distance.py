"""Unsigned distance to validated mesh arrays; no inside/outside or collision claim."""
import numpy as np

DOT_ROWS = 'ij,ij->i'


def nearest_surface(point, vertices, faces, *, chunk_size=8192):
    """Unsigned Euclidean distance; ties use the first source triangle, not a unique interface."""
    point = np.asarray(point, dtype=float)
    best = None
    for start in range(0, len(faces), chunk_size):
        a, b, c = np.moveaxis(vertices[faces[start:start + chunk_size]], 1, 0)
        nearest = a.copy()
        distances = np.einsum(DOT_ROWS, point - nearest, point - nearest)
        for u, v in ((a, b), (b, c), (c, a)):
            edge = v - u
            length2 = np.einsum(DOT_ROWS, edge, edge)
            fraction = np.divide(np.einsum(DOT_ROWS, point - u, edge), length2,
                                 out=np.zeros_like(length2), where=length2 > 0)
            candidate = u + np.clip(fraction, 0, 1)[:, None] * edge
            delta = point - candidate
            d2 = np.einsum(DOT_ROWS, delta, delta)
            take = d2 < distances
            nearest[take], distances[take] = candidate[take], d2[take]
        normal = np.cross(b - a, c - a)
        norm2 = np.einsum(DOT_ROWS, normal, normal)
        offset = np.divide(np.einsum(DOT_ROWS, point - a, normal), norm2,
                           out=np.zeros_like(norm2), where=norm2 > 0)
        projection = point - offset[:, None] * normal
        inside = norm2 > 0
        for u, v in ((a, b), (b, c), (c, a)):
            inside &= np.einsum(DOT_ROWS, np.cross(v - u, projection - u), normal) >= 0
        delta = point - projection
        d2 = np.einsum(DOT_ROWS, delta, delta)
        take = inside & (d2 < distances)
        nearest[take], distances[take] = projection[take], d2[take]
        index = int(np.argmin(distances))
        if best is None or distances[index] < best[0]:
            best = (float(distances[index]), start + index, nearest[index].tolist())
    if best is None:
        raise ValueError('annotation_geometry_empty_mesh')
    return {'distance_m': float(np.sqrt(best[0])), 'triangle_index': best[1], 'closest_point_xyz_m': best[2]}
