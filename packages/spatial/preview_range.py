"""Bounded surface-evidence selection shared by online and offline previews."""
import math
from decimal import Decimal,ROUND_CEILING,localcontext

MAX_RANGE_CELLS = 4096
DEFAULT_RANGE_CELLS = 1024
MAX_ABS_COORDINATE_M = 1_000_000


def range_indices(resolution, bounds_m, frame_id, expected_frame, limit):
    if (not isinstance(frame_id, str) or not frame_id or len(frame_id) > 256
            or frame_id != expected_frame):
        raise ValueError('range_frame_mismatch')
    if type(limit) is not int or not 1 <= limit <= MAX_RANGE_CELLS:
        raise ValueError('invalid_range_limit')
    if not math.isfinite(resolution) or resolution <= 0:
        raise ValueError('invalid_resolution')
    if (not isinstance(bounds_m, (list, tuple)) or len(bounds_m) != 2
            or any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in bounds_m)):
        raise ValueError('invalid_range_bounds')
    if any(type(v) not in (int, float) or abs(v) > MAX_ABS_COORDINATE_M
           or not math.isfinite(v) for row in bounds_m for v in row):
        raise ValueError('invalid_range_bounds')
    lo, hi = [[float(v) for v in row] for row in bounds_m]
    if any(a >= b for a, b in zip(lo, hi)):
        raise ValueError('invalid_range_bounds')
    # Decimal declarations keep negative and fractional boundary behavior stable.
    # Select integers i satisfying min <= (i + 0.5) * resolution < max.
    with localcontext() as context:
        context.prec=64
        step=Decimal(str(resolution))
        index_lo=[int((Decimal(str(v))/step-Decimal('.5')).to_integral_value(rounding=ROUND_CEILING)) for v in lo]
        index_hi=[int((Decimal(str(v))/step-Decimal('.5')).to_integral_value(rounding=ROUND_CEILING)) for v in hi]
    return lo,hi,index_lo,index_hi


def surface_range(cells, resolution, bounds_m, frame_id, expected_frame, limit):
    lo,hi,index_lo,index_hi=range_indices(resolution,bounds_m,frame_id,expected_frame,limit)
    selected = []
    count = 0
    # Do not enumerate unknown volume or allocate an unbounded list of matches.
    for cell in cells:
        if all(index_lo[i] <= cell[i] < index_hi[i] for i in range(3)):
            count += 1
            if count <= limit:
                selected.append(cell)
    complete = count <= limit
    indices = [list(cell) for cell in sorted(selected)] if complete else []
    return {
        'bounds_m': [lo, hi], 'frame_id': frame_id, 'unit': 'm',
        'selection_rule': 'cell_center_in_half_open_aabb',
        'resolution_m': resolution, 'limit': limit, 'max_limit': MAX_RANGE_CELLS,
        'status': 'complete' if complete else 'limit_exceeded', 'result_complete': complete,
        'matched_cells': count, 'returned_cells': len(indices), 'cell_indices': indices,
        'cell_state': 'surface_candidate', 'unlisted_state': 'unknown' if complete else None,
        'coverage': 'surface_evidence_only',
        'action': 'none' if complete else 'shrink_bounds_or_increase_limit_within_max',
    }
