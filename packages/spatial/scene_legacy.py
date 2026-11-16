"""Declared legacy point anchors only; does not adopt real data as synthetic truth."""
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import Field, ValidationError

from packages.spatial.scene_graph import Fixed, Identity, Vector
from packages.spatial.scene_identity import Digest

MAX_LEGACY_BYTES = 2 * 1024 * 1024
LEGACY_SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/preview-objects-v0.1.schema.json'


class TypeMapping(Fixed):
    source_type_id: Identity
    target_type_id: Identity


class AnchorMapping(Fixed):
    profile: Literal['cospace.legacy-anchor-mapping/0.1']
    source_document_sha256: Digest
    source_space_id: Identity
    source_model_id: Identity
    source_model_sha256: Digest
    source_frame_id: Identity
    mappings: Annotated[list[TypeMapping], Field(min_length=1, max_length=100)]


def _read_document(raw, expected_digest):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_LEGACY_BYTES:
        raise ValueError('legacy_byte_budget')
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError('legacy_document_digest')
    document = json.loads(raw, object_pairs_hook=_unique_json_keys)
    schema = json.loads(LEGACY_SCHEMA.read_bytes())
    if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(document):
        raise ValueError('legacy_document_structure')
    return document


def _unique_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_legacy_json_key')
        result[key] = value
    return result


class Anchor(Fixed):
    entity_id: Identity
    source_type_id: Identity
    target_type_id: Identity
    position: Vector
    source_point_index: Annotated[int, Field(ge=0)]


def _source_binding(document, mapping):
    expected = {'space_id': mapping.source_space_id, 'model_id': mapping.source_model_id,
                'source_model_sha256': mapping.source_model_sha256, 'frame_id': mapping.source_frame_id}
    if any(document[key] != value for key, value in expected.items()):
        raise ValueError('legacy_source_binding')


def _anchor(obj, mappings, model_sha256):
    if obj['type_id'] not in mappings:
        raise ValueError('legacy_type_mapping_missing')
    if obj['evidence']['sha256'] != model_sha256:
        raise ValueError('legacy_point_source_binding')
    try:
        return Anchor(entity_id=obj['object_id'], source_type_id=obj['type_id'],
                      target_type_id=mappings[obj['type_id']], position=obj['anchor_m'],
                      source_point_index=obj['evidence']['point_index']).model_dump()
    except ValidationError as exc:
        raise ValueError('legacy_anchor_structure:' + str(exc)) from exc


def project_legacy_anchors(raw, mapping_document):
    """Project explicit source coordinates; does not recompute or verify model points."""
    try:
        mapping = AnchorMapping.model_validate(mapping_document)
    except ValidationError as exc:
        raise ValueError('legacy_mapping_structure:' + str(exc)) from exc
    document = _read_document(raw, mapping.source_document_sha256)
    _source_binding(document, mapping)
    mappings = {m.source_type_id: m.target_type_id for m in mapping.mappings}
    if len(mappings) != len(mapping.mappings):
        raise ValueError('duplicate_legacy_type_mapping')
    anchors = [_anchor(obj, mappings, mapping.source_model_sha256) for obj in document['objects']]
    if len({a['entity_id'] for a in anchors}) != len(anchors):
        raise ValueError('duplicate_legacy_object')
    return {'profile': 'cospace.legacy-anchor-projection/0.1', 'source': mapping.model_dump(),
            'data_kind': 'source_unverified', 'frame_id': mapping.source_frame_id, 'unit': 'm',
            'anchors': anchors, 'geometry_role': 'reference_point',
            'limitations': ['declared_point_only', 'no_extent_or_connections', 'no_coordinate_transform',
                            'no_model_point_recomputation', 'target_type_meaning_unverified'],
            'evidence_verified': False, 'real_release_ready': False, 'robot_ready': False}
