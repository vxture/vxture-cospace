"""Read-only nearest design surface over all extracted structure declarations."""
from typing import Annotated

from pydantic import Field

from packages.data.ifc_workspace import load_mesh
from packages.spatial.mesh_distance import nearest_surface
from packages.spatial.scene_graph import Fixed
from packages.spatial.scene_identity import Digest
from packages.views.agent.ifc_structure_exchange import StructureSnapshot, build_structure_snapshot, export_structure_snapshot

MAX_COMPONENTS = 512
MAX_TRIANGLES = 400_000
MAX_MESH_BYTES = 32 * 1024 * 1024
MAX_ARRAY_BYTES = 32 * 1024 * 1024
Scalar = Annotated[float, Field(ge=-1_000_000, le=1_000_000)]


class SurfaceQuery(Fixed):
    space_id: Annotated[str, Field(pattern=r'^space-[a-f0-9]{16}$')]
    catalog_sha256: Digest
    frame_id: Annotated[str, Field(pattern=r'^ifc_world_[a-f0-9]{16}$')]
    point_xyz_m: Annotated[list[Scalar], Field(min_length=3, max_length=3)]
    max_distance_m: Annotated[float, Field(gt=0, le=1000)]


def query_surface(workspace, query):
    binding, catalog = workspace.catalog(query.space_id, query.catalog_sha256)
    if binding is None:
        raise ValueError('ifc_not_configured')
    raw = build_structure_snapshot(query.space_id, query.catalog_sha256, catalog)
    snapshot = StructureSnapshot.model_validate_json(raw)
    if query.frame_id != snapshot.frame_id:
        raise ValueError('ifc_surface_frame_mismatch')
    subjects = sorted((e for e in snapshot.entities if e.geometry_status == 'extracted'), key=lambda e: e.element_id)
    products = {e.element_id: catalog['products'][int(e.element_id[1:])] for e in subjects}
    triangles = sum(p['mesh']['triangles'] for p in products.values())
    mesh_bytes = sum(p['mesh']['bytes'] for p in products.values())
    array_bytes = sum(p['mesh']['vertices'] * 24 + p['mesh']['triangles'] * 12 for p in products.values())
    if (len(subjects) > MAX_COMPONENTS or triangles > MAX_TRIANGLES or mesh_bytes > MAX_MESH_BYTES
            or array_bytes > MAX_ARRAY_BYTES):
        raise ValueError('ifc_surface_query_budget')
    best = None
    for entity in subjects:
        product = products[entity.element_id]
        vertices, faces = load_mesh(binding.root, product)
        hit = nearest_surface(query.point_xyz_m, vertices, faces)
        if best is None or hit['distance_m'] < best['distance_m']:
            best = hit | {'entity_id': entity.entity_id, 'element_id': entity.element_id,
                          'ifc_type': entity.ifc_type, 'name': entity.name,
                          'source_mesh_sha256': product['mesh']['sha256']}
    if export_structure_snapshot(workspace, query.space_id, query.catalog_sha256) != raw:
        raise ValueError('ifc_surface_source_changed')
    match = best if best is not None and best['distance_m'] <= query.max_distance_m else None
    return {'profile': 'cospace.ifc-nearest-surface/0.1', 'source': snapshot.source.model_dump(),
            'frame_id': snapshot.frame_id, 'unit': 'm', 'query': query.model_dump(),
            'status': ('found' if match else 'no_match') if subjects else 'geometry_unavailable',
            'match': match, 'tested_components': len(subjects), 'tested_triangles': triangles,
            'without_geometry': sum(e.geometry_status != 'extracted' for e in snapshot.entities),
            'coverage': 'all_extracted_structure_entities', 'method': 'unsigned_point_to_triangle_surface',
            'tie_policy': 'lowest_element_id_then_triangle_index', 'data_kind': 'ifc_design_candidate',
            'assessment': 'unverified', 'alignment_verified': False, 'ontology_bound': False,
            'real_release_ready': False, 'limitations': ['selected_ifc_classes_only',
                'missing_geometry_not_searched', 'no_room_containment', 'no_inside_outside_or_collision_test',
                'no_field_alignment_or_current_state', 'no_navigation_or_traversability']}
