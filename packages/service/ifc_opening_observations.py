"""Read-only reported state for a pinned design object, after business authorization."""
from packages.infrastructure.spatial_observation_store import ObservationJournal
from packages.spatial.opening_observations import now_utc


def observation_scope(principal, space, pin):
    return {'issuer': principal.issuer, 'organization': principal.org_id,
            'workspace': principal.workspace_id, 'space_id': space, 'catalog_sha256': pin}


class IfcOpeningObservations:
    def __init__(self, root, ifc_workspace, *, clock=now_utc):
        self.journal = ObservationJournal(root)
        self.ifc = ifc_workspace
        self.clock = clock

    def read(self, principal, space, pin, element):
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
        if not self.journal.registered(scope):
            return result
        when = self.clock()
        state = self.journal.resolve(scope, subject['entity_id'], as_of=when, known_at=when)
        if state['data_kind'] != 'ifc_design_candidate':
            raise ValueError('observation_source_kind_mismatch')
        return result | {'configured': True, 'status': state['status'], 'value': state['value'],
                         'as_of': when, 'known_at': when, 'cursor': state['cursor'],
                         'through_sequence': state['through_sequence'],
                         'reported_at': state['last_received_at'],
                         'active_count': len(state['active']), 'expired_count': len(state['expired']),
                         'retracted_count': len(state['retracted'])}
