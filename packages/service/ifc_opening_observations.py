"""Read-only reported state for a pinned design object, after business authorization."""
from typing import Annotated

from pydantic import Field, ValidationInfo, model_validator

from packages.infrastructure.spatial_observation_store import ObservationJournal
from packages.spatial.opening_observations import now_utc
from packages.spatial.scene_graph import Fixed, utc
from packages.spatial.scene_identity import Digest


class ObservationReplay(Fixed):
    as_of: Annotated[str, Field(min_length=20, max_length=27)]
    known_at: Annotated[str, Field(min_length=20, max_length=27)]
    through_sequence: Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,15})$')]

    @model_validator(mode='after')
    def times(self, info: ValidationInfo):
        observed, known = utc(self.as_of), utc(self.known_at)
        if info.context and max(observed, known) > utc(info.context['now']):
            raise ValueError('observation_replay_future')
        return self


def observation_scope(principal, space, pin):
    return {'issuer': principal.issuer, 'organization': principal.org_id,
            'workspace': principal.workspace_id, 'space_id': space, 'catalog_sha256': pin}


class ObservationBatchQuery(Fixed):
    space_id: Annotated[str, Field(pattern=r'^space-[a-f0-9]{16}$')]
    catalog_sha256: Digest
    element_ids: Annotated[list[Annotated[str, Field(pattern=r'^e[0-9]{5}$')]], Field(min_length=1, max_length=128)]
    replay: ObservationReplay | None = None

    @model_validator(mode='after')
    def unique_elements(self):
        if len(set(self.element_ids)) != len(self.element_ids):
            raise ValueError('observation_batch_duplicate_element')
        return self


def _summary(state):
    return {'status': state['status'], 'value': state['value'], 'cursor': state['cursor'],
            'reported_at': state['last_received_at'], 'active_count': len(state['active']),
            'expired_count': len(state['expired']), 'retracted_count': len(state['retracted'])}


class IfcOpeningObservations:
    def __init__(self, root, ifc_workspace, *, clock=now_utc):
        self.journal = ObservationJournal(root)
        self.ifc = ifc_workspace
        self.clock = clock

    def read_many(self, principal, query):
        when = self.clock()
        replay = (ObservationReplay.model_validate(query.replay.model_dump(), context={'now': when})
                  if query.replay is not None else None)
        structure = self.ifc.structure_view(query.space_id, query.catalog_sha256)
        index = {e['element_id']: e for e in structure['entities'] if e['source_role'] == 'door'}
        if set(query.element_ids) - index.keys():
            raise ValueError('observation_door_declaration_required')
        scope = observation_scope(principal, query.space_id, query.catalog_sha256)
        if not self.journal.registered(scope):
            raise ValueError('observation_batch_registration_required')
        subjects = [index[element]['entity_id'] for element in query.element_ids]
        state = self.journal.resolve_many(scope, subjects, as_of=replay.as_of if replay else when,
                                          known_at=replay.known_at if replay else when,
                                          through_sequence=int(replay.through_sequence) if replay else None)
        if any(s['data_kind'] != 'ifc_design_candidate' for s in state['states']):
            raise ValueError('observation_source_kind_mismatch')
        return {'profile': 'cospace.ifc-opening-observation-batch/0.1', 'space_id': query.space_id,
                'catalog_sha256': query.catalog_sha256, 'as_of': state['as_of'], 'known_at': state['known_at'],
                'through_sequence': state['through_sequence'], 'cursor': state['cursor'],
                'states': [{'element_id': element, 'entity_id': subject, **_summary(value)}
                           for element, subject, value in zip(query.element_ids, subjects, state['states'])],
                'catalog_content_verified': True, 'source_content_verified': False,
                'evidence_content_verified': False, 'clock_quality_verified': False,
                'data_kind': 'ifc_design_candidate', 'assessment': 'unverified', 'real_release_ready': False}

    def read(self, principal, space, pin, element, *, replay=None):
        when = self.clock()
        query = ObservationReplay.model_validate(replay, context={'now': when}) if replay is not None else None
        structure = self.ifc.structure_view(space, pin)
        subject = next((e for e in structure['entities'] if e['element_id'] == element), None)
        if subject is None or subject['source_role'] != 'door':
            raise ValueError('observation_door_declaration_required')
        result = {'profile': 'cospace.ifc-opening-observation-view/0.1', 'space_id': space,
                  'catalog_sha256': pin, 'element_id': element, 'entity_id': subject['entity_id'],
                  'configured': False, 'status': 'unavailable', 'value': None, 'reported_at': None,
                  'catalog_content_verified': True, 'source_content_verified': False, 'evidence_content_verified': False,
                  'clock_quality_verified': False, 'real_release_ready': False,
                  'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
                  'active_count': 0, 'expired_count': 0, 'retracted_count': 0}
        scope = observation_scope(principal, space, pin)
        if not self.journal.registered(scope, subject['entity_id']):
            if query is not None:
                raise ValueError('observation_replay_registration_unavailable')
            return result
        as_of, known_at = (query.as_of, query.known_at) if query else (when, when)
        state = self.journal.resolve(scope, subject['entity_id'], as_of=as_of, known_at=known_at,
                                     through_sequence=int(query.through_sequence) if query else None)
        if state['data_kind'] != 'ifc_design_candidate':
            raise ValueError('observation_source_kind_mismatch')
        return result | {'configured': True, 'as_of': as_of, 'known_at': known_at,
                         'through_sequence': state['through_sequence'], **_summary(state)}
