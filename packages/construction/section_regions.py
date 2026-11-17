"""Raster-enclosed section void candidates, never rooms or verified space boundaries."""
import math

import numpy as np
from scipy import ndimage

MAX_CELLS = 2_000_000
MAX_STEPS = 2_000_000
MAX_SEGMENTS = 20_000
MAX_REGIONS = 512
MAX_RUNS = 200_000
MAX_REGION_SCAN = 50_000_000
CONNECTIVITY = np.ones((3, 3), dtype=bool)


def _line_cells(points, origin, resolution):
    """Supercover: include both sides of grid edges, and all cells at grid corners."""
    a, b = (points - origin) / resolution
    delta = b - a
    times = [np.array([0., 1.])]
    for axis in range(2):
        if delta[axis] != 0:
            lo, hi = sorted((a[axis], b[axis]))
            edges = np.arange(math.ceil(lo), math.floor(hi) + 1)
            times.append((edges - a[axis]) / delta[axis])
    events = np.unique(np.clip(np.concatenate(times), 0, 1))
    times = np.concatenate((events, (events[:-1] + events[1:]) / 2))
    xy = a + times[:, None] * delta
    # Snap only numerical grid-edge roundoff (1e-9 cell); not a geometric gap repair.
    edge = np.abs(xy - np.rint(xy)) <= 1e-9
    xy = np.where(edge, np.rint(xy), xy)
    base = np.floor(xy).astype(np.int64)
    cells = [base]
    for x, y in ((1, 0), (0, 1), (1, 1)):
        selected = (edge[:, 0] if x else np.ones(len(xy), dtype=bool)) & (edge[:, 1] if y else True)
        cells.append(base[selected] - [x, y])
    return np.unique(np.concatenate(cells), axis=0)


def _runs(mask):
    result = []
    for row in np.flatnonzero(mask.any(axis=1)):
        padded = np.pad(mask[row].astype(np.int8), (1, 1))
        edges = np.flatnonzero(np.diff(padded))
        result.extend([int(row), int(a), int(b)] for a, b in zip(edges[::2], edges[1::2]))
        if len(result) > MAX_RUNS:
            raise ValueError('section_region_run_budget')
    return result


def _candidates(labels, count, resolution, minimum_area):
    exterior = set(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])).tolist())
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    keep = [i for i in range(1, count + 1) if i not in exterior and sizes[i] * resolution**2 >= minimum_area]
    if len(keep) > MAX_REGIONS:
        raise ValueError('section_region_count_budget')
    if len(keep) * labels.size > MAX_REGION_SCAN:
        raise ValueError('section_region_scan_budget')
    regions = []
    run_count = 0
    for label in keep:
        mask = labels == label
        rows, cols = np.nonzero(mask)
        runs = _runs(mask)
        run_count += len(runs)
        if run_count > MAX_RUNS:
            raise ValueError('section_region_run_budget')
        regions.append({'id': f'void-{len(regions) + 1}', 'grid_label': label, 'cells': int(sizes[label]),
                        'raster_area_m2': float(sizes[label] * resolution**2),
                        'bounds_cells': [int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1],
                        'runs': runs, 'source_segment_indices': [], 'source_entity_ids': []})
    return regions


def _validate_parameters(resolution, minimum_area):
    if (type(resolution) not in (int, float) or not math.isfinite(resolution) or not .02 <= resolution <= .5
            or type(minimum_area) not in (int, float) or not math.isfinite(minimum_area)
            or not .01 <= minimum_area <= 10_000):
        raise ValueError('section_region_parameters')


def _attribute_sources(regions, lines, labels, indices, all_segments):
    by_label = {row['grid_label']: row for row in regions}
    for index, cells in enumerate(lines):
        adjacent = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                adjacent.update(labels[cells[:, 1] + dy, cells[:, 0] + dx].tolist())
        for label in adjacent & by_label.keys():
            by_label[label]['source_segment_indices'].append(indices[index])
    for row in regions:
        row['source_entity_ids'] = sorted({all_segments[i]['source_entity_id'] for i in row['source_segment_indices']})
        del row['grid_label']


def enclosed_section_regions(section, *, resolution, minimum_area=1.):
    _validate_parameters(resolution, minimum_area)
    all_segments = section['segments']
    if len(all_segments) > MAX_SEGMENTS:
        raise ValueError('section_region_segment_budget')
    indices = [i for i, row in enumerate(all_segments) if row['ifc_type'] == 'IfcWall']
    segments = [all_segments[i] for i in indices]
    result = {'z_m': section['z_m'], 'resolution_m': resolution, 'minimum_area_m2': minimum_area,
              'input_segment_count': len(all_segments), 'barrier_segment_count': len(segments),
              'origin_xy_m': None, 'shape_rows_columns': [0, 0], 'blocked_cells': 0, 'candidates': []}
    if not segments:
        return result
    points = np.asarray([row['points_m'] for row in segments], dtype=float)
    if (points.shape != (len(segments), 2, 3) or not np.isfinite(points).all()
            or np.max(np.abs(points)) > 1_000_000 or np.any(points[:, :, 2] != section['z_m'])):
        raise ValueError('section_region_coordinates')
    xy = points[:, :, :2]
    origin = (np.floor(xy.reshape(-1, 2).min(0) / resolution) - 2) * resolution
    shape = np.ceil((xy.reshape(-1, 2).max(0) - origin) / resolution).astype(np.int64) + 3
    if int(shape[0]) * int(shape[1]) > MAX_CELLS:
        raise ValueError('section_region_cell_budget')
    # Bound work before allocating/rasterizing any long segment.
    steps = int(np.ceil(np.abs(xy[:, 1] - xy[:, 0]) / resolution).sum()) + 4 * len(segments)
    if steps > MAX_STEPS:
        raise ValueError('section_region_step_budget')
    blocked = np.zeros((int(shape[1]), int(shape[0])), dtype=bool)
    lines, cell_count = [], 0
    for line in xy:
        cells = _line_cells(line, origin, resolution)
        cell_count += len(cells)
        if cell_count > MAX_STEPS:
            raise ValueError('section_region_step_budget')
        lines.append(cells)
        blocked[cells[:, 1], cells[:, 0]] = True
    labels, count = ndimage.label(~blocked, structure=CONNECTIVITY)
    regions = _candidates(labels, count, resolution, minimum_area)
    _attribute_sources(regions, lines, labels, indices, all_segments)
    result.update(origin_xy_m=origin.tolist(), shape_rows_columns=list(blocked.shape),
                  blocked_cells=int(blocked.sum()), candidates=regions)
    return result
