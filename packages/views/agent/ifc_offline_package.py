"""Bounded immutable design-source bundle. No extraction, field adoption or publishing."""
import hashlib
import json
import struct
from typing import Annotated, Literal

from pydantic import Field

from packages.spatial.scene_graph import Fixed
from packages.spatial.scene_identity import Digest, canonical
from packages.views.agent.ifc_structure_exchange import (
    SourcePin, StructureSnapshot, _unique, export_structure_snapshot, inspect_structure_snapshot,
)
from packages.views.agent.ifc_geometry_exchange import (
    MAX_HEADER as GEOMETRY_HEADER_BYTES, MAX_VERTICES, MAX_FACES,
    encode_geometry_component, inspect_geometry_component,
)

MAGIC = b'CSIFCP01'
MAX_BYTES = 32 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
MAX_GEOMETRIES = 512
STRUCTURE_MEMBER = 'structure.json'


class Member(Fixed):
    name: Annotated[str, Field(pattern=r'^(structure\.json|e[0-9]{5}\.bin)$')]
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=10 * 1024 * 1024)]


class PackageManifest(Fixed):
    profile: Literal['cospace.ifc-design-package/0.1']
    source: SourcePin
    structure_sha256: Digest
    geometry_coverage: Literal['all_extracted_structure_entities']
    members: Annotated[list[Member], Field(min_length=1, max_length=MAX_GEOMETRIES + 1)]
    data_kind: Literal['ifc_design_candidate']
    assessment: Literal['unverified']
    alignment_verified: Literal[False]
    ontology_bound: Literal[False]
    real_release_ready: Literal[False]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _preflight(catalog, snapshot, structure_bytes):
    elements = sorted(e.element_id for e in snapshot.entities if e.geometry_status == 'extracted')
    if len(elements) > MAX_GEOMETRIES:
        raise ValueError('ifc_package_geometry_budget')
    maximum = 12 + MAX_MANIFEST + structure_bytes
    for element in elements:
        mesh = catalog['products'][int(element[1:])]['mesh']
        if mesh['vertices'] > MAX_VERTICES or mesh['triangles'] > MAX_FACES:
            raise ValueError('ifc_package_geometry_budget')
        maximum += 12 + GEOMETRY_HEADER_BYTES + mesh['vertices'] * 24 + mesh['triangles'] * 12
    if maximum > MAX_BYTES:
        raise ValueError('ifc_package_byte_budget')
    return elements


def export_design_package(workspace, space, pin):
    # Validate source once; all members are digest-checked against this fixed catalog.
    binding, catalog = workspace.catalog(space, pin)
    if binding is None:
        raise ValueError('ifc_not_configured')
    from packages.views.agent.ifc_structure_exchange import build_structure_snapshot
    structure = build_structure_snapshot(space, pin, catalog)
    snapshot = StructureSnapshot.model_validate_json(structure)
    elements = _preflight(catalog, snapshot, len(structure))
    payloads = [(STRUCTURE_MEMBER, structure)]
    for element in elements:
        raw = encode_geometry_component(binding.root, catalog, element, structure)
        payloads.append((element + '.bin', raw))
    # Detect source/config changes during the batch before returning any download.
    if export_structure_snapshot(workspace, space, pin) != structure:
        raise ValueError('ifc_package_source_changed')
    manifest = PackageManifest.model_validate({
        'profile': 'cospace.ifc-design-package/0.1', 'source': snapshot.source.model_dump(),
        'structure_sha256': _sha(structure), 'geometry_coverage': 'all_extracted_structure_entities',
        'members': [{'name': name, 'sha256': _sha(raw), 'bytes': len(raw)} for name, raw in payloads],
        'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
        'alignment_verified': False, 'ontology_bound': False, 'real_release_ready': False})
    metadata = canonical(manifest.model_dump())
    if len(metadata) > MAX_MANIFEST:
        raise ValueError('ifc_package_manifest_budget')
    raw = MAGIC + struct.pack('<I', len(metadata)) + metadata + b''.join(data for _, data in payloads)
    if len(raw) > MAX_BYTES:
        raise ValueError('ifc_package_byte_budget')
    return raw


def _read_members(raw, manifest, start):
    result = {}
    for member in manifest.members:
        end = start + member.bytes
        if member.name in result or end > len(raw):
            raise ValueError('ifc_package_member_layout')
        data = raw[start:end]
        if _sha(data) != member.sha256:
            raise ValueError('ifc_package_member_digest')
        result[member.name] = data
        start = end
    if start != len(raw):
        raise ValueError('ifc_package_payload_length')
    return result


def read_design_package(raw, *, expected_sha256, expected_source):
    if not isinstance(raw, bytes) or not 12 < len(raw) <= MAX_BYTES:
        raise ValueError('ifc_package_byte_budget')
    if _sha(raw) != expected_sha256:
        raise ValueError('ifc_package_byte_digest')
    if raw[:8] != MAGIC:
        raise ValueError('ifc_package_magic')
    size = struct.unpack_from('<I', raw, 8)[0]
    if not 1 <= size <= MAX_MANIFEST or 12 + size > len(raw):
        raise ValueError('ifc_package_manifest_budget')
    metadata = raw[12:12 + size]
    try:
        manifest = PackageManifest.model_validate(json.loads(metadata, object_pairs_hook=_unique))
    except RecursionError as exc:
        raise ValueError('ifc_package_manifest_nesting') from exc
    if canonical(manifest.model_dump()) != metadata:
        raise ValueError('ifc_package_canonical_manifest')
    if manifest.source != SourcePin.model_validate(expected_source):
        raise ValueError('ifc_package_source_binding')
    members = _read_members(raw, manifest, 12 + size)
    structure_raw = members.get(STRUCTURE_MEMBER, b'')
    snapshot = inspect_structure_snapshot(structure_raw, expected_sha256=manifest.structure_sha256,
                                          expected_source=expected_source)
    expected = [STRUCTURE_MEMBER] + sorted(e.element_id + '.bin' for e in snapshot.entities
                                          if e.geometry_status == 'extracted')
    if [m.name for m in manifest.members] != expected:
        raise ValueError('ifc_package_geometry_coverage')
    vertices = triangles = 0
    for member in manifest.members[1:]:
        _, points, faces = inspect_geometry_component(
            members[member.name], expected_sha256=member.sha256, structure_raw=structure_raw,
            expected_structure_sha256=manifest.structure_sha256, expected_source=expected_source,
            expected_element=member.name[:-4])
        vertices += len(points)
        triangles += len(faces)
    summary = {'profile': manifest.profile, 'source': manifest.source.model_dump(),
            'structure_sha256': manifest.structure_sha256, 'entities': len(snapshot.entities),
            'relations': len(snapshot.relations), 'geometry_components': len(manifest.members) - 1,
            'without_geometry': sum(e.geometry_status != 'extracted' for e in snapshot.entities),
            'vertices': vertices, 'triangles': triangles, 'data_kind': 'ifc_design_candidate',
            'assessment': 'unverified', 'original_ifc_content_verified': False,
            'original_mesh_content_verified': False, 'alignment_verified': False,
            'ontology_bound': False, 'real_release_ready': False}
    return {'manifest': manifest.model_dump(), 'structure': snapshot.model_dump(),
            'members': members, 'summary': summary}


def inspect_design_package(raw, *, expected_sha256, expected_source):
    return read_design_package(raw, expected_sha256=expected_sha256,
                               expected_source=expected_source)['summary']
