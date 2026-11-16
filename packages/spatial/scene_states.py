"""Explicit synthetic historical state policy; no mutation, routing or field truth."""
from packages.spatial.scene_graph import utc, validate_scene_graph
from packages.spatial.scene_identity import content_digest, snapshot_ref

POLICY = 'cospace.synthetic-state-latest-per-source/0.1'


def _latest_per_source(rows):
    selected = []
    for source in sorted({row['source_id'] for row in rows}):
        group = [row for row in rows if row['source_id'] == source]
        newest = max(utc(row['observed_at']) for row in group)
        selected.extend(row for row in group if utc(row['observed_at']) == newest)
    return sorted(selected, key=lambda row: row['id'])


def resolve_opening_state(document, identity, *, as_of, known_at):
    validate_scene_graph(document)
    when, known = utc(as_of), utc(known_at)
    entities = {row['id']: row for row in document['entities']}
    if identity not in entities:
        raise ValueError('state_entity_not_found')
    roles = {row['id']: row['role'] for row in document['ontology']['types']}
    if roles[entities[identity]['type_id']] != 'door':
        raise ValueError('state_opening_subject_required')
    rows = [row for row in document['observations'] if row['entity_id'] == identity
            and utc(row['observed_at']) <= when and utc(row['received_at']) <= known]
    latest = _latest_per_source(rows)
    active = [row for row in latest if utc(row['valid_until']) > when]
    values = {row['value'] for row in active}
    if not latest:
        status = 'unavailable'
    elif not active:
        status = 'expired'
    elif len(values) > 1:
        status = 'conflict'
    elif values == {'unknown'}:
        status = 'unknown'
    else:
        status = 'known'
    pin = snapshot_ref(document)
    return {'profile': 'cospace.synthetic-state-result/0.1', 'data_kind': 'synthetic', 'source': pin, 'entity_id': identity, 'property': 'opening_state', 'as_of': as_of, 'known_at': known_at, 'policy': POLICY, 'status': status, 'value': next(iter(values)) if status == 'known' else None, 'observation_ids': [row['id'] for row in active], 'expired_observation_ids': [row['id'] for row in latest if row not in active], 'cursor': content_digest({'source': pin, 'policy': POLICY, 'as_of': as_of, 'known_at': known_at}), 'assessment': 'unverified', 'evidence_content_verified': False, 'real_release_ready': False, 'limitations': ['no_source_priority', 'no_clock_quality_verification', 'no_correction_event_support',
                             'latest_expired_does_not_revive_older_state', 'no_navigation_or_traversability']}
