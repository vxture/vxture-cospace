"""Bounded synthetic identity proposals from approximate boxes, never adoption."""
import math

from packages.spatial.scene_changes import compare_snapshots
from packages.spatial.scene_identity import snapshot_ref


def _boxes(document):
    result = {}
    for entity in document['entities']:
        rows = [g['value']['bounds'] for g in document['geometry'] if g['entity_id'] == entity['id']
                and g['role'] == 'approximate_bounds' and g['value']['shape'] == 'aabb']
        if len(rows) == 1:
            result[entity['id']] = rows[0]
    return result


def _similarity(a, b):
    center_a, center_b = [[(x + y) / 2 for x, y in zip(*box)] for box in (a, b)]
    overlap = math.prod(max(0, min(a[1][i], b[1][i]) - max(a[0][i], b[0][i])) for i in range(3))
    volumes = [math.prod(y - x for x, y in zip(*box)) for box in (a, b)]
    return overlap / (sum(volumes) - overlap), math.dist(center_a, center_b)


def propose_identity_matches(base, target, *, maximum_distance_m, top_k=3):
    if (type(maximum_distance_m) not in (int, float) or not math.isfinite(maximum_distance_m)
            or not 0 < maximum_distance_m <= 1_000_000 or type(top_k) is not int or not 1 <= top_k <= 10):
        raise ValueError('matching_configuration')
    changes = compare_snapshots(base, target)
    removed, added = changes['sections']['entities']['removed'], changes['sections']['entities']['added']
    if len(removed) * len(added) > 20_000:
        raise ValueError('matching_pair_budget')
    a, b = _boxes(base), _boxes(target)
    before, after = [{e['id']: e for e in document['entities']} for document in (base, target)]
    proposals = []
    for identity in removed:
        candidates = []
        if identity in a:
            for other in added:
                if other not in b or before[identity]['type_id'] != after[other]['type_id']:
                    continue
                iou, distance = _similarity(a[identity], b[other])
                if distance <= maximum_distance_m:
                    candidates.append(dict(target_id=other, approximate_box_iou=iou, center_distance_m=distance))
        candidates.sort(key=lambda row: (-row['approximate_box_iou'], row['center_distance_m'], row['target_id']))
        proposals.append(dict(source_id=identity, candidates=candidates[:top_k],
                              candidate_count_before_limit=len(candidates), truncated=len(candidates) > top_k,
                              status='unresolved' if candidates else 'no_candidate', geometry_supported=identity in a))
    return dict(profile='cospace.synthetic-identity-matches/0.1', data_kind='synthetic',
                base=snapshot_ref(base), target=snapshot_ref(target),
                configuration=dict(maximum_distance_m=maximum_distance_m, top_k=top_k, maximum_pairs=20_000),
                proposals=proposals, unsupported_target_ids=sorted(set(added) - b.keys()),
                identity_verified=False, automatic_adoption=False, real_release_ready=False,
                limitations=['approximate_bounds_only', 'same_frame_and_ontology_required',
                             'same_type_filter_not_type_verification', 'no_candidate_is_not_identity_absence',
                             'top_candidates_not_exhaustive_split_or_merge_proof'])
