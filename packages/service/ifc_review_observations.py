"""Bind a reviewed design description and one journal read without adopting either."""
from typing import Annotated

from pydantic import Field

from packages.construction.ifc_review_snapshot import inspect_review_snapshot
from packages.service.ifc_opening_observations import ObservationReplay, observation_scope, _summary
from packages.spatial.scene_graph import Fixed, utc
from packages.spatial.scene_identity import Digest, content_digest


class ReviewObservationQuery(Fixed):
    snapshot_sha256: Digest
    element_ids: Annotated[list[Annotated[str, Field(pattern=r'^e[0-9]{5}$')]], Field(min_length=1, max_length=128)]
    replay: ObservationReplay | None = None
    expected_context_cursor: Digest | None = None


def read_review_observations(journal, principal, raw, *, query, design_package, expected_source,
                             now, ontology_raw=None):
    """Trusted caller authorizes scene and ontology before calling; no public route.

    A context cursor is a reproducibility check, never an authorization token.
    """
    query = ReviewObservationQuery.model_validate(query)
    if len(set(query.element_ids)) != len(query.element_ids):
        raise ValueError('review_observation_duplicate_element')
    utc(now)
    replay = ObservationReplay.model_validate(query.replay.model_dump(), context={'now': now}) if query.replay else None
    if query.expected_context_cursor is not None and replay is None:
        raise ValueError('review_observation_replay_required')
    checked = inspect_review_snapshot(raw, expected_sha256=query.snapshot_sha256, design_package=design_package,
                                      expected_source=expected_source, ontology_raw=ontology_raw)
    source = checked['snapshot']['source']
    doors = {row['element_id']: row for row in checked['structure']['entities'] if row['source_role'] == 'door'}
    if set(query.element_ids) - doors.keys():
        raise ValueError('review_observation_door_required')
    scope = observation_scope(principal, source['space_id'], source['catalog_sha256'])
    entities = [doors[element]['entity_id'] for element in query.element_ids]
    # One transaction pins registration and the whole selected journal prefix.
    state = journal.resolve_many(scope, entities, as_of=replay.as_of if replay else now,
                                  known_at=replay.known_at if replay else now,
                                  through_sequence=int(replay.through_sequence) if replay else None)
    if any(row['data_kind'] != 'ifc_design_candidate' for row in state['states']):
        raise ValueError('review_observation_source_kind_mismatch')
    context = {'profile': 'cospace.ifc-review-observation-context/0.1',
               'snapshot_sha256': query.snapshot_sha256, 'source': source,
               'design_package_sha256': checked['snapshot']['design_package_sha256'],
               'structure_sha256': checked['snapshot']['structure_sha256'],
               'as_of': state['as_of'], 'known_at': state['known_at'], 'through_sequence': state['through_sequence'],
               'observation_cursor': state['cursor'],
               'states': [{'element_id': element, 'entity_id': entity, **_summary(value)}
                          for element, entity, value in zip(query.element_ids, entities, state['states'])],
               'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
               'alignment_verified': False, 'ontology_bound': False,
               'evidence_content_verified': False, 'clock_quality_verified': False, 'real_release_ready': False}
    cursor = content_digest(context)
    if query.expected_context_cursor is not None and query.expected_context_cursor != cursor:
        raise ValueError('review_observation_context_changed')
    return context | {'context_cursor': cursor}
