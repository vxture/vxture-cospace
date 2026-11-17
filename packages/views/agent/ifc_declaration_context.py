"""Bounded neighborhoods of source declarations, not physical connectivity or routes."""
from collections import deque
from typing import Annotated, Literal

from pydantic import Field, model_validator

from packages.spatial.scene_graph import Fixed
from packages.views.agent.ifc_structure_exchange import inspect_structure_snapshot

KINDS = ['aggregates', 'contained_in', 'opening_in', 'fills', 'space_boundary']
Kind = Literal['aggregates', 'contained_in', 'opening_in', 'fills', 'space_boundary']
MAX_ENTITIES = 512
MAX_RELATIONS = 2048


class DeclarationContextQuery(Fixed):
    element_id: Annotated[str, Field(pattern=r'^e[0-9]{5}$')]
    max_hops: Annotated[int, Field(ge=1, le=4)] = 1
    relation_kinds: Annotated[list[Kind], Field(min_length=1, max_length=5)] = KINDS.copy()

    @model_validator(mode='after')
    def unique_kinds(self):
        if len(set(self.relation_kinds)) != len(self.relation_kinds):
            raise ValueError('declaration_context_duplicate_kind')
        return self


def _neighborhood(subject, relations, maximum):
    neighbors = {}
    for row in relations:
        neighbors.setdefault(row.source_id, set()).add(row.target_id)
        neighbors.setdefault(row.target_id, set()).add(row.source_id)
    distances = {subject: 0}
    pending = deque([subject])
    while pending:
        identity = pending.popleft()
        if distances[identity] == maximum:
            continue
        for other in neighbors.get(identity, ()):
            if other not in distances:
                if len(distances) == MAX_ENTITIES:
                    raise ValueError('declaration_context_entity_budget')
                distances[other] = distances[identity] + 1
                pending.append(other)
    boundary = {identity for identity in distances if any(
        other not in distances for other in neighbors.get(identity, ()))}
    return distances, boundary


def query_declaration_context(raw, *, expected_sha256, expected_source, query):
    request = DeclarationContextQuery.model_validate(query)
    snapshot = inspect_structure_snapshot(raw, expected_sha256=expected_sha256, expected_source=expected_source)
    subject = next((e for e in snapshot.entities if e.element_id == request.element_id), None)
    if subject is None:
        raise ValueError('declaration_context_element_unavailable')
    relations = [r for r in snapshot.relations if r.kind in request.relation_kinds]
    distances, boundary = _neighborhood(subject.entity_id, relations, request.max_hops)
    selected = [r.model_dump() for r in relations if r.source_id in distances and r.target_id in distances]
    if len(selected) > MAX_RELATIONS:
        raise ValueError('declaration_context_relation_budget')
    return {'profile': 'cospace.ifc-declaration-context/0.1', 'source': snapshot.source.model_dump(),
            'structure_sha256': expected_sha256, 'frame_id': snapshot.frame_id, 'unit': 'm',
            'query': request.model_dump(), 'subject': subject.model_dump(),
            'entities': [e.model_dump() | {'hop_distance': distances[e.entity_id]}
                         for e in snapshot.entities if e.entity_id in distances],
            'relations': selected,
            'boundary_entity_ids': [e.entity_id for e in snapshot.entities if e.entity_id in boundary],
            'has_more': bool(boundary), 'coverage': 'selected_ifc_classes_only',
            'traversal': 'undirected_source_relations_original_direction_preserved',
            'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
            'original_ifc_content_verified': False, 'geometry_included': False,
            'alignment_verified': False, 'ontology_bound': False, 'real_release_ready': False,
            'limitations': ['source_declarations_not_field_facts', 'relation_hops_not_spatial_distance',
                            'no_transitive_containment_inference', 'no_space_connection_inference',
                            'no_navigation_or_traversability', 'no_current_state']}
