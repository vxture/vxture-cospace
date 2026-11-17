"""Offline coordinate lookup over a fully verified design package, never field adoption."""
from typing import Annotated

from pydantic import Field

from packages.spatial.mesh_distance import nearest_surface
from packages.spatial.scene_graph import Fixed
from packages.views.agent.ifc_geometry_exchange import inspect_geometry_component
from packages.views.agent.ifc_offline_package import read_design_package

MAX_TRIANGLES = 400_000
Scalar = Annotated[float, Field(ge=-1_000_000, le=1_000_000)]


class OfflineSurfaceQuery(Fixed):
    frame_id: Annotated[str, Field(pattern=r'^ifc_world_[a-f0-9]{16}$')]
    point_xyz_m: Annotated[list[Scalar], Field(min_length=3, max_length=3)]
    max_distance_m: Annotated[float, Field(gt=0, le=1000)]


def query_package_surface(raw, *, expected_sha256, expected_source, query):
    request = OfflineSurfaceQuery.model_validate(query)
    loaded = read_design_package(raw, expected_sha256=expected_sha256, expected_source=expected_source)
    snapshot, manifest = loaded['structure'], loaded['manifest']
    if request.frame_id != snapshot['frame_id']:
        raise ValueError('ifc_offline_surface_frame_mismatch')
    if loaded['summary']['triangles'] > MAX_TRIANGLES:
        raise ValueError('ifc_offline_surface_triangle_budget')
    entities = {e['element_id']: e for e in snapshot['entities']}
    best = None
    for member in manifest['members'][1:]:
        element = member['name'][:-4]
        header, vertices, faces = inspect_geometry_component(
            loaded['members'][member['name']], expected_sha256=member['sha256'],
            structure_raw=loaded['members']['structure.json'],
            expected_structure_sha256=manifest['structure_sha256'], expected_source=expected_source,
            expected_element=element)
        hit = nearest_surface(request.point_xyz_m, vertices, faces)
        if best is None or hit['distance_m'] < best['distance_m']:
            entity = entities[element]
            best = hit | {'entity_id': entity['entity_id'], 'element_id': element,
                          'ifc_type': entity['ifc_type'], 'name': entity['name'],
                          'source_mesh_sha256': header.source_mesh_sha256,
                          'geometry_component_sha256': member['sha256']}
    match = best if best is not None and best['distance_m'] <= request.max_distance_m else None
    status = 'found' if match else 'no_match'
    if loaded['summary']['geometry_components'] == 0:
        status = 'geometry_unavailable'
    return {'profile': 'cospace.ifc-offline-nearest-surface/0.1', 'source': manifest['source'],
            'package_sha256': expected_sha256, 'structure_sha256': manifest['structure_sha256'],
            'frame_id': snapshot['frame_id'], 'unit': 'm', 'query': request.model_dump(),
            'status': status, 'match': match,
            'tested_components': loaded['summary']['geometry_components'],
            'tested_triangles': loaded['summary']['triangles'],
            'without_geometry': loaded['summary']['without_geometry'],
            'coverage': 'all_extracted_structure_entities', 'method': 'unsigned_point_to_triangle_surface',
            'tie_policy': 'lowest_element_id_then_triangle_index', 'data_kind': 'ifc_design_candidate',
            'assessment': 'unverified', 'original_ifc_content_verified': False,
            'original_mesh_content_verified': False, 'alignment_verified': False,
            'ontology_bound': False, 'real_release_ready': False,
            'limitations': ['selected_ifc_classes_only', 'missing_geometry_not_searched',
                            'no_room_containment', 'no_inside_outside_or_collision_test',
                            'no_field_alignment_or_current_state', 'no_navigation_or_traversability']}
