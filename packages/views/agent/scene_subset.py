"""SG1 bounded JSON component subset, no archive extraction or installation."""
from copy import deepcopy
import hashlib
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from packages.spatial.scene_graph import Fixed, Identity, MAX_DOCUMENT_BYTES, validate_scene_graph
from packages.spatial.scene_identity import Digest, SnapshotRef, canonical, content_digest, snapshot_ref

Role = Literal['entities', 'geometry', 'structure', 'observations']
ROLES = ('entities', 'geometry', 'structure', 'observations')
DEPENDENCIES = {'entities': [], 'geometry': ['entities'],
                'structure': ['entities', 'geometry'], 'observations': ['entities']}
MAX_PACKAGE_BYTES = 4 * 1024 * 1024


class Component(Fixed):
    role: Role
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=MAX_DOCUMENT_BYTES)]
    depends_on: Annotated[list[Role], Field(max_length=3)]


class SubsetManifest(Fixed):
    profile: Literal['cospace.synthetic-scene-subset/0.1']
    data_kind: Literal['synthetic']
    source: SnapshotRef
    subset_snapshot_id: Identity
    requested_ids: Annotated[list[Identity], Field(min_length=1, max_length=128)]
    dependency_ids: Annotated[list[Identity], Field(max_length=1000)]
    components: Annotated[list[Component], Field(min_length=4, max_length=4)]
    selection: Literal['explicit_entities_with_incident_connection_closure']


def _selection(document, selected):
    if not isinstance(selected, list) or not 1 <= len(selected) <= 128:
        raise ValueError('subset_selection_budget')
    if any(not isinstance(i, str) for i in selected) or len(set(selected)) != len(selected):
        raise ValueError('subset_selection_identity')
    entities = {e['id'] for e in document['entities']}
    if set(selected) - entities:
        raise ValueError('subset_entity_missing')
    return set(selected)


def _incident_connections(document, requested):
    # One-hop over the original selection only: no recursive building-wide expansion.
    return [c for c in document['connections'] if c['connector_id'] in requested
            or any(p['space_id'] in requested for p in c['ports'])]


def _subset_graph(document, requested, connections):
    included = set(requested)
    for connection in connections:
        included.add(connection['connector_id'])
        included.update(p['space_id'] for p in connection['ports'])
    graph = deepcopy(document)
    graph['snapshot_id'] = 'subset-' + content_digest({'source': snapshot_ref(document),
                                                       'ids': sorted(requested)})[:32]
    graph['entities'] = [e for e in graph['entities'] if e['id'] in included]
    graph['geometry'] = [g for g in graph['geometry'] if g['entity_id'] in included]
    graph['relations'] = [r for r in graph['relations']
                          if r['source_id'] in included and r['target_id'] in included]
    graph['connections'] = deepcopy(connections)
    graph['observations'] = [o for o in graph['observations'] if o['entity_id'] in included]
    validate_scene_graph(graph)
    return graph, included


def _payloads(graph):
    return {'entities': {k: deepcopy(graph[k]) for k in
                         ('profile', 'data_kind', 'scene_id', 'snapshot_id', 'frame',
                          'ontology', 'evidence', 'sources', 'entities')},
            'geometry': deepcopy(graph['geometry']),
            'structure': {k: deepcopy(graph[k]) for k in ('relations', 'connections')},
            'observations': deepcopy(graph['observations'])}


def build_scene_subset(document, selected_ids):
    source = snapshot_ref(document)
    requested = _selection(document, selected_ids)
    graph, included = _subset_graph(document, requested, _incident_connections(document, requested))
    payloads = _payloads(graph)
    components = []
    for role in ROLES:
        raw = canonical(payloads[role])
        components.append({'role': role, 'sha256': hashlib.sha256(raw).hexdigest(),
                           'bytes': len(raw), 'depends_on': DEPENDENCIES[role][:]})
    manifest = {'profile': 'cospace.synthetic-scene-subset/0.1', 'data_kind': 'synthetic',
                'source': source, 'subset_snapshot_id': graph['snapshot_id'],
                'requested_ids': sorted(requested), 'dependency_ids': sorted(included-requested),
                'components': components,
                'selection': 'explicit_entities_with_incident_connection_closure'}
    package = {'manifest': manifest, 'payloads': payloads}
    validate_scene_subset(package, source)
    return package


def _manifest(package):
    if not isinstance(package, dict) or set(package) != {'manifest', 'payloads'}:
        raise ValueError('subset_package_structure')
    if len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise ValueError('subset_byte_budget')
    try:
        return SubsetManifest.model_validate(package['manifest'])
    except ValidationError as exc:
        raise ValueError('subset_manifest_structure:' + str(exc)) from exc


def _verify_components(manifest, payloads):
    if not isinstance(payloads, dict) or set(payloads) != set(ROLES):
        raise ValueError('subset_payload_roles')
    if len({c.role for c in manifest.components}) != len(ROLES):
        raise ValueError('subset_component_roles')
    for component in manifest.components:
        if component.depends_on != DEPENDENCIES[component.role]:
            raise ValueError('subset_component_dependencies')
        raw = canonical(payloads[component.role])
        if len(raw) != component.bytes or hashlib.sha256(raw).hexdigest() != component.sha256:
            raise ValueError('subset_component_integrity')


def _reconstruct(payloads):
    if not isinstance(payloads['entities'], dict):
        raise ValueError('subset_entity_component')
    graph = deepcopy(payloads['entities'])
    expected = {'profile', 'data_kind', 'scene_id', 'snapshot_id', 'frame',
                'ontology', 'evidence', 'sources', 'entities'}
    if set(graph) != expected:
        raise ValueError('subset_entity_component')
    structure = payloads['structure']
    if not isinstance(structure, dict) or set(structure) != {'relations', 'connections'}:
        raise ValueError('subset_structure_component')
    graph.update(geometry=deepcopy(payloads['geometry']), observations=deepcopy(payloads['observations']),
                 **deepcopy(structure))
    validate_scene_graph(graph)
    return graph


def _subset_scope(manifest, graph):
    requested, dependencies = manifest.requested_ids, manifest.dependency_ids
    if len(set(requested)) != len(requested) or len(set(dependencies)) != len(dependencies):
        raise ValueError('subset_duplicate_identity')
    if set(requested) & set(dependencies):
        raise ValueError('subset_dependency_overlap')
    if set(requested) | set(dependencies) != {e['id'] for e in graph['entities']}:
        raise ValueError('subset_identity_catalog')
    if graph['scene_id'] != manifest.source.scene_id or graph['snapshot_id'] != manifest.subset_snapshot_id:
        raise ValueError('subset_snapshot_binding')


def validate_scene_subset(package, expected_source):
    """Byte integrity and local reference closure only; not source truth or completeness."""
    manifest = _manifest(package)
    if manifest.source.model_dump() != expected_source:
        raise ValueError('subset_source_binding')
    _verify_components(manifest, package['payloads'])
    graph = _reconstruct(package['payloads'])
    _subset_scope(manifest, graph)
    return {'metadata_valid': True, 'data_kind': 'synthetic',
            'requested_ids': manifest.requested_ids[:], 'dependency_ids': manifest.dependency_ids[:],
            'source_content_verified': False, 'full_scene_coverage': False,
            'selection_boundary_complete': False, 'real_release_ready': False, 'robot_ready': False,
            'limitations': ['one_hop_connections_only', 'not_a_spatial_clip', 'no_state_resolution',
                            'source_digest_is_not_a_signature', 'no_navigation_or_traversability']}


def verify_subset_against_source(package, source_document):
    """Explicit full-source comparison; local package alone cannot prove faithful selection."""
    report = validate_scene_subset(package, snapshot_ref(source_document))
    expected = build_scene_subset(source_document, package['manifest']['requested_ids'])
    if canonical(expected) != canonical(package):
        raise ValueError('subset_differs_from_source_selection')
    return report | {'source_content_verified': True, 'selection_boundary_complete': True}
