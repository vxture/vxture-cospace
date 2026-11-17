"""Deterministic bounded geometric samples, never measured control correspondences."""
import numpy as np

MAX_TRIANGLES = 200_000
MAX_CLOUD_POINTS = 2_000_000


def sample_triangle_surface(triangles, *, count=6000):
    faces = np.asarray(triangles, dtype=float)
    if type(count) is not int or not 12 <= count <= 6000:
        raise ValueError('surface_sample_budget')
    if (faces.ndim != 3 or faces.shape[1:] != (3, 3) or not 1 <= len(faces) <= MAX_TRIANGLES
            or not np.isfinite(faces).all() or np.max(np.abs(faces)) > 1_000_000):
        raise ValueError('surface_triangle_budget_or_coordinates')
    areas = np.linalg.norm(np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0]), axis=1) / 2
    if areas.sum() <= 1e-12:
        raise ValueError('surface_positive_area_required')
    quota = count * areas / areas.sum()
    allocation = np.floor(quota).astype(int)
    remainder = count - allocation.sum()
    order = np.argsort(-(quota - allocation), kind='stable')
    allocation[order[:remainder]] += 1
    samples = []
    for triangle, number in zip(faces, allocation):
        if number == 0:
            continue
        sequence = np.arange(number, dtype=float)
        root = np.sqrt((sequence + .5) / number)
        turn = (sequence * ((np.sqrt(5) - 1) / 2) + .5) % 1
        weights = np.column_stack((1 - root, root * (1 - turn), root * turn))
        samples.append(weights @ triangle)
    return np.concatenate(samples)


def sample_cloud_voxels(points, *, maximum=18000):
    cloud = np.asarray(points, dtype=float)
    if type(maximum) is not int or not 12 <= maximum <= 18000:
        raise ValueError('voxel_sample_budget')
    if (cloud.ndim != 2 or cloud.shape[1] != 3 or not 12 <= len(cloud) <= MAX_CLOUD_POINTS
            or not np.isfinite(cloud).all() or np.max(np.abs(cloud)) > 1_000_000):
        raise ValueError('voxel_point_budget_or_coordinates')
    # Coalesce exact duplicates before measuring density. Every representative remains an input point.
    unique = np.unique(cloud, axis=0)
    if len(unique) <= maximum:
        return unique, {'method': 'exact_unique', 'voxel_width_numeric': None, 'input_points': len(cloud)}
    origin = unique.min(axis=0)
    lower, upper = 0.0, float(np.ptp(unique, axis=0).max())
    selected, width = unique[:1], upper
    for _ in range(18):
        trial = (lower + upper) / 2
        cells = np.floor((unique - origin) / trial).astype(np.int64)
        _, indices = np.unique(cells, axis=0, return_index=True)
        if len(indices) <= maximum:
            selected, width, upper = unique[np.sort(indices)], trial, trial
        else:
            lower = trial
    return selected, {'method': 'voxel_first_lexicographic_input', 'voxel_width_numeric': width,
                      'input_points': len(cloud), 'unique_points': len(unique), 'search_rounds': 18}
