"""Small synthetic region expression; no voxel or safety-control guarantee."""
import math


def validate_point(point):
    if (not isinstance(point, (list, tuple)) or len(point) != 3
            or not all(type(v) is int or (type(v) is float and math.isfinite(v)) for v in point)):
        raise ValueError('point requires three finite numeric coordinates')


def validate_box(bounds):
    for corner in bounds:
        validate_point(corner)
    if any(a >= b for a, b in zip(*bounds)):
        raise ValueError('coverage bounds must have positive extent')


def validate_coverage(coverage, truth):
    if (coverage['scene_id'] != truth['scene_id']
            or coverage['frame_id'] != truth['frame']['frame_id']
            or coverage['bounds'] != truth['target_scope']):
        raise ValueError('coverage scene/frame/scope mismatch')
    validate_box(coverage['bounds'])
    evidence = [e['evidence_id'] for e in coverage['evidence']]
    if len(evidence) != len(set(evidence)):
        raise ValueError('duplicate coverage evidence identity')
    seen = set()
    for region in coverage['regions']:
        if region['region_id'] in seen:
            raise ValueError('duplicate coverage region identity')
        seen.add(region['region_id'])
        validate_box(region['bounds'])
        for corner in region['bounds']:
            if any(v < a or v > b for v, a, b in zip(corner, *coverage['bounds'])):
                raise ValueError('coverage region outside target scope')
        refs = region['evidence_ids']
        if len(refs) != len(set(refs)) or set(refs) - set(evidence):
            raise ValueError('invalid coverage evidence reference')
        if region['state'] in ('occupied', 'observed_free'):
            if not refs or region['reason'] != 'synthetic_observation':
                raise ValueError('occupied/free requires synthetic observation evidence')
        elif region['reason'] == 'synthetic_observation':
            raise ValueError('unknown requires an explicit unknown reason')
        elif region['reason'] in ('conflict', 'degraded') and not refs:
            raise ValueError('conflict/degraded requires diagnostic evidence')


def contains(bounds, point):
    # Half-open boxes avoid attributing a shared boundary to two adjacent regions.
    return all(a <= v < b for v, a, b in zip(point, *bounds))


def query_coverage(coverage, point):
    validate_point(point)
    if not contains(coverage['bounds'], point):
        return {'state': 'out_of_scope', 'reason': 'outside_target_scope', 'evidence_ids': []}
    hits = [r for r in coverage['regions'] if contains(r['bounds'], point)]
    evidence = sorted({e for r in hits for e in r['evidence_ids']})
    if not hits:
        return {'state': 'unknown', 'reason': 'unobserved', 'evidence_ids': []}
    states = {r['state'] for r in hits}
    if 'occupied' in states and 'observed_free' in states:
        return {'state': 'unknown', 'reason': 'conflict', 'evidence_ids': evidence}
    if 'unknown' in states:
        reasons = {r['reason'] for r in hits if r['state'] == 'unknown'}
        reason = next(r for r in ('conflict', 'degraded', 'unobserved') if r in reasons)
        return {'state': 'unknown', 'reason': reason, 'evidence_ids': evidence}
    return {'state': hits[0]['state'], 'reason': 'synthetic_observation', 'evidence_ids': evidence}
