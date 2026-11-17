"""Full single-element design tessellation, bound to a fixed structure snapshot."""
import hashlib
import json
import struct
from typing import Annotated, Literal

import numpy as np
from pydantic import Field

from packages.data.ifc_workspace import load_mesh
from packages.spatial.scene_graph import Fixed
from packages.spatial.scene_identity import Digest, canonical
from packages.views.agent.ifc_structure_exchange import (
    SourcePin, StructureSnapshot, _unique, build_structure_snapshot,
)

MAGIC = b'CSIFCG01'
MAX_HEADER = 4096
MAX_VERTICES = 200_000
MAX_FACES = 400_000
MAX_BYTES = 10 * 1024 * 1024


class GeometryHeader(Fixed):
    profile: Literal['cospace.ifc-element-geometry/0.1']
    source: SourcePin
    structure_sha256: Digest
    entity_id: Annotated[str, Field(min_length=1, max_length=255)]
    element_id: Annotated[str, Field(pattern=r'^e[0-9]{5}$')]
    source_mesh_sha256: Digest
    frame_id: Annotated[str, Field(pattern=r'^ifc_world_[a-f0-9]{16}$')]
    unit: Literal['m']
    encoding: Literal['float64le_xyz_uint32le_triangles']
    vertices: Annotated[int, Field(ge=1, le=MAX_VERTICES)]
    triangles: Annotated[int, Field(ge=1, le=MAX_FACES)]
    data_kind: Literal['ifc_design_candidate']
    assessment: Literal['unverified']
    alignment_verified: Literal[False]
    ontology_bound: Literal[False]
    real_release_ready: Literal[False]


def _subject(snapshot, element):
    subject = next((e for e in snapshot.entities if e.element_id == element), None)
    if subject is None or subject.geometry_status != 'extracted':
        raise ValueError('geometry_extracted_declaration_required')
    return subject


def _budget(vertices, triangles):
    if not 1 <= vertices <= MAX_VERTICES or not 1 <= triangles <= MAX_FACES:
        raise ValueError('geometry_component_budget')


def build_geometry_component(root, space, pin, catalog, element):
    """Caller verifies source/catalog and authorization first; no mesh decimation."""
    structure_raw = build_structure_snapshot(space, pin, catalog)
    return encode_geometry_component(root, catalog, element, structure_raw)


def encode_geometry_component(root, catalog, element, structure_raw):
    """Internal reuse after validating the same catalog/source; snapshot is not client input."""
    snapshot = StructureSnapshot.model_validate_json(structure_raw)
    subject = _subject(snapshot, element)
    product = catalog['products'][int(element[1:])]
    _budget(product['mesh']['vertices'], product['mesh']['triangles'])
    vertices, faces = load_mesh(root, product)
    header = GeometryHeader.model_validate({
        'profile': 'cospace.ifc-element-geometry/0.1', 'source': snapshot.source.model_dump(),
        'structure_sha256': hashlib.sha256(structure_raw).hexdigest(), 'entity_id': subject.entity_id,
        'element_id': element, 'source_mesh_sha256': product['mesh']['sha256'], 'frame_id': snapshot.frame_id,
        'unit': 'm', 'encoding': 'float64le_xyz_uint32le_triangles', 'vertices': len(vertices), 'triangles': len(faces),
        'data_kind': 'ifc_design_candidate', 'assessment': 'unverified', 'alignment_verified': False,
        'ontology_bound': False, 'real_release_ready': False})
    metadata = canonical(header.model_dump())
    if len(metadata) > MAX_HEADER:
        raise ValueError('geometry_header_budget')
    raw = (MAGIC + struct.pack('<I', len(metadata)) + metadata
           + vertices.astype('<f8').tobytes() + faces.astype('<u4').tobytes())
    if len(raw) > MAX_BYTES:
        raise ValueError('geometry_component_budget')
    return raw


def export_geometry_component(workspace, space, pin, element):
    binding, catalog = workspace.catalog(space, pin)
    if binding is None:
        raise ValueError('ifc_not_configured')
    return build_geometry_component(binding.root, space, binding.catalog_sha256, catalog, element)


def inspect_geometry_component(raw, *, expected_sha256, structure_raw, expected_structure_sha256,
                               expected_source, expected_element):
    """Pins come from trusted distribution; this does not revalidate original IFC/NPZ."""
    from packages.views.agent.ifc_structure_exchange import inspect_structure_snapshot
    snapshot = inspect_structure_snapshot(structure_raw, expected_sha256=expected_structure_sha256,
                                          expected_source=expected_source)
    subject = _subject(snapshot, expected_element)
    if not isinstance(raw, bytes) or not 12 < len(raw) <= MAX_BYTES:
        raise ValueError('geometry_component_budget')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('geometry_byte_digest')
    if raw[:8] != MAGIC:
        raise ValueError('geometry_magic')
    size = struct.unpack_from('<I', raw, 8)[0]
    if not 1 <= size <= MAX_HEADER or 12 + size > len(raw):
        raise ValueError('geometry_header_budget')
    metadata = raw[12:12 + size]
    try:
        header = GeometryHeader.model_validate(json.loads(metadata, object_pairs_hook=_unique))
    except RecursionError as exc:
        raise ValueError('geometry_header_nesting') from exc
    if canonical(header.model_dump()) != metadata:
        raise ValueError('geometry_canonical_header')
    if (header.source != snapshot.source or header.structure_sha256 != expected_structure_sha256
            or header.frame_id != snapshot.frame_id or header.element_id != expected_element
            or header.entity_id != subject.entity_id):
        raise ValueError('geometry_structure_binding')
    start = 12 + size
    face_start = start + header.vertices * 24
    if len(raw) != face_start + header.triangles * 12:
        raise ValueError('geometry_payload_length')
    vertices = np.frombuffer(raw, dtype='<f8', count=header.vertices * 3, offset=start).reshape(-1, 3)
    faces = np.frombuffer(raw, dtype='<u4', count=header.triangles * 3, offset=face_start).reshape(-1, 3)
    if not np.isfinite(vertices).all() or np.max(np.abs(vertices)) > 10_000_000:
        raise ValueError('geometry_coordinates')
    if faces.max() >= header.vertices:
        raise ValueError('geometry_triangle_index')
    return header, vertices, faces


def geometry_summary(header, vertices, faces):
    return {'profile': header.profile, 'source': header.source.model_dump(),
            'structure_sha256': header.structure_sha256, 'entity_id': header.entity_id,
            'element_id': header.element_id, 'frame_id': header.frame_id, 'unit': 'm',
            'vertices': len(vertices), 'triangles': len(faces),
            'bounds': [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()],
            'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
            'original_ifc_content_verified': False, 'original_mesh_content_verified': False,
            'alignment_verified': False, 'ontology_bound': False, 'real_release_ready': False}
