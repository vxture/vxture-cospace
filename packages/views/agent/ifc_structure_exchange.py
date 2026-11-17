"""Pinned design declarations for independent consumers, not adopted spatial facts."""
from collections import Counter
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from packages.data.ifc_structure_read import Relation, validate_structure
from packages.spatial.scene_graph import Fixed
from packages.spatial.scene_identity import Digest, canonical

PROFILE = 'cospace.ifc-structure-snapshot/0.1'
MAX_BYTES = 8 * 1024 * 1024


class SourcePin(Fixed):
    space_id: Annotated[str, Field(pattern=r'^space-[a-f0-9]{16}$')]
    catalog_sha256: Digest
    ifc_sha256: Digest
    ifc_bytes: Annotated[int, Field(ge=1, le=128 * 1024 * 1024)]


class Declaration(Fixed):
    entity_id: Annotated[str, Field(min_length=1, max_length=255)]
    element_id: Annotated[str, Field(pattern=r'^e[0-9]{5}$')]
    ifc_type: Annotated[str, Field(pattern=r'^Ifc[A-Za-z0-9]+$', max_length=110)]
    source_role: Literal['building', 'level', 'space', 'door', 'stair', 'stair_flight',
                         'opening', 'wall', 'slab', 'distribution_board']
    name: Annotated[str, Field(max_length=4096)]
    geometry_status: Literal['extracted', 'no_representation', 'extraction_failed']


class StructureSnapshot(Fixed):
    profile: Literal['cospace.ifc-structure-snapshot/0.1']
    data_kind: Literal['ifc_design_candidate']
    assessment: Literal['unverified']
    source: SourcePin
    frame_id: Annotated[str, Field(pattern=r'^ifc_world_[a-f0-9]{16}$')]
    unit: Literal['m']
    coverage: Literal['selected_ifc_classes_only']
    geometry_included: Literal[False]
    alignment_verified: Literal[False]
    ontology_bound: Literal[False]
    real_release_ready: Literal[False]
    entities: Annotated[list[Declaration], Field(min_length=1, max_length=10_000)]
    relations: Annotated[list[Relation], Field(max_length=20_000)]

    @model_validator(mode='after')
    def references(self):
        ids = {e.entity_id for e in self.entities}
        elements = {e.element_id for e in self.entities}
        if len(ids) != len(self.entities) or len(elements) != len(self.entities):
            raise ValueError('snapshot_duplicate_entity')
        if self.frame_id != 'ifc_world_' + self.source.ifc_sha256[:16]:
            raise ValueError('snapshot_frame_binding')
        keys = {(r.ifc_relation_id, r.kind, r.source_id, r.target_id) for r in self.relations}
        if len(keys) != len(self.relations) or any(
                r.source_id not in ids or r.target_id not in ids or r.source_id == r.target_id
                for r in self.relations):
            raise ValueError('snapshot_relation_binding')
        return self


def build_structure_snapshot(space, pin, catalog):
    """Caller must first verify catalog/source bytes and authorize the scene."""
    entities, relations, products = validate_structure(catalog)
    indices = {p['global_id']: f'e{i:05}' for i, p in enumerate(catalog['products'])}
    rows = [{'entity_id': e.entity_id, 'element_id': indices[e.entity_id], 'ifc_type': e.ifc_type,
             'source_role': e.role, 'name': products[e.entity_id]['name'],
             'geometry_status': products[e.entity_id]['geometry_status']} for e in entities]
    document = {'profile': PROFILE, 'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
                'source': {'space_id': space, 'catalog_sha256': pin, 'ifc_sha256': catalog['source']['sha256'],
                           'ifc_bytes': catalog['source']['bytes']},
                'frame_id': catalog['frame_id'], 'unit': 'm', 'coverage': 'selected_ifc_classes_only',
                'geometry_included': False, 'alignment_verified': False, 'ontology_bound': False,
                'real_release_ready': False, 'entities': rows, 'relations': relations}
    raw = canonical(StructureSnapshot.model_validate(document).model_dump())
    if len(raw) > MAX_BYTES:
        raise ValueError('snapshot_byte_budget')
    return raw


def export_structure_snapshot(workspace, space, pin):
    binding, catalog = workspace.catalog(space, pin)
    if binding is None:
        raise ValueError('ifc_not_configured')
    try:
        return build_structure_snapshot(space, binding.catalog_sha256, catalog)
    except ValidationError as exc:
        raise ValueError('ifc_structure_evidence_invalid') from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('snapshot_duplicate_json_key')
        result[key] = value
    return result


def inspect_structure_snapshot(raw, *, expected_sha256, expected_source):
    """Verify exact bytes against an out-of-band pin; original IFC is not included."""
    source = SourcePin.model_validate(expected_source)
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('snapshot_byte_budget')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('snapshot_byte_digest')
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
        snapshot = StructureSnapshot.model_validate(value)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('snapshot_json_invalid') from exc
    if snapshot.source != source:
        raise ValueError('snapshot_source_binding')
    if canonical(snapshot.model_dump()) != raw:
        raise ValueError('snapshot_canonical_bytes_required')
    return snapshot


def snapshot_summary(snapshot):
    return {'profile': PROFILE, 'source': snapshot.source.model_dump(),
            'entities': len(snapshot.entities), 'relations': len(snapshot.relations),
            'declared_role_counts': dict(sorted(Counter(e.source_role for e in snapshot.entities).items())),
            'data_kind': snapshot.data_kind, 'assessment': snapshot.assessment,
            'original_ifc_content_verified': False, 'ontology_bound': False,
            'geometry_included': False, 'alignment_verified': False, 'real_release_ready': False}
