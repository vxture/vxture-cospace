"""Multi-start geometric hypotheses, never an independently verified alignment."""
from itertools import permutations, product

import numpy as np
from scipy.spatial import cKDTree

from packages.construction.rgbd_tracking import rigid_fit, transform


def _points(value, maximum):
    points = np.asarray(value, dtype=float)
    if (points.ndim != 2 or points.shape[1] != 3 or not 12 <= len(points) <= maximum
            or not np.isfinite(points).all() or np.max(np.abs(points)) > 1_000_000):
        raise ValueError('proposal_point_budget_or_coordinates')
    if np.linalg.matrix_rank(points - points.mean(0)) < 3:
        raise ValueError('proposal_three_dimensional_geometry_required')
    return points


def _basis(points):
    return np.linalg.eigh(np.cov(points.T))[1][:, ::-1]


def _initializations(source, target):
    a, b = _basis(source), _basis(target)
    for order in permutations(range(3)):
        for signs in product((-1, 1), repeat=3):
            rotation = (b[:, order] * signs) @ a.T
            if np.linalg.det(rotation) < 0:
                continue
            matrix = np.eye(4)
            matrix[:3, :3] = rotation
            matrix[:3, 3] = target.mean(0) - rotation @ source.mean(0)
            yield matrix


def registration_proposals(source, target):
    source, target = _points(source, 6000), _points(target, 18000)
    tree = cKDTree(target)
    rows = []
    for seed, matrix in enumerate(_initializations(source, target)):
        try:
            for iteration in range(30):
                moved = transform(source, matrix)
                distances, indices = tree.query(moved, workers=1)
                keep = np.argsort(distances, kind='stable')[:max(6, int(len(source) * .7))]
                step = rigid_fit(moved[keep], target[indices[keep]])
                matrix = step @ matrix
                if np.max(np.abs(step - np.eye(4))) < 1e-8:
                    break
        except ValueError:
            continue
        moved = transform(source, matrix)
        forward = tree.query(moved, workers=1)[0]
        reverse = cKDTree(moved).query(target, workers=1)[0]
        trimmed = np.sort(forward)[:max(6, int(len(source) * .7))]
        rows.append({'seed': seed, 'iterations': iteration + 1, 'ifc_to_cloud_numeric': matrix.tolist(), 'trimmed_rmse': float(np.sqrt(np.mean(trimmed ** 2))), 'source_to_cloud_median': float(np.median(forward)), 'cloud_to_source_median': float(np.median(reverse))})
    if not rows:
        raise ValueError('proposal_no_nondegenerate_solution')
    rows.sort(key=lambda row: (row['source_to_cloud_median'] + row['cloud_to_source_median'], row['seed']))
    return {'profile': 'cospace.ifc-geometric-proposals/0.1', 'candidates': rows, 'source_points': len(source), 'cloud_points': len(target), 'initializations': 24, 'method': 'pca_proper_axis_permutations_trimmed_point_icp', 'cloud_numeric_units_per_ifc_m_hypothesis': 1.0, 'unit_verified': False, 'independent_control_count': 0, 'alignment_verified': False, 'real_release_ready': False, 'limitations': ['no_scale_estimation', 'no_unit_or_gravity_evidence', 'no_independent_controls',
                             'sample_residuals_not_alignment_accuracy', 'local_minima_and_symmetry_possible',
                             'not_a_semantic_or_field_confirmation', 'no_automatic_transform_adoption']}
